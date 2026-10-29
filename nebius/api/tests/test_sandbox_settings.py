"""Sandbox guards, pauses and timeouts come from settings (.env), not from constants in code."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from api.adapters.llm import FakeLLM, LLMClient
from api.adapters.sandbox import FakeRunner
from api.agents.red_team import script_attack
from api.app.state import build_runner, build_state
from api.core.settings import Settings
from api.core.templates import get_template
from api.tests.evidence_fakes import reset_engine, use_test_settings
from api.tests.http import api_client
from api.tests.test_redteam import _incidents


def test_a_script_run_carries_the_guards_from_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = use_test_settings(tmp_path, monkeypatch).model_copy(
        update={"script_min_speed_share": 0.25, "script_line_budget": 5000}
    )
    st = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    try:
        venue = get_template("school_wing")
        code = "def on_step(view, act):\n    pass\n"
        attack = script_attack("Script", code, _incidents()[0], "A1")
        with_script = st.runs.build_job(venue, tier=2, attack=attack)
        plain = st.runs.build_job(venue, tier=2)
        assert with_script.sim_settings["script_min_speed_share"] == 0.25
        assert with_script.sim_settings["script_line_budget"] == 5000
        assert "script_line_budget" not in plain.sim_settings  # other run ids do not change
    finally:
        reset_engine()


def test_container_process_limits_come_from_settings(tmp_path: Path) -> None:
    s = Settings(
        _env_file=None,
        sandbox_provider="docker",
        runs_dir=tmp_path,
        sim_pids_limit=128,
        code_pids_limit=32,
    )
    runner: Any = build_runner(s)
    assert runner.isolation.process_limit == 128 and runner.code_pids_limit == 32


async def test_the_pause_length_comes_from_settings(tmp_path: Path) -> None:
    s = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_compat_base_url="https://example.test/v1",
        openai_compat_api_key="k",
        model_fast="m",
        llm_cache_mode="off",
        cache_dir=tmp_path,
        llm_pause_s=42,
    )
    c = LLMClient(s)
    c._pause_primary("429 rate limit", "rate_limit")
    assert 40 <= c._paused_until - time.time() <= 42


def test_web_timeouts_are_sent_to_the_app_and_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    from api.app.main import create_app

    settings = use_test_settings(tmp_path, monkeypatch).model_copy(
        update={"web_read_timeout_s": 15.0}
    )
    st = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    try:
        with api_client(create_app(state=st, settings=settings)) as c:
            assert c.get("/api/v1/health").json()["client"]["read_timeout_s"] == 15.0
    finally:
        reset_engine()
    with pytest.raises(ValueError, match="WEB_WRITE_TIMEOUT_S"):
        Settings(_env_file=None, agent_step_timeout_s=300, web_write_timeout_s=60)
