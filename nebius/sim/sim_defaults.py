"""Physical defaults for when a value is not in the run request (the simulator run on its own,
in tests or by hand). The API sends every value it owns (api/orchestrator/runs.py sim_settings);
api/tests/test_sim_defaults.py keeps the shared ones equal to api/core/settings.py."""

from __future__ import annotations

from typing import Any

SIM_DEFAULTS: dict[str, Any] = {
    "dt": 0.05,
    "frame_dt": 0.25,
    "agent_radius": 0.22,
    "agent_time_gap": 0.25,
    "model": "cfsm",
    "walk_speed_mean": 1.34,
    "specific_flow": 1.3,
    "stair_speed": 0.6,
    "stair_flow": 1.0,
    "density_warn_ppm2": 3.5,
    "density_danger_ppm2": 5.0,
    "squeeze_radius": 0.15,
    "clog_after_s": 4.0,
    "turbulence_pressure": 0.02,
    # replay frames per second, and fewer above this many people
    "frame_hz": 4.0,
    "frame_hz_big": 2.0,
    "big_crowd": 2500,
}


def setting(settings: dict[str, Any], key: str) -> Any:
    """A run setting, or its documented default."""
    return settings.get(key, SIM_DEFAULTS[key])
