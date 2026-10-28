"""How deep a test goes is data (api/data/test_modes.json), served to the page."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.core.session_modes import SessionModes, session_modes


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
