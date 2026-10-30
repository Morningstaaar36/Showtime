"""Designer agent: a plain-language venue description → VenueSpec → solved, checked Venue.

The model writes relationships (sizes, walls, regions); `build_venue` computes the geometry;
the geometry checks run on the result and their errors go back to the model once
(describe → solve → check → repair, as in Holodeck and Text2BIM). Then the design goes round:
a plan checker measures it (people placed, an instant evacuation estimate, the real site's
size), a model that reads images looks at the drawn plans, and the designer revises, up to
`DESIGN_ROUNDS` times; the best round is kept and every round is recorded on the venue.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from api.adapters.llm import BudgetExceeded
from api.agents.base import AgentCall, AgentDef, AgentEnv, AgentUnavailable, call_agent
from api.agents.plan_critic import critic_on, critique_plan
from api.core.design_review import DesignReview, score
from api.core.estimates import ratios
from api.core.geometry import Check, validate_venue
from api.core.venue_builder import BuildResult, build_venue
from api.models import Exit, Obstacle, Venue, Zone
from api.models.venue_spec import VenueSpec

DESIGNER_AGENT = AgentDef(
    name="designer",
    role="main",
    prompt_file="venue_designer.md",
    output_model=VenueSpec,
    temperature=0.1,
    max_tokens=1800,
    description="Turns a description of a venue into a layout the solver can build.",
)

_BLOCKING = ("Left out", "No room", "No exit", "Open-air sites have one level", "too shallow")


@dataclass
class DesignOutcome:
    """A built venue (or why there is none)."""

    status: str  # built | needs_fixes (open it and fix the listed problems) | failed
    venue: Venue | None = None
    spec: VenueSpec | None = None
    notes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    call: AgentCall[VenueSpec] | None = None


# what the model can change in the spec, by geometry check (the checks speak of the venue)
_SPEC_FIX: dict[str, str] = {
    "zone_overfull": "Make the floor larger (width_m, depth_m) or put fewer people there.",
    "zone_no_exit": "Add an exit on a wall of that level, or a stair (building.stairs).",
    "zone_outside": "Make the floor larger or remove features that fill it.",
    "exit_outside": "Put the exit on another wall or position.",
    "exit_too_narrow": "Make the exit at least 0.8 m wide.",
    "stair_outside": "Make the building larger or put the stair near another wall.",
    "no_open_exit": "Add at least one exit on a free wall of the street level.",
}


def _for_designer(c: Check, venue: Venue) -> str:
    """A geometry error in terms the designer knows: names and levels, not object ids."""
    names: dict[str, str] = {}
    for f in venue.floors:
        floor = (f.name or f.floor_id).lower()
        items: list[Zone | Exit | Obstacle] = [*f.zones, *f.exits, *f.obstacles]
        for item in items:
            label = getattr(item, "label", None) or item.id
            names[item.id] = f"“{label.split(' · ')[0]}” on the {floor}"
    msg = c.message
    for oid in c.target_ids:
        if oid in names:
            msg = msg.replace(f"'{oid}'", names[oid])
    return f"{msg} {_SPEC_FIX.get(c.code, c.hint or '')}".strip()


# how far the layout's headcount may stray from the one the event brief gives
PEOPLE_TOLERANCE = 0.05


def check_spec(spec: VenueSpec, people: int | None = None) -> tuple[BuildResult, list[str]]:
    """Build a spec and list what the model must fix (solver omissions and geometry errors).

    `people` is the event's headcount when the caller knows it (the Brief agent read it from
    the request): a layout that holds a different number is sent back to the model.
    """
    built = build_venue(spec)
    problems = list(built.problems)
    problems += [n for n in built.notes if any(b in n for b in _BLOCKING)]
    for c in validate_venue(built.venue).checks:
        if c.severity == "error":
            problems.append(_for_designer(c, built.venue))
    want, got = spec.total_people(), built.venue.total_people()
    if want and got != want and not problems:
        problems.append(
            f"The description gives {want:,} people but the layout holds {got:,}: "
            "check the headcounts per level and per zone."
        )
    if people and not problems and abs(got - people) > PEOPLE_TOLERANCE * people:
        problems.append(
            f"The event has {people:,} people but the layout holds {got:,}: "
            "set the headcounts per level or per zone so they add up to the event's total."
            + _area_hint(spec)
        )
    return built, problems


def _area_hint(spec: VenueSpec) -> str:
    """Name the passages and end areas a zone can stand in, when the layout has any: a model
    that puts every group on the main floor often drops the ones the description places there."""
    labels = [p.label for p in spec.passages]
    labels += [p.end_area.label for p in spec.passages if p.end_area is not None]
    used = {z.area for z in spec.zones if z.area}
    free = [lab for lab in labels if lab and lab not in used]
    if not free:
        return ""
    names = ", ".join(f'"{lab}"' for lab in free)
    return (
        f" Groups the description places in {names} need their own zone there"
        ' (its label as "area").'
    )


def _summary(s: VenueSpec) -> str:
    levels = ""
    if s.building is not None:
        b = s.building
        levels = f", {b.storeys} storeys" + (f" + {b.basements} basement" if b.basements else "")
    return (
        f"{s.mode} {s.width_m:g}×{s.depth_m:g} m{levels}, {len(s.exits)} exits, "
        f"{s.total_people():,} people"
    )


def _planning_space() -> dict[str, str]:
    """Space per person the prompt quotes, from the planning ratios (people per m² → m²)."""
    d = ratios()["planning_density_ppm2"]
    return {"seated_m2": f"{1 / d['seated']:.1f}", "standing_m2": f"{1 / d['standing']:.1f}"}


Progress = Callable[[dict[str, Any]], None]
SiteOf = Callable[[VenueSpec], Awaitable[dict[str, Any] | None]]
Review = Callable[[VenueSpec, Venue], DesignReview]
SITE_FIT = 0.15  # a drawn size this far from the real building's is sent back
CRITIC_REVISIONS = 1  # revisions the plan critic's points alone may ask for


def _site_fixes(spec: VenueSpec, site: dict[str, Any] | None) -> list[str]:
    """The real building's size, when the layout strays from it (either way round)."""
    if not site or not site.get("width_m"):
        return []
    w, d = float(site["width_m"]), float(site["depth_m"])

    def near(a: float, b: float) -> bool:
        return abs(a - b) <= SITE_FIT * b

    if (near(spec.width_m, w) and near(spec.depth_m, d)) or (
        near(spec.width_m, d) and near(spec.depth_m, w)
    ):
        return []
    return [
        f"The real building ({site['source']}) measures {w:g} m east-west by {d:g} m "
        f"north-south; the layout is {spec.width_m:g} × {spec.depth_m:g} m. Use the real size."
    ]


def _revision_task(task: str, spec: VenueSpec, issues: list[str], request: str = "") -> str:
    lines = "\n".join(f"- {i}" for i in issues)
    ask = f"\nThe organizer asks: {request.strip()}" if request.strip() else ""
    return (
        f"{task}\n\nYour previous layout:\n{spec.model_dump_json(exclude_none=True)}\n\n"
        f"A review of it found:\n{lines}{ask}\n\nRevise the layout. Keep every fact the "
        "description states (sizes, storeys, stairs, exits, headcounts); change only what fixes "
        "these points, and leave out any point that asks for something the description does not "
        "state. Return the complete layout JSON."
    )


async def design_venue(
    env: AgentEnv,
    text: str,
    people: int | None = None,
    *,
    review: Review | None = None,
    site_of: SiteOf | None = None,
    progress: Progress | None = None,
    rounds: int = 1,
    start: VenueSpec | None = None,
    request: str = "",
) -> DesignOutcome:
    """Design a venue from a description: design, check, critique, revise, keep the best.

    `people`: the event's total headcount when it is known apart from the description.
    `review` measures a built design (plan checker + instant estimate); `site_of` finds the
    real building for a spec (map APIs); `rounds` caps the design rounds. `start` and
    `request` redesign an existing layout with the organizer's own words.
    """
    say = progress or (lambda _e: None)
    task = f'Description: "{text.strip()}"'
    if people:
        task += f"\nPeople at the event: {people:,} in total."
    say({"round": 1, "of": rounds, "stage": "designing"})
    if start is not None:
        call = await call_agent(
            env, DESIGNER_AGENT, _planning_space(),
            _revision_task(task, start, ["(none: this is the organizer's change)"], request),
            output_model=VenueSpec, validate=lambda sp: check_spec(sp, people)[1],
            summarize=_summary,
        )  # fmt: skip
    else:
        call = await call_agent(
            env,
            DESIGNER_AGENT,
            _planning_space(),
            task,
            output_model=VenueSpec,
            validate=lambda spec: check_spec(spec, people)[1],
            summarize=_summary,
        )
    spec = call.output
    if spec is None:
        return DesignOutcome(
            status="failed",
            call=call,
            problems=[call.error or "The model did not return a layout."],
        )
    site: dict[str, Any] | None = None
    if site_of is not None:
        try:
            site = await site_of(spec)
        except Exception as exc:  # the map is a help, never a reason to fail the design
            site = {"source": "no building outline", "notes": [f"Map lookup failed: {exc}"]}
        if site and site.get("width_m"):
            task += f"\n{site.get('brief', '')}"
    log: list[dict[str, Any]] = []
    best: tuple[Any, ...] | None = None
    current_call = call
    critic_revisions = 0
    for r in range(1, rounds + 1):
        built, problems = check_spec(spec, people)
        say({"round": r, "of": rounds, "stage": "checking"})
        rv = review(spec, built.venue) if review is not None else DesignReview()
        fixes = [*problems, *_site_fixes(spec, site), *rv.fixes]
        critique: list[str] = []
        dropped: list[str] = []
        critic = "off"
        if critic_on(env) and not problems:
            say({"round": r, "of": rounds, "stage": "critiquing"})
            try:
                c = await critique_plan(env, text, built.venue)
            except AgentUnavailable:
                c = None
            critic = "no answer" if c is None else ("ok" if not c.issues else "issues")
            critique = c.issues if c is not None else []
            dropped = c.dropped if c is not None else []
        log.append(
            {
                "round": r,
                "summary": _summary(spec),
                "problems": problems,
                "fixes": fixes[len(problems) :],
                "notes": rv.notes,
                "critic": critic,
                "critique": critique,
                "critique_dropped": dropped,
                "evac_s": rv.evac_s,
                "not_out": rv.not_out,
                "per_floor": rv.per_floor,
            }
        )
        # the round that best matches the description wins, the earliest of equals: a faster
        # evacuation is no reason to keep a layout (a real case must stay as unsafe as it was)
        rank = (*score(rv, problems)[:2], len(_site_fixes(spec, site)), len(critique), r)
        if best is None or rank < best[0]:
            best = (rank, r, spec, built, problems, current_call)
        todo = fixes + critique
        # the critic reads a drawing and can be wrong: its points alone earn one revision, the
        # measured ones (the plan checker's) every round there is
        critic_only = not fixes and bool(critique)
        if r == rounds or not todo or (critic_only and critic_revisions >= CRITIC_REVISIONS):
            break
        critic_revisions += int(critic_only)
        say({"round": r + 1, "of": rounds, "stage": "revising"})
        try:
            revised = await call_agent(
                env, DESIGNER_AGENT, _planning_space(), _revision_task(task, spec, todo),
                output_model=VenueSpec, validate=lambda sp: check_spec(sp, people)[1],
                summarize=_summary,
            )  # fmt: skip
        except (AgentUnavailable, BudgetExceeded):
            # the model stopped answering mid-way: the best round so far still stands
            log[-1]["revision"] = "the model did not answer"
            break
        if revised.output is None:
            break
        spec, current_call = revised.output, revised
    assert best is not None
    _, kept, spec, built, problems, call = best
    for entry in log:
        entry["kept"] = entry["round"] == kept
    say({"round": kept, "of": rounds, "stage": "done"})
    blocking = [c for c in validate_venue(built.venue).checks if c.severity == "error"]
    ext = dict(built.venue.extensions)
    generated = dict(ext.get("generated") or {})
    generated["design_rounds"] = log
    generated["spec"] = json.loads(spec.model_dump_json(exclude_none=True))
    generated["description"] = text.strip()[:4000]
    if site:
        generated["site"] = {k: v for k, v in site.items() if k not in ("neighbours", "brief")}
        if site.get("neighbours"):
            ext["site"] = {"context": site["neighbours"], "source": site.get("source")}
    ext["generated"] = generated
    venue = built.venue.model_copy(update={"extensions": ext})
    site_notes = list((site or {}).get("notes") or [])
    return DesignOutcome(
        status="needs_fixes" if blocking or problems else "built",
        venue=venue,
        spec=spec,
        notes=[n for n in built.notes if n not in problems] + site_notes,
        assumptions=[*spec.assumptions, *built.assumptions],
        problems=problems,
        call=call,
    )
