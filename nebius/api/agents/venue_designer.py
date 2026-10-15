"""Designer agent: a plain-language venue description → VenueSpec → solved, checked Venue.

The model writes relationships (sizes, walls, regions); `build_venue` computes the geometry;
the geometry checks run on the result and their errors go back to the model once
(describe → solve → check → repair, as in Holodeck and Text2BIM).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.agents.base import AgentCall, AgentDef, AgentEnv, call_agent
from api.core.geometry import validate_venue
from api.core.venue_builder import BuildResult, build_venue
from api.models import Venue
from api.models.venue_spec import VenueSpec

DESIGNER_AGENT = AgentDef(
    name="designer",
    role="main",
    prompt_file="venue_designer.md",
    output_model=VenueSpec,
    temperature=0.1,
    max_tokens=1500,
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


def check_spec(spec: VenueSpec) -> tuple[BuildResult, list[str]]:
    """Build a spec and list what the model must fix (solver omissions and geometry errors)."""
    built = build_venue(spec)
    problems = [n for n in built.notes if any(b in n for b in _BLOCKING)]
    for c in validate_venue(built.venue).checks:
        if c.severity == "error":
            problems.append(c.message + (f" {c.hint}" if c.hint else ""))
    return built, problems


async def design_venue(env: AgentEnv, text: str) -> DesignOutcome:
    """Ask the designer for a spec, solve it, and repair once if the checks fail."""
    call = await call_agent(
        env,
        DESIGNER_AGENT,
        {},
        f'Description: "{text.strip()}"',
        output_model=VenueSpec,
        validate=lambda spec: check_spec(spec)[1],
        summarize=lambda s: (
            f"{s.mode} {s.width_m:g}×{s.depth_m:g} m, {len(s.exits)} exits, "
            f"{sum(z.people for z in s.zones):,} people"
        ),
    )
    spec = call.output
    if spec is None:
        return DesignOutcome(
            status="failed",
            call=call,
            problems=[call.error or "The model did not return a layout."],
        )
    built, problems = check_spec(spec)
    blocking = [c for c in validate_venue(built.venue).checks if c.severity == "error"]
    return DesignOutcome(
        status="needs_fixes" if blocking else "built",
        venue=built.venue,
        spec=spec,
        notes=[n for n in built.notes if n not in problems],
        assumptions=[*spec.assumptions, *built.assumptions],
        problems=problems,
        call=call,
    )
