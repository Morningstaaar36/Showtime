"""Latest safe time to start evacuating (section 10.8).

    T_latest = T_hazard − (T_pre_movement + RSET × SAFETY_FACTOR)

All times are seconds after the reference instant (event start for weather hazards,
the alarm for scenario hazards). ISO times are local to the venue.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from api.core.extensions import HazardResult
from api.models import Countdown


def compute_countdown(
    hazard: HazardResult | None,
    rset_s: float | None,
    pre_movement_s: float,
    safety_factor: float,
    rset_source: str = "",
    event_start_iso: str | None = None,
) -> Countdown:
    """Apply the formula; never invents a time when an input is missing."""
    base = Countdown(
        status="unknown",
        pre_movement_s=pre_movement_s,
        safety_factor=safety_factor,
        rset_s=rset_s,
        rset_source=rset_source,
    )
    if hazard is None or hazard.t_hazard_s is None:
        base.status = "no_hazard"
        base.hazard_source = hazard.source if hazard else None
        base.hazard_explanation = hazard.explanation if hazard else "No hazard in forecast window."
        return base
    base.t_hazard_s = hazard.t_hazard_s
    base.t_hazard_iso = hazard.t_hazard_iso
    base.hazard_source = hazard.source
    base.hazard_explanation = hazard.explanation
    if rset_s is None:
        base.status = "unknown"
        return base
    t_latest = hazard.t_hazard_s - (pre_movement_s + rset_s * safety_factor)
    base.t_latest_s = round(t_latest, 1)
    ref = hazard.t_hazard_iso and datetime.fromisoformat(hazard.t_hazard_iso)
    if ref:
        base.t_latest_iso = (ref - timedelta(seconds=hazard.t_hazard_s - t_latest)).isoformat(
            timespec="minutes"
        )
    elif event_start_iso:
        base.t_latest_iso = (
            datetime.fromisoformat(event_start_iso) + timedelta(seconds=t_latest)
        ).isoformat(timespec="minutes")
    base.status = "too_late" if t_latest < 0 else "ok"
    return base
