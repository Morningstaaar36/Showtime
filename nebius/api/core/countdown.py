"""Latest safe time to start evacuating (section 10.8).

    T_latest = T_hazard − (T_pre_movement + RSET × SAFETY_FACTOR)

All times are seconds after the reference instant (event start for weather hazards,
the alarm for scenario hazards). ISO times are local to the venue, and only exist when the
hazard itself has a clock time (a forecast); an alarm-relative hazard has no clock time.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from api.core.extensions import HazardResult
from api.models import Countdown


def choose_hazard(hazards: list[HazardResult]) -> HazardResult | None:
    """The hazard the countdown uses: the earliest, compared only within one reference frame.

    Alarm-relative hazards (scenario or user-set times) and clock hazards (a forecast,
    counted from the event start) measure seconds from different instants, so they are
    never compared with each other. The alarm-relative one is the scenario under test.
    """
    timed = [h for h in hazards if h.t_hazard_s is not None]
    alarm = [h for h in timed if not h.t_hazard_iso]
    pool = alarm or timed
    if pool:
        return min(pool, key=lambda h: h.t_hazard_s or 0.0)
    return hazards[0] if hazards else None


def compute_countdown(
    hazard: HazardResult | None,
    rset_s: float | None,
    pre_movement_s: float,
    safety_factor: float,
    rset_source: str = "",
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
    # Only a hazard with a clock time gives a clock time to start by. A scenario or manual
    # hazard counts from the alarm, which has no fixed clock time, so adding its seconds to
    # the event start would print a wrong "start evacuating by" time.
    if hazard.t_hazard_iso:
        ref = datetime.fromisoformat(hazard.t_hazard_iso)
        base.t_latest_iso = (ref - timedelta(seconds=hazard.t_hazard_s - t_latest)).isoformat(
            timespec="minutes"
        )
    base.status = "too_late" if t_latest < 0 else "ok"
    return base
