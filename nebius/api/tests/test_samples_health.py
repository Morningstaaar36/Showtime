"""Sample projects that fail to install no longer fail silently: /health says so."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import FakeRunner
from api.app.main import create_app
from api.app.state import build_state
from api.tests.evidence_fakes import reset_engine, use_test_settings


def test_a_failed_sample_install_shows_in_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = use_test_settings(tmp_path, monkeypatch)

    def broken(state: object) -> None:
        raise OSError("demo pack unreadable")

    monkeypatch.setattr("api.orchestrator.demos.install_demos", broken)
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    try:
        with TestClient(create_app(state=state, settings=settings)) as c:
            samples = c.get("/api/v1/health").json()["samples"]
        assert samples["ok"] is False and "demo pack unreadable" in samples["detail"]
    finally:
        reset_engine()
