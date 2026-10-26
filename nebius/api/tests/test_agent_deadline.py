"""An agent step has one total deadline: a hosted model that never answers cannot hold up a test
for retries × attempts × timeouts."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.adapters.llm import LLMClient
from api.agents.base import AgentEnv, AgentUnavailable, call_agent
from api.core.settings import Settings
from api.tests.test_escalation import PROBE


class _Hangs:
    """AsyncOpenAI stand-in that never answers."""

    def __init__(self) -> None:
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls += 1
        await asyncio.sleep(3600)


def _llm(tmp_path: Path, **kw: Any) -> tuple[LLMClient, _Hangs]:
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_compat_base_url="https://example.test/v1",
        openai_compat_api_key="k",
        model_fast="fast-model",
        model_main="main-model",
        llm_cache_mode="off",
        llm_fallback="none",
        cache_dir=tmp_path,
        llm_timeout_s=30.0,  # one call alone would wait 30 s
        **kw,
    )
    t = _Hangs()
    return LLMClient(settings, transport=t), t


@pytest.mark.asyncio
async def test_a_hanging_model_is_cut_off_at_the_step_deadline(tmp_path: Path) -> None:
    llm, hangs = _llm(tmp_path, agent_step_timeout_s=0.3)
    t0 = time.perf_counter()
    with pytest.raises(AgentUnavailable, match=r"0\.3 s"):
        await call_agent(AgentEnv(llm=llm, audit=False), PROBE, {}, "hi")
    assert time.perf_counter() - t0 < 2.0
    assert hangs.calls == 1


def test_the_step_deadline_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _llm(tmp_path, agent_step_timeout_s=0)
