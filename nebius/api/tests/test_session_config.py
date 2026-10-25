"""Who proposes attacks and fixes: "model" by default and for an unknown mode, as documented."""

from __future__ import annotations

from pathlib import Path

from api.core.settings import Settings
from api.orchestrator.session import AGENT_MODES, session_config


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, llm_provider="fake", cache_dir=tmp_path)


def test_the_agents_mode_defaults_to_model(tmp_path: Path) -> None:
    assert session_config(_settings(tmp_path), None)["agents"] == "model"


def test_an_unknown_agents_mode_falls_back_to_model(tmp_path: Path) -> None:
    assert session_config(_settings(tmp_path), {"agents": "banana"})["agents"] == "model"


def test_every_listed_mode_is_kept(tmp_path: Path) -> None:
    for mode in AGENT_MODES:
        assert session_config(_settings(tmp_path), {"agents": mode})["agents"] == mode
