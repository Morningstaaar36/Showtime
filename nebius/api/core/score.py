"""Planning score: one number and a letter summarising a plan, with every part shown.

Five parts, each 0-100, weighted. The formula is fixed and printed with the score so it can be
checked; it summarises results computed elsewhere (simulation or instant estimate, estimates,
geometry checks). It is a planning aid, not a safety certification.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from api.models import RunMetrics

WEIGHTS = {"evac": 0.30, "density": 0.30, "capacity": 0.20, "exits": 0.10, "checks": 0.10}
GRADES = [(85, "A"), (70, "B"), (55, "C"), (40, "D"), (0, "F")]


class ScorePart(BaseModel):
    """One part of the score and how it was computed."""

    key: str
    label: str
    score: float
    weight: float
    detail: str


class Score(BaseModel):
    """Weighted planning score with its parts."""

    score: int
    grade: str
    parts: list[ScorePart]
    capped: str = ""
    basis: str = ""


def _lin(value: float, good: float, bad: float) -> float:
    """100 at `good` or better, 0 at `bad` or worse, linear between."""
    if good == bad:
        return 100.0 if value <= good else 0.0
    t = (value - good) / (bad - good)
    return round(100.0 * min(1.0, max(0.0, 1.0 - t)), 1)


def planning_score(
    metrics: RunMetrics,
    *,
    target_evac_s: float,
    warn_ppm2: float,
    danger_ppm2: float,
    people: int,
    safe_people: int,
    exit_width_have: float,
    exit_width_need: float,
    errors: int,
    warnings: int,
    basis: str = "",
) -> Score:
    """Score a plan from its results; the parts explain themselves."""
    p95 = metrics.evac_time_p95_s
    evac = _lin(p95, 0.6 * target_evac_s, 1.2 * target_evac_s) if p95 is not None else 0.0
    dens = _lin(metrics.peak_density_ppm2, warn_ppm2, danger_ppm2 + 1.0)
    load = people / max(safe_people, 1)
    cap = _lin(load, 0.8, 1.2)
    ratio = exit_width_have / exit_width_need if exit_width_need > 0 else 2.0
    exits = _lin(-ratio, -1.2, -0.8)
    checks = 0.0 if errors else max(0.0, 100.0 - 10.0 * warnings)
    p95_txt = f"{p95 / 60:.1f} min" if p95 is not None else "not everyone got out"
    parts = [
        ScorePart(key="evac", label="Evacuation time", score=evac, weight=WEIGHTS["evac"],
                  detail=f"95% out in {p95_txt}; target {target_evac_s / 60:.0f} min "
                  "(full marks at 60% of target, zero at 120%)."),
        ScorePart(key="density", label="Peak crowding", score=dens, weight=WEIGHTS["density"],
                  detail=f"Peak {metrics.peak_density_ppm2:.1f} people per m² (full marks up to "
                  f"{warn_ppm2:g}, zero at {danger_ppm2 + 1:g})."),
        ScorePart(key="capacity", label="Capacity margin", score=cap, weight=WEIGHTS["capacity"],
                  detail=f"{people:,} planned of {safe_people:,} safe ({load:.0%})."),
        ScorePart(key="exits", label="Exit width", score=exits, weight=WEIGHTS["exits"],
                  detail=f"{exit_width_have:.1f} m open for {exit_width_need:.1f} m needed."),
        ScorePart(key="checks", label="Plan checks", score=checks, weight=WEIGHTS["checks"],
                  detail=f"{errors} errors, {warnings} warnings."),
    ]  # fmt: skip
    total = sum(p.score * p.weight for p in parts)
    capped = ""
    left = metrics.agents_not_evacuated
    share = left / max(metrics.agents_total or people, 1)
    if left > 0 and share >= 0.01:
        total = min(total, 39.0)
        capped = f"Capped at F: {left:,} people ({share:.0%}) did not get out."
    elif left > 0:
        total = min(total, 54.0)
        capped = f"Capped at D: {left:,} people were still inside when the simulation stopped."
    elif errors:
        total = min(total, 54.0)
        capped = "Capped at D: the plan has errors to fix."
    grade = next(g for limit, g in GRADES if total >= limit)
    return Score(score=round(total), grade=grade, parts=parts, capped=capped, basis=basis)


def score_inputs(estimates: Any) -> dict[str, Any]:
    """The estimate values the score needs (from an `Estimates` model)."""
    return {
        "people": estimates.capacity.current_people,
        "safe_people": estimates.capacity.safe_people,
        "exit_width_have": estimates.exit_width_open_m,
        "exit_width_need": estimates.exit_width_needed_m,
    }
