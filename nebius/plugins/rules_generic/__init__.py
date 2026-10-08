"""Example egress rules (RulesPack). Values follow the International Building Code (IBC 2021,
chapter 10) for orientation only; local codes differ. Findings stay "unconfirmed" until the
user checks the source."""

from __future__ import annotations

import math

from pydantic import BaseModel

from api.core.extensions import Registry, RuleFinding
from api.core.extensions import geometry as geo
from api.models import RunResult, Venue

IBC = "https://codes.iccsafe.org/content/IBC2021P1/chapter-10-means-of-egress"


class Config(BaseModel):
    """Example limits (edit in plugin.toml)."""

    mm_exit_width_per_person: float = 5.1  # IBC 1005.3.2: 0.2 in per occupant
    max_travel_m: float = 61.0  # IBC table 1017.2, assembly without sprinklers: 200 ft
    max_standing_density: float = 2.15  # IBC table 1004.5: 5 sq ft net per person standing
    two_exits_above: int = 49  # IBC 1006.2.1


class GenericRules:
    """Checkable example rules; the numbers they compare are computed from the plan."""

    id = "rules_generic"
    label = "Generic egress rules (example values, IBC 2021)"

    def __init__(self, config: Config) -> None:
        self.c = config

    def check(self, venue: Venue, tier1: RunResult | None) -> list[RuleFinding]:
        c = self.c
        out: list[RuleFinding] = []
        people = venue.total_people()
        exits = [(f, e) for f in venue.floors for e in f.exits if not e.blocked]
        width = sum(e.width_m for _, e in exits)
        need = people * c.mm_exit_width_per_person / 1000
        out.append(
            RuleFinding(
                rule_id="exit_width",
                metric="total exit width",
                value=round(width, 2),
                limit=round(need, 2),
                unit="m",
                status="pass" if width >= need else "fail",
                source_url=IBC,
                message=f"Exits give {width:.1f} m for {people:,} people; the example rule asks "
                f"{c.mm_exit_width_per_person:g} mm per person = {need:.1f} m.",
            )
        )
        out.append(
            RuleFinding(
                rule_id="two_exits",
                metric="open exits",
                value=len(exits),
                limit=2,
                unit="",
                status="pass" if people <= c.two_exits_above or len(exits) >= 2 else "fail",
                source_url=IBC,
                message=f"{len(exits)} open exits for {people:,} people (two or more above "
                f"{c.two_exits_above}).",
            )
        )
        for f in venue.floors:
            for z in f.zones:
                if z.people <= 0:
                    continue
                area = geo.to_polygon(z.polygon).area
                d = z.people / max(area, 1e-6)
                out.append(
                    RuleFinding(
                        rule_id=f"density:{z.id}",
                        metric="standing density",
                        value=round(d, 2),
                        limit=c.max_standing_density,
                        unit="people per m²",
                        target_id=z.id,
                        status="pass" if d <= c.max_standing_density else "fail",
                        source_url=IBC,
                        message=f"{z.label or z.id}: {d:.2f} people per m² at the start "
                        f"(example limit {c.max_standing_density:g}).",
                    )
                )
                floor_exits = [e for e in f.exits if not e.blocked]
                if floor_exits:
                    far = max(
                        min(math.dist(p, geo.centroid(e.polygon)) for e in floor_exits)
                        for p in z.polygon
                    )
                    out.append(
                        RuleFinding(
                            rule_id=f"travel:{z.id}",
                            metric="straight-line travel",
                            value=round(far, 1),
                            limit=c.max_travel_m,
                            unit="m",
                            target_id=z.id,
                            source_url=IBC,
                            status="pass" if far <= c.max_travel_m else "fail",
                            message=f"{z.label or z.id}: farthest corner is {far:.0f} m from the nearest "
                            f"exit in a straight line (example limit {c.max_travel_m:g} m; walking "
                            "routes are longer).",
                        )
                    )
        if len(exits) >= 2:
            pts = [geo.centroid(e.polygon) for _, e in exits]
            sep = max(math.dist(a, b) for a in pts for b in pts)
            x0, y0, x1, y1 = geo.to_polygon(venue.floors[0].walkable).bounds
            diag = math.hypot(x1 - x0, y1 - y0)
            out.append(
                RuleFinding(
                    rule_id="exit_separation",
                    metric="exit separation",
                    value=round(sep, 1),
                    limit=round(diag / 3, 1),
                    unit="m",
                    source_url=IBC,
                    status="pass" if sep >= diag / 3 else "fail",
                    message=f"The two farthest exits are {sep:.0f} m apart; the example rule asks at "
                    f"least a third of the diagonal ({diag / 3:.0f} m).",
                )
            )
        return out


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the rules pack."""
    registry.add("RulesPack", GenericRules.id, GenericRules(config))
