"""A service that is not configured is a clear state, never a crash: the app starts, uses what
works (Docker, the incident dataset) and says so (step 6d)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.app.main import create_app
from api.app.state import build_runner, build_state
from api.core.settings import Settings
from api.tests.evidence_fakes import reset_engine, use_test_settings


def test_an_unconfigured_sandbox_falls_back_and_says_why(tmp_path: Path) -> None:
    s = Settings(
        _env_file=None,
        sandbox_provider="nebius",
        nebius_api_key="",
        runs_dir=tmp_path,
        cache_dir=tmp_path,
    )
    runner = build_runner(s)
    assert runner.provider == "docker"
    assert runner.fallback_reason == (
        "Nebius Sandboxes is not configured: set NEBIUS_API_KEY in .env. Using Local Docker."
    )


def test_health_names_what_is_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = use_test_settings(tmp_path, monkeypatch).model_copy(
        update={
            "sandbox_provider": "nebius",
            "nebius_api_key": "",
            "search_provider": "tavily",
            "tavily_api_key": "",
        }
    )
    st = build_state(s, llm=FakeLLM({}, s))
    try:
        with TestClient(create_app(state=st, settings=s)) as c:
            p = c.get("/api/v1/health").json()["providers"]
        assert p["sandbox"]["fallback"].startswith("Nebius Sandboxes is not configured")
        assert p["sandbox"]["provider"] == "docker"  # what runs, not what was asked for
        assert (
            p["search"]["not_configured"]
            == "Tavily web search is not configured: set TAVILY_API_KEY in .env."
        )
        assert p["search"]["ok"] is True and p["search"]["live"] is False  # off, not broken
    finally:
        reset_engine()


def test_a_fallback_that_is_itself_unconfigured_is_refused_at_startup() -> None:
    with pytest.raises(ValueError, match="SANDBOX_FALLBACK"):
        Settings(_env_file=None, sandbox_fallback="nebius", nebius_api_key="")
