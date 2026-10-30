"""A designed building, checked the way a plan checker would before anyone simulates it.

The designer's layout is measured, not judged by a model: does it hold what the description
says, can everyone reach a way out, how far do people walk to it, how crowded is each floor,
does each floor have the fit-out its use needs, and how long does everyone take to get out
(the instant estimate, with people placed in every area). Findings come in two kinds:
- `fix`: the layout does not match the description or cannot work; the designer revises it;
- `note`: a fact about the building as described (one stair for 45 people), reported but
  never "fixed": a real case must stay the building it was.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from shapely.geometry import Point
from shapely.ops import unary_union

from api.core.estimates import ratios
from api.core.extensions import geometry as geo
from api.core.tier1 import run_tier1
from api.models import Venue
from api.models.venue_spec import VenueSpec

# common path of travel to a choice of two ways out, for assembly use (IBC 1006.2.1: 75 ft)
COMMON_PATH_M = 23.0
# more people than this on a floor need two ways out of it (IBC table 1006.3.3, assembly: 49)
ONE_EXIT_MAX_PEOPLE = 49
TOO_DENSE_PPM2 = 4.0  # more than this standing in an area is a crush before anything happens
FITOUT_WORDS = {
    "dining": ("restaurant", "café", "cafe", "food court", "dining", "eatery", "kitchen"),
    "rooms": ("ward", "classroom", "guest room", "hotel room", "office room"),
}


@dataclass
class Finding:
    kind: Literal["fix", "note"]
    text: str


@dataclass
class DesignReview:
    """What the plan checker found, and the instant estimate of getting everyone out."""

    findings: list[Finding] = field(default_factory=list)
    evac_s: float | None = None  # instant estimate, 95 % of people out
    not_out: int = 0  # people with no way out in the estimate
    per_floor: list[dict[str, Any]] = field(default_factory=list)

    @property
    def fixes(self) -> list[str]:
        return [f.text for f in self.findings if f.kind == "fix"]

    @property
    def notes(self) -> list[str]:
        return [f.text for f in self.findings if f.kind == "note"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixes": self.fixes,
            "notes": self.notes,
            "evac_s": self.evac_s,
            "not_out": self.not_out,
            "per_floor": self.per_floor,
        }


def _ways_out(venue: Venue, floor_id: str) -> list[Any]:
    """Where people on a floor leave it: its exits and the top landings of stairs down (or up
    from a basement) that start on it."""
    f = next(x for x in venue.floors if x.floor_id == floor_id)
    out = [geo.to_polygon(e.polygon) for e in f.exits if not e.blocked]
    out += [geo.to_polygon(s.top_polygon) for s in venue.stairs if s.from_floor == floor_id]
    return out


def review_design(
    description: str, spec: VenueSpec, venue: Venue, registry: Any, settings: Any
) -> DesignReview:
    """Measure a built design against its description and the usual planning limits."""
    rv = DesignReview()
    text = description.lower()
    b = spec.building
    interior = b.interior if b is not None else "open"
    for want, words in FITOUT_WORDS.items():
        if interior != want and any(w in text for w in words) and b is not None:
            rv.findings.append(
                Finding(
                    "fix",
                    f"The description speaks of {', '.join(w for w in words if w in text)}, "
                    f'but building.interior is "{interior}": set it to "{want}" so each floor '
                    "gets that fit-out.",
                )
            )
    seated = 1 / ratios()["planning_density_ppm2"]["seated"]
    for f in venue.floors:
        people = sum(z.people for z in f.zones)
        name = f.name or f.floor_id
        obstacles = unary_union([geo.to_polygon(o.polygon) for o in f.obstacles])
        area = sum(
            geo.to_polygon(z.polygon).difference(obstacles).area for z in f.zones if z.people > 0
        )
        ways = _ways_out(venue, f.floor_id)
        far = 0.0
        if ways and f.zones:
            target = unary_union(ways)
            far = max(Point(p).distance(target) for z in f.zones if z.people > 0 for p in z.polygon)
        density = people / area if area > 0 else 0.0
        rv.per_floor.append(
            {
                "floor": name,
                "people": people,
                "area_m2": round(area, 1),
                "people_per_m2": round(density, 2),
                "farthest_walk_m": round(far, 1),
                "ways_out": len(ways),
            }
        )
        if people and not ways:
            rv.findings.append(Finding("fix", f"{name}: {people} people and no way out of it."))
        if density > TOO_DENSE_PPM2:
            rv.findings.append(
                Finding(
                    "fix",
                    f"{name}: {people} people on {area:.0f} m² of free floor "
                    f"({density:.1f} per m²): the floor is too small for them; make the "
                    "building larger or check the headcount.",
                )
            )
        elif density > 1 / seated * 1.5:
            rv.findings.append(
                Finding("note", f"{name}: {density:.1f} people per m² of free floor, crowded.")
            )
        if len(ways) == 1 and people > ONE_EXIT_MAX_PEOPLE:
            rv.findings.append(
                Finding(
                    "note",
                    f"{name}: {people} people and one way out; building codes ask for two "
                    f"above {ONE_EXIT_MAX_PEOPLE} (IBC table 1006.3.3).",
                )
            )
        if len(ways) == 1 and far > COMMON_PATH_M:
            rv.findings.append(
                Finding(
                    "note",
                    f"{name}: up to {far:.0f} m to its one way out (codes allow about "
                    f"{COMMON_PATH_M:.0f} m before there must be a second).",
                )
            )
    t1 = run_tier1(venue, [], registry, settings)
    rv.evac_s = t1.metrics.evac_time_p95_s or t1.metrics.evac_time_max_s
    rv.not_out = int(t1.metrics.agents_not_evacuated or 0)
    if rv.not_out:
        rv.findings.append(
            Finding(
                "fix",
                f"In the instant estimate {rv.not_out} people cannot reach a way out: a stair, "
                "exit or feature blocks them. Move it or add a way out where they stand.",
            )
        )
    return rv


def score(rv: DesignReview, problems: list[str]) -> tuple[int, int, float]:
    """Lower is better: blocking problems, then things to fix, then the estimate."""
    return (len(problems), len(rv.fixes), rv.evac_s if rv.evac_s is not None else math.inf)
