"""Organizer estimates: safe capacity, exits, staff, sanitation, fencing and a budget.

Every number comes from geometry, the instant estimate (Tier 1) or a published planning ratio
(`api/data/planning_ratios.json`, each with its source). Nothing here comes from a language model.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field
from shapely.geometry import Polygon
from shapely.ops import unary_union

from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.core.settings import ROOT_DIR
from api.models import Venue

Audience = Literal["standing", "seated", "mixed"]


class EstimateLine(BaseModel):
    """One estimated quantity and where it comes from."""

    key: str
    label: str
    value: float
    unit: str = ""
    detail: str = ""
    source: str = ""
    url: str = ""
    status: Literal["ok", "warn", "info"] = "info"


class BudgetLine(BaseModel):
    """Quantity × unit price (example prices unless the user set their own)."""

    item: str
    quantity: float
    unit: str
    unit_cost: float
    total: float


class Capacity(BaseModel):
    """The largest crowd the plan handles, and what limits it."""

    safe_people: int
    by_space: int
    by_egress: int | None
    limited_by: Literal["space", "exits", "stairs"]
    usable_area_m2: float
    density_ppm2: float
    target_evac_s: float
    current_people: int
    note: str


class Estimates(BaseModel):
    """Everything the Estimates panel and the report show."""

    event: dict[str, Any]
    capacity: Capacity
    lines: list[EstimateLine] = Field(default_factory=list)
    budget: list[BudgetLine] = Field(default_factory=list)
    budget_total: float = 0.0
    exit_width_open_m: float = 0.0
    exit_width_needed_m: float = 0.0
    currency: str = "USD"
    prices_are_examples: bool = True
    disclaimer: str = (
        "Estimates from published planning ratios and the instant egress model. "
        "Planning aid, not a safety certification: confirm with your licensing authority."
    )


@lru_cache(maxsize=1)
def ratios() -> dict[str, Any]:
    """Planning ratios with their sources."""
    data: dict[str, Any] = json.loads(
        (ROOT_DIR / "api" / "data" / "planning_ratios.json").read_text()
    )
    return data


def event_info(venue: Venue) -> dict[str, Any]:
    """Event details (set with the set_event op), with defaults that are stated."""
    ev = dict(venue.extensions.get("event") or {})
    ev.setdefault("duration_h", 4.0)
    ev.setdefault("alcohol", False)
    ev.setdefault("audience", "seated" if venue.mode == "indoor" else "standing")
    return ev


def usable_area(venue: Venue) -> float:
    """Floor area people can stand on inside the crowd zones (or all free floor if no zones)."""
    total = 0.0
    for f in venue.floors:
        free = geo.free_space(f)
        zones = [geo.to_polygon(z.polygon) for z in f.zones]
        if zones:
            total += float(unary_union(zones).intersection(free).area)
        elif isinstance(free, Polygon) or hasattr(free, "area"):
            total += float(free.area)
    return total


def scale_people(venue: Venue, factor: float) -> Venue:
    """The same plan with every zone's headcount multiplied by `factor` (total kept exact)."""
    if abs(factor - 1.0) < 1e-9:
        return venue
    v = venue.model_copy(deep=True)
    zones = [z for f in v.floors for z in f.zones]
    target = round(sum(z.people for z in zones) * factor)
    for z in zones:
        z.people = round(z.people * factor)
    if zones:
        zones[-1].people = max(0, zones[-1].people + target - sum(z.people for z in zones))
    return v


def capacity(venue: Venue, registry: Registry, settings: Any) -> Capacity:
    """Space-limited and exit-limited capacity (Green Guide method: width × flow × time)."""
    ev = event_info(venue)
    r = ratios()["planning_density_ppm2"]
    density = float(r.get(ev["audience"], r["standing"]))
    area = usable_area(venue)
    by_space = int(area * density)
    target = (
        settings.target_evac_indoor_s if venue.mode == "indoor" else settings.target_evac_outdoor_s
    )
    current = venue.total_people()
    width = sum(e.width_m for f in venue.floors for e in f.exits if not e.blocked)
    by_egress = int(width * settings.specific_flow * target)
    limited: Literal["space", "exits", "stairs"] = "exits" if by_egress < by_space else "space"
    upper = sum(z.people for f in venue.floors[1:] for z in f.zones)
    if venue.stairs and upper and current:
        stair_cap = sum(s.width_m for s in venue.stairs) * settings.stair_flow * target
        by_stairs = int(stair_cap / (upper / current))  # total crowd at which the stairs fill up
        if by_stairs < min(by_egress, by_space):
            by_egress, limited = by_stairs, "stairs"
    safe = min(by_space, by_egress)
    clears = "stairs and exits clear" if limited == "stairs" else "exits clear"
    note = (
        f"Floor space for {by_space:,} at {density:g} people per m²; "
        f"{clears} {by_egress:,} within {target / 60:.0f} min."
    )
    return Capacity(
        safe_people=round(safe, -1) if safe >= 100 else safe,
        by_space=by_space,
        by_egress=by_egress,
        limited_by=limited,
        usable_area_m2=round(area, 1),
        density_ppm2=density,
        target_evac_s=target,
        current_people=current,
        note=note,
    )


def compute_estimates(
    venue: Venue, registry: Registry, settings: Any, unit_costs: dict[str, Any] | None = None
) -> Estimates:
    """All organizer estimates for the venue as planned."""
    rat = ratios()
    ev = event_info(venue)
    n = venue.total_people()
    cap = capacity(venue, registry, settings)
    lines: list[EstimateLine] = []

    status: Literal["ok", "warn", "info"] = "ok" if n <= cap.safe_people else "warn"
    limit = {"exits": "exit width", "stairs": "stair width", "space": "floor space"}[cap.limited_by]
    lines.append(
        EstimateLine(
            key="capacity",
            label="Safe capacity",
            value=cap.safe_people,
            unit="people",
            detail=f"You plan {n:,}. Limited by {limit}. {cap.note}",
            source=rat["planning_density_ppm2"]["source"] + "; " + rat["egress_capacity"]["source"],
            url=rat["egress_capacity"]["url"],
            status=status,
        )
    )

    open_w = sum(e.width_m for f in venue.floors for e in f.exits if not e.blocked)
    ew = rat["exit_width_mm_per_person"]
    need_w = n * float(ew["value"]) / 1000
    lines.append(
        EstimateLine(
            key="exit_width",
            label="Exit width needed",
            value=round(need_w, 1),
            unit="m",
            detail=f"You have {open_w:.1f} m of open exits.",
            source=ew["source"],
            url=ew["url"],
            status="ok" if open_w >= need_w else "warn",
        )
    )

    st = rat["stewards"]
    high = bool(ev.get("alcohol"))
    per = st["per_person_high_risk"] if high else st["per_person"]
    stewards = max(2, math.ceil(n / per))
    lines.append(
        EstimateLine(
            key="stewards",
            label="Stewards",
            value=stewards,
            unit="people",
            detail=f"1 per {per} ({'alcohol served' if high else 'standard risk'}).",
            source=st["source"],
            url=st["url"],
        )
    )

    fa = rat["first_aid"]
    first_aid = max(
        fa["minimum"], fa["minimum"] + fa["per_extra_thousand"] * math.ceil(max(0, n - 1000) / 1000)
    )
    lines.append(
        EstimateLine(
            key="first_aid",
            label="First aiders",
            value=first_aid,
            unit="people",
            detail=f"{fa['minimum']} minimum, +{fa['per_extra_thousand']} per extra 1,000.",
            source=fa["source"],
            url=fa["url"],
        )
    )

    tl = rat["toilets"]
    dur = float(ev.get("duration_h") or 4)
    row_key = "under_6h" if dur < 6 else ("over_6h_alcohol" if ev.get("alcohol") else "over_6h")
    row = tl["rows"][row_key]
    span = ("under" if dur < 6 else "over") + " 6 h"
    if row_key.endswith("alcohol"):
        span += ", alcohol"
    women = n * float(tl["female_share"])
    men = n - women
    wc_f = math.ceil(women / row["female"]) if n else 0
    wc_m = math.ceil(men / row["male"]) if n else 0
    urinals = math.ceil(men / row["urinal"]) if n else 0
    accessible = max(int(tl["accessible_minimum"]), math.ceil((wc_f + wc_m) / 20)) if n else 0
    handwash = math.ceil((wc_f + wc_m + accessible) / tl["handwash_per_toilets"]) if n else 0
    lines.append(
        EstimateLine(
            key="toilets",
            label="Toilets",
            value=wc_f + wc_m,
            unit="units",
            detail=(
                f"{wc_f} for women, {wc_m} for men, plus {urinals} urinals, "
                f"{accessible} accessible, {handwash} hand-wash units ({span})."
            ),
            source=tl["source"],
            url=tl["url"],
        )
    )

    fence_m = 0.0
    if venue.mode == "outdoor":
        fence_m = float(geo.to_polygon(venue.floors[0].walkable).exterior.length) - open_w
        lines.append(
            EstimateLine(
                key="fence",
                label="Perimeter fencing",
                value=round(fence_m),
                unit="m",
                detail="Site outline minus the gates.",
                source="Measured from the plan",
            )
        )
    barrier_m = 0.0
    stage = next((o for f in venue.floors for o in f.obstacles if o.kind == "stage"), None)
    if stage is not None and ev["audience"] != "seated":  # barriers are for standing crowds
        have = sum(
            float(geo.to_polygon(o.polygon).length) / 2
            for f in venue.floors
            for o in f.obstacles
            if o.kind == "barrier"
        )
        sx0, sy0, sx1, sy1 = geo.to_polygon(stage.polygon).bounds
        wing = float(rat["front_barrier_wing_m"]["value"])
        barrier_m = max(sx1 - sx0, sy1 - sy0) + 2 * wing
        lines.append(
            EstimateLine(
                key="barrier",
                label="Front-of-stage barrier",
                value=round(barrier_m),
                unit="m",
                detail=f"The plan has {have:.0f} m of barrier.",
                source=rat["front_barrier_wing_m"]["source"],
                url=rat["front_barrier_wing_m"]["url"],
                status="ok" if have >= barrier_m * 0.9 else "warn",
            )
        )

    prices = {**rat["unit_costs_example"], **(unit_costs or {})}
    examples = not unit_costs
    days = max(1, math.ceil(dur / 24))
    shifts = max(1, math.ceil(dur / 8))
    budget = [
        BudgetLine(
            item="Stewards",
            quantity=stewards * shifts,
            unit="shift",
            unit_cost=prices["steward_shift"],
            total=0,
        ),
        BudgetLine(
            item="First aiders",
            quantity=first_aid * shifts,
            unit="shift",
            unit_cost=prices["first_aider_shift"],
            total=0,
        ),
        BudgetLine(
            item="Toilet units",
            quantity=(wc_f + wc_m) * days,
            unit="unit-day",
            unit_cost=prices["toilet_unit_day"],
            total=0,
        ),
        BudgetLine(
            item="Accessible toilets",
            quantity=accessible * days,
            unit="unit-day",
            unit_cost=prices["accessible_toilet_day"],
            total=0,
        ),
        BudgetLine(
            item="Hand-wash units",
            quantity=handwash * days,
            unit="unit-day",
            unit_cost=prices["handwash_unit_day"],
            total=0,
        ),
    ]
    if fence_m:
        budget.append(
            BudgetLine(
                item="Perimeter fencing",
                quantity=round(fence_m),
                unit="m",
                unit_cost=prices["fence_m"],
                total=0,
            )
        )
    if barrier_m:
        budget.append(
            BudgetLine(
                item="Crowd barrier",
                quantity=round(barrier_m),
                unit="m",
                unit_cost=prices["barrier_m"],
                total=0,
            )
        )
    for b in budget:
        b.total = round(b.quantity * b.unit_cost, 2)
    return Estimates(
        event=ev,
        capacity=cap,
        lines=lines,
        budget=budget,
        budget_total=round(sum(b.total for b in budget), 2),
        exit_width_open_m=round(open_w, 2),
        exit_width_needed_m=round(need_w, 2),
        currency=str(prices.get("currency", "USD")),
        prices_are_examples=examples,
    )
