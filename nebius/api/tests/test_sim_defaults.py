"""The simulator's own defaults (for runs without a value) match the API's settings."""

from __future__ import annotations

import importlib.util

from api.core.settings import ROOT_DIR, Settings

SHARED = {  # simulator key -> setting
    "agent_radius": "agent_radius",
    "agent_time_gap": "agent_time_gap",
    "walk_speed_mean": "walk_speed_mean",
    "specific_flow": "specific_flow",
    "stair_speed": "stair_speed",
    "stair_flow": "stair_flow",
    "density_warn_ppm2": "density_warn_ppm2",
    "density_danger_ppm2": "density_danger_ppm2",
    "dt": "sim_dt_s",
}


def test_simulator_defaults_match_the_settings() -> None:
    spec = importlib.util.spec_from_file_location(
        "sim_defaults", ROOT_DIR / "sim" / "sim_defaults.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    s = Settings(_env_file=None)
    for key, name in SHARED.items():
        assert mod.SIM_DEFAULTS[key] == getattr(s, name), key
