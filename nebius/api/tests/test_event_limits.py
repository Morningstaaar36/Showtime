"""The plausibility limits on AI-proposed scenarios come from the settings."""

from __future__ import annotations

from types import SimpleNamespace

from api.agents.limits import EventLimits, event_problems
from api.core.settings import Settings


def _ev(**kw: object) -> SimpleNamespace:
    return SimpleNamespace(**{"type": "surge", "extra_people": 0, "people": 0, "at_s": 0, **kw})


def test_limits_follow_the_settings() -> None:
    default = EventLimits.of(Settings(_env_file=None))
    assert event_problems([_ev(extra_people=400, at_s=60)], 1000, default) == []
    assert event_problems([_ev(extra_people=600)], 1000, default)  # more than half the crowd
    assert event_problems([_ev(at_s=700)], 1000, default)  # too late to matter
    strict = EventLimits.of(Settings(_env_file=None, surge_max_share=0.2, attack_max_start_s=30))
    assert len(event_problems([_ev(extra_people=400, at_s=60)], 1000, strict)) == 2
    assert event_problems([_ev(type="counterflow", people=40)], 60, default) == []  # floor of 50
