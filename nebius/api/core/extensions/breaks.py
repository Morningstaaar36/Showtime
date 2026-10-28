"""When a run breaks the plan, and when it is at risk: one implementation for the server, the
severity score, the exporters and (through GET /settings) the web page. The numbers come from
the settings (`BreakRule.of`); nothing here is a threshold of its own."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.models import RunResult


@dataclass(frozen=True)
class BreakRule:
    """The break and at-risk thresholds, taken from the settings with `of`."""

    danger_ppm2: float
    min_s: float
    target_s: float | None
    safety_factor: float
    stuck_people: int
    stuck_fraction: float
    quick_min_out: float
    warn_ppm2: float
    at_risk_s: float

    @classmethod
    def of(cls, s: Any, target_s: float | None) -> BreakRule:
        """From the settings (api.core.settings.Settings) and the venue's evacuation target."""
        return cls(
            s.density_danger_ppm2,
            s.danger_min_duration_s,
            target_s,
            s.safety_factor,
            s.stuck_tolerance_people,
            s.stuck_tolerance_fraction,
            s.quick_min_out_fraction,
            s.density_warn_ppm2,
            s.at_risk_warning_s,
        )

    def stuck_tolerance(self, total: int) -> int:
        """People still inside at the end that are noise, not a failure."""
        return max(self.stuck_people, round(total * self.stuck_fraction))


def evac_estimate(r: RunResult) -> float | None:
    """95% evacuation time, or the extrapolated estimate for partial (Tier 2) runs."""
    m = r.metrics
    v = m.evac_time_p95_s if m.evac_time_p95_s is not None else m.extra.get("rset_extrapolated_s")
    return float(v) if v is not None else None


def break_reasons(r: RunResult, rule: BreakRule) -> list[str]:
    """Why a run counts as a break (contract: docs/API_CONTRACT.md)."""
    m = r.metrics
    out: list[str] = []
    if r.status in ("failed", "timeout"):
        return []
    rset = evac_estimate(r)
    if rule.target_s and rset is not None and rset * rule.safety_factor > rule.target_s:
        out.append(
            f"evacuation time {rset:.0f} s × safety factor {rule.safety_factor:g} exceeds the "
            f"{rule.target_s / 60:.0f} min target"
        )
    if m.time_above_danger_s >= rule.min_s:
        out.append(
            f"density at or above {rule.danger_ppm2:g} people per m² for "
            f"{m.time_above_danger_s:.0f} s"
        )
    trapped = int(m.extra.get("trapped", 0))
    if trapped:
        out.append(f"{trapped} people trapped with no open exit")
    tol = rule.stuck_tolerance(m.agents_total)
    if m.agents_not_evacuated > tol and r.tier != 2:
        out.append(f"{m.agents_not_evacuated} people still inside at the end")
    if r.tier == 2 and m.agents_not_evacuated > tol and m.evac_time_p95_s is None:
        frac = m.extra.get("evacuated_fraction")
        if frac is not None and frac < rule.quick_min_out:
            out.append(f"only {frac * 100:.0f}% out after {r.sim_time_s:.0f} s")
    return out


def at_risk(r: RunResult, rule: BreakRule) -> bool:
    """Holds, but close: the warning density was reached, or held longer than `at_risk_s`."""
    m = r.metrics
    return m.peak_density_ppm2 >= rule.warn_ppm2 or m.time_above_warning_s > rule.at_risk_s
