"""LLM_PROVIDER=openai: any OpenAI-compatible API with MODEL_* ids, prices and its own label."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.adapters.llm import LLMClient, LLMError
from api.core.settings import Settings


class _Transport:
    """Stands in for AsyncOpenAI; records the request."""

    def __init__(self) -> None:
        self.sent: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.sent = kwargs
        msg = SimpleNamespace(content="Hello.", reasoning_content=None)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def _settings(tmp_path: Path, **kw: Any) -> Settings:
    base: dict[str, Any] = {
        "llm_provider": "openai",
        "openai_compat_base_url": "https://example.test/v1",
        "openai_compat_api_key": "k",
        "openai_compat_label": "openrouter",
        "model_fast": "big-model",
        "model_long": "",
        "model_main": "",
        "model_judge": "",
        "price_fast_in": 1.0,
        "price_fast_out": 2.0,
        "llm_cache_mode": "off",
        "cache_dir": tmp_path,
    }
    return Settings(**(base | kw))


def test_openai_provider_uses_cloud_models_and_label(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert s.model_for("judge") == "big-model"  # falls back to MODEL_FAST
    assert s.price_for("fast") == (1.0, 2.0)
    assert s.llm_label == "OPENROUTER"
    c = LLMClient(s)
    assert c.base_url == "https://example.test/v1" and c.api_key == "k"


@pytest.mark.asyncio
async def test_openai_provider_skips_nemotron_directive_and_costs(tmp_path: Path) -> None:
    t = _Transport()
    c = LLMClient(_settings(tmp_path), transport=t)
    reply = await c.chat("fast", [{"role": "system", "content": "Be brief."}])
    assert t.sent["messages"][0]["content"] == "Be brief."  # no "/no_think" for other models
    assert reply.usage.cost_usd == pytest.approx(0.002)
    t2 = _Transport()
    c2 = LLMClient(_settings(tmp_path, model_fast="nvidia/nemotron-nano-9b-v2"), transport=t2)
    await c2.chat("fast", [{"role": "system", "content": "Be brief."}])
    assert t2.sent["messages"][0]["content"].startswith("/no_think")


@pytest.mark.asyncio
async def test_openai_provider_health_needs_url_and_key(tmp_path: Path) -> None:
    h = await LLMClient(_settings(tmp_path, openai_compat_api_key="")).health()
    assert not h["ok"] and "OPENAI_COMPAT_API_KEY" in h["detail"]


def test_free_models_cost_nothing(tmp_path: Path) -> None:
    s = _settings(tmp_path, model_fast="nvidia/nemotron-3-super-120b-a12b:free")
    assert s.price_for("fast") == (0.0, 0.0)


@pytest.mark.asyncio
async def test_slow_gateway_hits_total_deadline(tmp_path: Path) -> None:
    class _Stalls(_Transport):
        async def _create(self, **kwargs: Any) -> Any:
            await asyncio.sleep(5)

    c = LLMClient(_settings(tmp_path, llm_timeout_s=0.05), transport=_Stalls())
    with pytest.raises(LLMError, match="did not answer"):
        await c.chat("fast", [{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_extra_body_is_sent_to_hosted_apis_only(tmp_path: Path) -> None:
    body = {"reasoning": {"enabled": False}}
    raw = json.dumps(body)
    t = _Transport()
    await LLMClient(_settings(tmp_path, llm_extra_body=raw), transport=t).chat(
        "fast", [{"role": "user", "content": "hi"}]
    )
    assert t.sent["extra_body"] == body
    t2 = _Transport()
    local = _settings(tmp_path, llm_provider="local", llm_extra_body=raw)
    await LLMClient(local, transport=t2).chat("fast", [{"role": "user", "content": "hi"}])
    assert "extra_body" not in t2.sent


def test_extra_body_must_be_a_json_object(tmp_path: Path) -> None:
    assert _settings(tmp_path, llm_extra_body="").llm_extra_body_dict == {}
    with pytest.raises(ValueError, match="JSON object"):
        _settings(tmp_path, llm_extra_body="reasoning off")


def test_answer_wrapped_in_schema_shape_is_unwrapped(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class Brief(BaseModel):
        title: str
        attendees: int

    c = LLMClient(_settings(tmp_path))
    text = '{"description": "x", "properties": {"title": "Concert", "attendees": 6000}}'
    assert c._parse(text, Brief).attendees == 6000


@pytest.mark.asyncio
async def test_hosted_failure_falls_back_to_the_local_model(tmp_path: Path) -> None:
    class _Quota(_Transport):
        async def _create(self, **kwargs: Any) -> Any:
            raise RuntimeError("429 Rate limit exceeded: free-models-per-day")

    local = _Transport()
    c = LLMClient(_settings(tmp_path), transport=_Quota())
    c._local_client = local
    reply = await c.chat("fast", [{"role": "system", "content": "Be brief."}])
    assert reply.text == "Hello." and reply.usage.provider == "local-fallback"
    assert local.sent["messages"][0]["content"].startswith("/no_think")
    assert c.fallback_reason == "daily free quota used up"
    local2 = _Transport()
    c._local_client = local2
    await c.chat("fast", [{"role": "user", "content": "again"}])
    assert local2.sent  # the hosted model is skipped while paused
    none = LLMClient(_settings(tmp_path, llm_fallback="none"), transport=_Quota())
    with pytest.raises(LLMError):
        await none.chat("fast", [{"role": "user", "content": "hi"}])
