"""Designer agent: a plain-language venue description → VenueSpec → solved, checked Venue.

The model writes relationships (sizes, walls, regions); `build_venue` computes the geometry;
the geometry checks run on the result and their errors go back to the model once
(describe → solve → check → repair, as in Holodeck and Text2BIM).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.agents.base import AgentCall, AgentDef, AgentEnv, call_agent
from api.core.geometry import Check, validate_venue
from api.core.venue_builder import BuildResult, build_venue
from api.models import Venue
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
        for item in [*f.zones, *f.exits, *f.obstacles]:
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


async def design_venue(env: AgentEnv, text: str, people: int | None = None) -> DesignOutcome:
    """Ask the designer for a spec, solve it, and repair once if the checks fail.

    `people`: the event's total headcount when it is known apart from the description.
    """
    task = f'Description: "{text.strip()}"'
    if people:
        task += f"\nPeople at the event: {people:,} in total."
    call = await call_agent(
        env,
        DESIGNER_AGENT,
        {},
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
    built, problems = check_spec(spec, people)
    # anything the model still has to fix (a geometry error, a crowd heading for an exit that
    # does not exist, a headcount that does not add up) means the layout is not ready to test
    blocking = [c for c in validate_venue(built.venue).checks if c.severity == "error"]
    return DesignOutcome(
        status="needs_fixes" if blocking or problems else "built",
        venue=built.venue,
        spec=spec,
        notes=[n for n in built.notes if n not in problems],
        assumptions=[*spec.assumptions, *built.assumptions],
        problems=problems,
        call=call,
    )
