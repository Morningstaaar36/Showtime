"""What-if designer: the AI chooses which scenarios a venue should be tested under.

It sees the venue and a toolbox: the scenario library (each entry already made concrete for
this venue) and the scenario events it may compose into a scenario of its own. It writes no
numbers: every scenario is then simulated, and only the simulation's numbers are shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import GenericAlias
from typing import Any

from pydantic import BaseModel, Field, create_model

from api.agents.base import AgentCall, AgentDef, AgentEnv, call_agent
from api.agents.context import event_union, events_doc, ids_line, readable, venue_summary
from api.core.extensions import Registry
from api.core.scenarios import CATEGORY_LABELS, Built, Category, Resolved, ScenarioSpec
from api.models import ScenarioEventIn, Venue

MAX_WHAT_IFS = 6
# icon per category for scenarios the AI composes itself (lucide names)
CATEGORY_ICON: dict[str, str] = {
    "fire_smoke": "flame",
    "crowd": "users",
    "weather": "cloud-rain",
    "access": "door-closed",
    "people": "accessibility",
    "operations": "clipboard-list",
}


class WhatIfBase(BaseModel):
    """Static stand-in for the dynamic output model."""

    scenarios: list[dict[str, Any]] = Field(default_factory=list)


WHAT_IF_AGENT = AgentDef(
    name="what_if",
    role="fast",
    prompt_file="what_if.md",
    output_model=WhatIfBase,
    temperature=0.3,
    max_tokens=1800,
    description="Chooses and composes the what-if scenarios a venue should be tested under.",
)


def _allowed(registry: Registry) -> set[str]:
    # every scenario event except free-form scripts (those are the red team's)
    return {ev.type for ev in registry.all("ScenarioEvent") if ev.type != "script"}


def _model(registry: Registry) -> type[BaseModel]:
    draft = create_model(
        "WhatIfDraft",
        # a plain string: an unknown id is sent back (and then dropped) on its own, instead of
        # failing the whole answer
        use=(str | None, Field(default=None, description="a library id, or null to compose")),
        title=(str, Field(default="", max_length=40)),
        why=(str, Field(default="", max_length=160)),
        category=(Category, "crowd"),
        events=(
            GenericAlias(list, event_union(registry, _allowed(registry))),
            Field(default_factory=list, max_length=6),
        ),
        people_scale=(float, Field(default=1.0, ge=0.5, le=1.5)),
    )
    return create_model(
        "WhatIfOut",
        scenarios=(GenericAlias(list, draft), Field(min_length=2, max_length=MAX_WHAT_IFS)),
    )


def _library_doc(library: list[Resolved]) -> str:
    lines = []
    for r in library:
        if r.built is None:
            continue
        targets = "; ".join(r.built.targets)[:140]
        lines.append(f"- {r.spec.id}: {r.spec.title} — {r.spec.description} ({targets})")
    return "\n".join(lines)


@dataclass
class WhatIfPlan:
    """The scenarios to run, in the AI's order, and the model call behind them."""

    scenarios: list[Resolved]
    call: AgentCall[Any]


async def design_what_ifs(
    env: AgentEnv, registry: Registry, venue: Venue, library: list[Resolved], context: str = ""
) -> WhatIfPlan:
    """Ask the AI for up to six what-ifs: library entries by id, or its own composed from
    events. Unknown ids, wrong references and oversized crowds go back to it once."""
    ready = {r.spec.id: r for r in library if r.built is not None}
    model = _model(registry)
    total = venue.total_people()

    def problems_of(d: Any) -> list[str]:
        if d.use is not None:
            return [] if d.use in ready else [f"'{d.use}' is not in the library"]
        p: list[str] = []
        if not d.events:
            p.append("a composed scenario needs events (or 'use' a library id)")
        if not d.title.strip():
            p.append("a composed scenario needs a title")
        for e in d.events:
            spec = registry.event(e.type)
            p.extend(spec.validate_refs(venue, spec.params_model.model_validate(e.model_dump())))
            if e.type == "surge" and e.extra_people > max(50, total // 2):
                p.append(f"a surge of {e.extra_people} is more than half the crowd")
            if e.type == "counterflow" and e.people > max(50, total // 3):
                p.append(f"a counterflow of {e.people} is more than a third of the crowd")
            if e.at_s > 600:
                p.append("events must start within the first 10 minutes")
        return p

    def validate(out: Any) -> list[str]:
        probs: list[str] = []
        for i, d in enumerate(out.scenarios):
            probs.extend(f"scenario {i + 1}: {x}" for x in problems_of(d))
        return probs[:6]

    call = await call_agent(
        env,
        WHAT_IF_AGENT,
        {
            "venue": venue_summary(venue),
            "ids": ids_line(venue),
            "library": _library_doc(library) or "(empty)",
            "events": events_doc(registry, _allowed(registry)),
            "context": context or "(none)",
            "categories": ", ".join(CATEGORY_LABELS),
        },
        "Choose the what-ifs for this venue.",
        output_model=model,
        validate=validate,
        summarize=lambda o: f"{len(o.scenarios)} what-ifs",
    )
    out: list[Resolved] = []
    seen: set[str] = set()
    for i, d in enumerate(call.output.scenarios if call.output is not None else []):
        if problems_of(d):
            continue  # still wrong after the repair round: left out
        if d.use is not None:
            if d.use not in seen:
                seen.add(d.use)
                out.append(ready[d.use])
            continue
        events = [ScenarioEventIn.model_validate(e.model_dump()) for e in d.events]
        title = readable(d.title.strip(), venue)
        built = Built(events=events, scale=d.people_scale, targets=[readable(d.why, venue)])
        spec = ScenarioSpec(
            id=f"ai_{i + 1}",
            title=title,
            description=readable(d.why, venue),
            icon=CATEGORY_ICON.get(d.category, "sparkles"),
            category=d.category,
            applies_to=(),
            build=lambda _f, b=built: b,
            label=title,
        )
        out.append(Resolved(spec, built))
    return WhatIfPlan(scenarios=out[:MAX_WHAT_IFS], call=call)
