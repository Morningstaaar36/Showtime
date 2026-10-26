"""When the hosted model is paused (a used-up daily quota, a rate limit) and no local model is
running, the badge says the AI is unavailable and every "the model isn't answering" error says
why and what to do: test Offline, or wait until the pause ends. It never tells someone on a
hosted provider only to start a local model (step 7, flow 8)."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.adapters.llm import LLMClient
from api.tests.test_llm_provider import _settings


class _Local:
    """A local llama-server that is running (or not)."""

    def __init__(self, up: bool) -> None:
        self.up = up
        self.models = SimpleNamespace(list=self._list)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _list(self) -> Any:
        if not self.up:
            raise ConnectionRefusedError("refused")
        return SimpleNamespace(data=[SimpleNamespace(id="nemotron-nano")])

    async def _create(self, **kw: Any) -> Any:
        raise ConnectionRefusedError("refused")


def _paused(tmp_path: Path, local_up: bool) -> LLMClient:
    c = LLMClient(_settings(tmp_path))
    c._local_client = _Local(local_up)
    c._health_cache = (float("inf"), {"ok": True, "detail": "OPENROUTER: big-model"})
    c._pause_primary("429 Rate limit exceeded: free-models-per-day")
    return c


@pytest.mark.asyncio
async def test_a_pause_with_no_local_model_is_reported_as_unavailable(tmp_path: Path) -> None:
    h = await _paused(tmp_path, local_up=False).health()
    assert h["ok"] is False and h["fallback"] is True
    assert "daily free quota used up" in h["detail"] and "local model is not running" in h["detail"]


@pytest.mark.asyncio
async def test_a_pause_with_a_local_model_falls_back(tmp_path: Path) -> None:
    h = await _paused(tmp_path, local_up=True).health()
    assert h["ok"] is True and h["fallback"] is True and "using the local model" in h["detail"]


def test_the_hint_names_the_pause_and_offline_mode(tmp_path: Path) -> None:
    c = _paused(tmp_path, local_up=False)
    hint = c.unavailable_hint()
    assert "daily free quota used up" in hint and "Offline" in hint
    assert time.strftime("%H:%M", time.gmtime(c._paused_until)) in hint
    plain = LLMClient(_settings(tmp_path))  # hosted, not paused: no local-model advice
    assert "llm-up" not in plain.unavailable_hint() and "Offline" in plain.unavailable_hint()
    local = LLMClient(_settings(tmp_path, llm_provider="local"))
    assert "make llm-up" in local.unavailable_hint()


def test_the_edit_endpoint_gives_that_hint(tmp_path: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app
    from api.app.state import build_state
    from api.tests.evidence_fakes import reset_engine, use_test_settings

    s = use_test_settings(tmp_path, monkeypatch)
    llm = _paused(tmp_path, local_up=False)
    st = build_state(s, llm=llm, runner=FakeRunner(s.runs_dir))
    try:
        with TestClient(create_app(state=st, settings=s)) as c:
            pid = st.projects.create("Hall", template_id="school_wing").id
            r = c.post(
                f"/api/v1/projects/{pid}/edit", json={"text": "add a 2 m exit on the east wall"}
            )
        assert r.status_code == 503
        body = r.json()
        assert body["code"] == "llm_unavailable"
        assert "Offline" in body["hint"] and "daily free quota used up" in body["hint"]
    finally:
        reset_engine()


def test_a_rejected_key_is_named_in_the_hint(tmp_path: Path) -> None:
    c = LLMClient(_settings(tmp_path))
    detail = "OPENROUTER rejected the API key (HTTP 401). Set a valid OPENAI_COMPAT_API_KEY in .env and restart."
    c._health_cache = (float("inf"), {"ok": False, "auth": False, "detail": detail})
    assert c.unavailable_hint().startswith(detail)
    assert "Offline" in c.unavailable_hint()
