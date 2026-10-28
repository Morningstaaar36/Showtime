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


def test_the_simulator_and_the_instant_estimate_share_their_rules() -> None:
    """Values the sim image can't import from the API are kept equal here."""
    import re

    from api.core.geometry import EXIT_WALL_TOLERANCE_M
    from api.core.tier1 import KIND_SPEED

    engine = (ROOT_DIR / "sim" / "plugins" / "engine_jupedsim.py").read_text()
    build = (ROOT_DIR / "sim" / "jps_build.py").read_text()
    sim_speeds = re.search(r"^KIND_SPEED = (\{[^}]*\})", engine, re.M)
    sim_tol = re.search(r"^WALL_TOLERANCE_M = ([\d.]+)", build, re.M)
    assert sim_speeds and sim_tol
    assert eval(sim_speeds.group(1)) == KIND_SPEED
    assert float(sim_tol.group(1)) == EXIT_WALL_TOLERANCE_M
