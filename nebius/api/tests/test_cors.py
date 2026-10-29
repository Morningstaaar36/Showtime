"""Which web origins may call the API comes from settings (CORS_ORIGINS), not from code."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import FakeRunner
from api.app.main import create_app
from api.app.state import build_state
from api.tests.evidence_fakes import reset_engine, use_test_settings
from api.tests.http import api_client


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = use_test_settings(tmp_path, monkeypatch)
    settings = settings.model_copy(update={"cors_origins": "https://showtime.example"})
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    with api_client(create_app(state=state, settings=settings)) as c:
        yield c
    reset_engine()


def _preflight(c: TestClient, origin: str) -> str | None:
    r = c.options(
        "/api/v1/templates",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    return r.headers.get("access-control-allow-origin")


def test_cors_origins_come_from_settings(client: TestClient) -> None:
    assert _preflight(client, "https://showtime.example") == "https://showtime.example"
    assert _preflight(client, "http://localhost:5173") == "http://localhost:5173"  # WEB_ORIGIN
    assert _preflight(client, "https://evil.example") is None
