"""How deep a test goes is data (api/data/test_modes.json), served to the page."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.core.session_modes import SessionModes, session_modes
from api.tests.http import api_client


def test_the_modes_load_and_include_the_default() -> None:
    m = session_modes()
    ids = [x.id for x in m.modes]
    assert m.default in ids and len(ids) == len(set(ids))
    assert set(m.autopilot) == {"quick", "thorough"}
    assert all(x.config.get("max_rounds", 0) >= 1 for x in m.modes)


def test_a_default_that_is_not_a_mode_is_refused() -> None:
    with pytest.raises(ValidationError):
        SessionModes.model_validate(
            {"default": "nope", "modes": [{"id": "a", "minutes": 1, "config": {}}], "autopilot": {}}
        )


def test_the_page_gets_the_editor_defaults_targets_and_speeds(tmp_path: object) -> None:
    from pathlib import Path

    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app
    from api.app.state import build_state
    from api.core.scenarios import SPEED_PRESETS
    from api.core.settings import Settings

    s = Settings(_env_file=None, cache_dir=Path(str(tmp_path)), runs_dir=Path(str(tmp_path)) / "r")
    st = build_state(s, llm=FakeLLM({}, s), runner=FakeRunner(s.runs_dir))
    with api_client(create_app(state=st, settings=s)) as c:
        eff = c.get("/api/v1/settings").json()["effective"]
        modes = c.get("/api/v1/test_modes").json()
    assert eff["editor"]["exit_width_m"] == s.new_exit_width_m
    assert eff["target_evac_indoor_s"] == s.target_evac_indoor_s
    assert eff["speed_presets"] == SPEED_PRESETS
    assert modes["default"] in [m["id"] for m in modes["modes"]]
