"""How deep a test goes (api/data/test_modes.json): the session settings behind each choice the
page offers, and Autopilot's two depths. Served by GET /test_modes, so the page holds none."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODES_FILE = Path(__file__).resolve().parents[1] / "data" / "test_modes.json"


class SessionMode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z_]+$")
    minutes: int = Field(ge=1)  # about how long a local run takes, for the hint
    config: dict[str, Any]


class SessionModes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    default: str
    modes: list[SessionMode] = Field(min_length=1)
    autopilot: dict[Literal["quick", "thorough"], dict[str, Any]]

    @model_validator(mode="after")
    def _default_exists(self) -> SessionModes:
        if self.default not in {m.id for m in self.modes}:
            raise ValueError(f"default test mode '{self.default}' is not one of the modes")
        return self


@lru_cache(maxsize=1)
def session_modes() -> SessionModes:
    """The modes, validated once."""
    return SessionModes.model_validate(json.loads(MODES_FILE.read_text()))
