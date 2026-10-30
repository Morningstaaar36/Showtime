"""Plan critic: a model that reads images checks the drawn floor plans against the description.

The plans are drawn by `api.core.plan_image`; the critic's issues go back to the designer in its
next round. It only runs when a model that reads images is configured (`MODEL_VISION`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.agents.base import AgentDef, AgentEnv, call_agent
from api.core.plan_image import drawn_floors, plan_data_url
from api.models import Venue


class Issue(BaseModel):
    issue: str = Field(max_length=300)
    # the description's own words that the plan contradicts: an issue without them is dropped
    quote: str = Field(default="", max_length=300)


class Answer(BaseModel):
    matches_description: bool = True
    issues: list[Issue] = Field(default_factory=list, max_length=5)


class Critique(BaseModel):
    matches_description: bool = True
    issues: list[str] = Field(default_factory=list, max_length=5)
    dropped: list[str] = Field(default_factory=list)  # issues the description does not support


def _words(text: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def grounded(
    description: str, issues: list[Issue], min_chars: int = 12
) -> tuple[list[str], list[str]]:
    """Issues that quote the description (word for word, ignoring case and punctuation), and
    the ones that do not: a critic may only hold the plan to what the organizer wrote."""
    text = _words(description)
    kept: list[str] = []
    dropped: list[str] = []
    for i in issues:
        q = _words(i.quote)
        (kept if len(q) >= min_chars and q in text else dropped).append(i.issue.strip()[:240])
    return [k for k in kept if k], [d for d in dropped if d]


PLAN_CRITIC_AGENT = AgentDef(
    name="plan_critic",
    role="vision",
    prompt_file="plan_critic.md",
    output_model=Answer,
    temperature=0.1,
    max_tokens=700,
    description="Looks at the drawn floor plans and says what does not match the description.",
)


def critic_on(env: AgentEnv) -> bool:
    """Whether a model that reads images is configured."""
    settings = getattr(env.llm, "settings", None)
    return bool(settings is not None and getattr(settings, "model_vision", ""))


def plan_facts(venue: Venue) -> str:
    """Each floor's exact counts, from the geometry: the critic reads the drawing for where
    things are, and these for how many (a model reading an image miscounts small labels)."""
    lines: list[str] = []
    for f in sorted(venue.floors, key=lambda x: x.elevation_m):
        labels: dict[str, int] = {}
        for o in f.obstacles:
            key = (o.label or o.kind).split(" (")[0]
            if key in ("Table", "Wall", "Stairwell wall") or key.startswith("Stairwell"):
                continue
            labels[key] = labels.get(key, 0) + 1
        exits = [f"{e.label or e.id} {e.width_m:g} m" for e in f.exits]
        stairs = sum(1 for s in venue.stairs if f.floor_id in (s.from_floor, s.to_floor))
        tables = sum(1 for o in f.obstacles if o.label == "Table")
        kept = ", ".join(f"{n} × {k}" if n > 1 else k for k, n in labels.items()) or "none"
        lines.append(
            f"- {f.name or f.floor_id}: {sum(z.people for z in f.zones)} people; exits: "
            f"{', '.join(exits) or 'none (people leave by the stairs)'}; stair flights touching "
            f"it: {stairs}; fixtures: {kept}; tables: {tables}"
        )
    return "\n".join(lines)


async def critique_plan(env: AgentEnv, description: str, venue: Venue) -> Critique | None:
    """The critic's view of the drawn plans, or None when it gave no valid answer."""
    shown = [venue.floors[i] for i in drawn_floors(venue)]
    call = await call_agent(
        env,
        PLAN_CRITIC_AGENT,
        {
            "description": description.strip()[:2500],
            "shown": ", ".join(f.name or f.floor_id for f in shown),
            "total": str(len(venue.floors)),
            "facts": plan_facts(venue),
        },
        "Check these floor plans against the description.",
        output_model=Answer,
        images=[plan_data_url(venue)],
        summarize=lambda c: (
            "matches the description"
            if not c.issues
            else "; ".join(i.issue for i in c.issues)[:200]
        ),
    )
    if call.output is None:
        return None
    c = call.output
    kept, dropped = grounded(description, c.issues)
    return Critique(
        matches_description=c.matches_description or not kept, issues=kept[:5], dropped=dropped
    )
