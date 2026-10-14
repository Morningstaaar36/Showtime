"""Model escalation (N16): a `fast` answer still invalid after its repair is retried on `main`."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from api.adapters.llm import FakeLLM, LLMClient
from api.agents.base import AgentDef, AgentEnv, call_agent
from api.core.settings import Settings


class Answer(BaseModel):
    answer: str


PROBE = AgentDef(name="probe", role="fast", prompt_file="explainer.md", output_model=Answer)


class _Transport:
    """AsyncOpenAI stand-in: the fast model only writes prose, the main model writes JSON."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        model = str(kwargs["model"])
        self.calls.append(model)
        text = '{"answer": "ok"}' if model == "main-model" else "Sure! Here is my answer."
        msg = SimpleNamespace(content=text, reasoning_content=None)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def _client(tmp_path: Path, **kw: Any) -> tuple[LLMClient, _Transport]:
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
        **kw,
    )
    transport = _Transport()
    return LLMClient(settings, transport=transport), transport


@pytest.mark.asyncio
async def test_invalid_fast_answer_twice_escalates_once_to_main(tmp_path: Path) -> None:
    llm, transport = _client(tmp_path)
    events: list[tuple[str, dict[str, Any]]] = []
    env = AgentEnv(llm=llm, audit=False, emit=lambda t, p: events.append((t, p)))
    call = await call_agent(env, PROBE, {"context": "{}"}, "Question: why?")
    # the original answer and its repair on the fast model, then exactly one call on main
    assert transport.calls == ["fast-model", "fast-model", "main-model"]
    assert call.ok and call.output is not None and call.output.answer == "ok"
    assert call.escalated and call.model == "main-model"
    payload = next(p for t, p in events if t == "agent_call")
    assert payload["escalated"] is True and payload["ok"] is True
    assert payload["tokens_in"] == 30  # all three calls are counted


@pytest.mark.asyncio
async def test_escalation_can_be_turned_off(tmp_path: Path) -> None:
    llm, transport = _client(tmp_path, llm_escalate=False)
    call = await call_agent(AgentEnv(llm=llm, audit=False), PROBE, {"context": "{}"}, "Q")
    assert transport.calls == ["fast-model", "fast-model"]
    assert not call.ok and not call.escalated


@pytest.mark.asyncio
async def test_fake_llm_escalation_uses_the_main_role() -> None:
    llm = FakeLLM({"probe": ["not json", {"answer": "fine"}]})
    call = await call_agent(AgentEnv(llm=llm, audit=False), PROBE, {"context": "{}"}, "Q")
    assert call.ok and call.escalated and call.model == "fake-main"
    assert call.output is not None and call.output.answer == "fine"


@pytest.mark.asyncio
async def test_main_role_agents_are_not_escalated() -> None:
    main_probe = AgentDef(
        name="probe", role="main", prompt_file="explainer.md", output_model=Answer
    )
    llm = FakeLLM({"probe": ["not json", {"answer": "unused"}]})
    call = await call_agent(AgentEnv(llm=llm, audit=False), main_probe, {"context": "{}"}, "Q")
    assert not call.ok and not call.escalated
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_domain_problems_left_after_repair_also_escalate() -> None:
    script = [{"answer": "bad"}, {"answer": "bad again"}, {"answer": "good"}]
    llm = FakeLLM({"probe": script})
    call = await call_agent(
        AgentEnv(llm=llm, audit=False),
        PROBE,
        {"context": "{}"},
        "Q",
        validate=lambda o: [] if o.answer == "good" else ["say good"],
    )
    assert call.ok and call.escalated and call.output is not None
    assert call.output.answer == "good" and len(llm.calls) == 3


@pytest.mark.asyncio
async def test_a_kept_fast_answer_is_reported_as_the_fast_model() -> None:
    # main is no better (one problem each): the fast answer stays, all three calls are counted
    script = [{"answer": "bad"}, {"answer": "still bad"}, {"answer": "main bad"}]
    llm = FakeLLM({"probe": script})
    call = await call_agent(
        AgentEnv(llm=llm, audit=False),
        PROBE,
        {"context": "{}"},
        "Q",
        validate=lambda o: [] if o.answer == "good" else ["say good"],
    )
    assert not call.ok and call.escalated
    assert call.output is not None and call.output.answer == "still bad"
    assert call.model == "fake-fast"
    assert call.usage is not None and call.usage.prompt_tokens == 300
