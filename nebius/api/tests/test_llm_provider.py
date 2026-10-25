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
    return Settings(_env_file=None, **(base | kw))


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


class _Unauthorized(Exception):
    status_code = 401


class _Probe:
    """Stands in for AsyncOpenAI's auth-checked requests (models.list and get)."""

    def __init__(self, fail: Exception | None = None, key_info: dict[str, Any] | None = None):
        self.fail = fail
        self.key_info = key_info or {"data": {"limit_remaining": None}}
        self.calls: list[str] = []
        self.models = SimpleNamespace(list=self._list)

    async def _list(self) -> Any:
        self.calls.append("models")
        if self.fail:
            raise self.fail
        return SimpleNamespace(data=[SimpleNamespace(id="m")])

    async def get(self, path: str, cast_to: Any = None) -> Any:
        self.calls.append(path)
        if self.fail:
            raise self.fail
        return SimpleNamespace(json=lambda: self.key_info)


@pytest.mark.asyncio
async def test_health_reports_a_rejected_key_and_caches_the_probe(tmp_path: Path) -> None:
    secret = "sk-or-v1-0123456789abcdef"
    s = _settings(
        tmp_path,
        openai_compat_base_url="https://openrouter.ai/api/v1",
        openai_compat_api_key=secret,
    )
    probe = _Probe(fail=_Unauthorized(f"401 User not found for key {secret}"))
    c = LLMClient(s, transport=probe)
    h = await c.health()
    assert not h["ok"] and h["auth"] is False
    assert "rejected the API key" in h["detail"] and "OPENAI_COMPAT_API_KEY" in h["detail"]
    assert probe.calls == ["/key"]  # OpenRouter: the auth-checked endpoint, not the open list
    await c.health()
    assert probe.calls == ["/key"]  # cached: no second request
    assert secret not in json.dumps(h)


@pytest.mark.asyncio
async def test_health_ok_key_and_out_of_credit(tmp_path: Path) -> None:
    s = _settings(tmp_path, openai_compat_base_url="https://openrouter.ai/api/v1")
    ok = await LLMClient(s, transport=_Probe()).health()
    assert ok["ok"] and ok["auth"] is True
    broke = _Probe(key_info={"data": {"limit_remaining": 0}})
    h = await LLMClient(s, transport=broke).health()
    assert not h["ok"] and "no credit" in h["detail"]


@pytest.mark.asyncio
async def test_health_other_hosts_use_models_and_redact_errors(tmp_path: Path) -> None:
    secret = "sk-abcdef0123456789"
    s = _settings(tmp_path, openai_compat_api_key=secret)
    probe = _Probe(fail=RuntimeError(f"connection refused (Bearer {secret})"))
    h = await LLMClient(s, transport=probe).health()
    assert probe.calls == ["models"]
    assert not h["ok"] and secret not in h["detail"] and "***" in h["detail"]


@pytest.mark.asyncio
async def test_local_health_is_not_cached(tmp_path: Path) -> None:
    probe = _Probe()
    c = LLMClient(_settings(tmp_path, llm_provider="local"), transport=probe)
    assert (await c.health())["ok"]
    await c.health()
    assert probe.calls == ["models", "models"]


@pytest.mark.asyncio
async def test_spare_key_takes_over_when_the_first_is_out_of_credit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import openai

    class _NoCredit(_Transport):
        async def _create(self, **kwargs: Any) -> Any:
            raise RuntimeError("Error code: 402 - Insufficient credits")

    made: list[str] = []
    spare = _Transport()

    def factory(**kw: Any) -> Any:
        made.append(kw["api_key"])
        return spare

    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    c = LLMClient(
        _settings(tmp_path, openai_compat_api_key_fallback="sk-spare-123456", llm_fallback="none"),
        transport=_NoCredit(),
    )
    reply = await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert reply.text == "Hello." and made == ["sk-spare-123456"]
    assert c.api_key == "sk-spare-123456"
    assert "sk-spare-123456" not in c.redact("failed with sk-spare-123456")


@pytest.mark.asyncio
async def test_spare_key_is_not_used_for_other_errors(tmp_path: Path) -> None:
    class _Broken(_Transport):
        async def _create(self, **kwargs: Any) -> Any:
            raise RuntimeError("Error code: 500 - upstream exploded")

    c = LLMClient(
        _settings(tmp_path, openai_compat_api_key_fallback="sk-spare-123456", llm_fallback="none"),
        transport=_Broken(),
    )
    with pytest.raises(LLMError):
        await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert c.api_key == "k"


@pytest.mark.asyncio
async def test_health_switches_to_the_spare_key_when_the_first_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import openai

    spare = _Probe()
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: spare)
    s = _settings(
        tmp_path,
        openai_compat_base_url="https://openrouter.ai/api/v1",
        openai_compat_api_key_fallback="sk-spare-123456",
    )
    c = LLMClient(s, transport=_Probe(fail=_Unauthorized("401 API key expired")))
    out = await c.health()
    assert out["ok"] is True and "spare key" in out["detail"]
    assert c.api_key == "sk-spare-123456" and spare.calls == ["/key"]


@pytest.mark.asyncio
async def test_a_model_that_fails_at_the_provider_hands_over_to_the_fallback_model(
    tmp_path: Path,
) -> None:
    class _OneModelDown(_Transport):
        async def _create(self, **kwargs: Any) -> Any:
            if kwargs["model"] == "big-model":
                raise RuntimeError("Error code: 404 - Provider returned error")
            return await super()._create(**kwargs)

    t = _OneModelDown()
    c = LLMClient(
        _settings(tmp_path, model_fallback="other-model", llm_fallback="none"), transport=t
    )
    reply = await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert reply.text == "Hello." and t.sent["model"] == "other-model"

    # a quota error is not the model's fault: no model switch
    class _Quota(_Transport):
        async def _create(self, **kwargs: Any) -> Any:
            raise RuntimeError("429 Rate limit exceeded")

    q = LLMClient(
        _settings(tmp_path, model_fallback="other-model", llm_fallback="none"), transport=_Quota()
    )
    with pytest.raises(LLMError):
        await q.chat("fast", [{"role": "user", "content": "hi"}])


class _Failing(_Transport):
    """Fails with `exc` for the first `times` calls, then answers."""

    def __init__(self, exc: BaseException, times: int = 1) -> None:
        super().__init__()
        self.exc, self.left, self.tries = exc, times, 0

    async def _create(self, **kwargs: Any) -> Any:
        self.tries += 1
        if self.left > 0:
            self.left -= 1
            raise self.exc
        return await super()._create(**kwargs)


class _Status(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"Error code: {status}")
        self.status_code = status


def _with_local(c: LLMClient) -> _Transport:
    local = _Transport()
    c._local_client = local
    return local


@pytest.mark.asyncio
async def test_a_single_timeout_falls_back_once_without_pausing(tmp_path: Path) -> None:
    hosted = _Failing(TimeoutError("read timed out"), times=1)
    c = LLMClient(_settings(tmp_path), transport=hosted)
    _with_local(c)
    first = await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert first.usage.provider == "local-fallback"
    assert not c._primary_paused()
    second = await c.chat("fast", [{"role": "user", "content": "again"}])
    assert second.usage.provider == "openai"  # the hosted model is asked again


@pytest.mark.asyncio
async def test_a_client_error_does_not_pause(tmp_path: Path) -> None:
    c = LLMClient(_settings(tmp_path), transport=_Failing(_Status(400)))
    _with_local(c)
    await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert not c._primary_paused()


@pytest.mark.asyncio
async def test_a_rate_limit_pauses_and_the_pause_shows_in_health(tmp_path: Path) -> None:
    c = LLMClient(_settings(tmp_path), transport=_Failing(_Status(429), times=5))
    _with_local(c)
    await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert c._primary_paused()
    c._health_cache = (float("inf"), {"ok": True, "detail": "OPENROUTER: big-model"})
    h = await c.health()
    assert h["fallback"] is True and h["paused_until"] and "rate limit" in h["pause_reason"]


@pytest.mark.asyncio
async def test_repeated_server_errors_pause_but_one_does_not(tmp_path: Path) -> None:
    c = LLMClient(_settings(tmp_path), transport=_Failing(_Status(503), times=10))
    _with_local(c)
    for i in range(3):
        assert not c._primary_paused(), f"paused after {i} server errors"
        await c.chat("fast", [{"role": "user", "content": f"hi {i}"}])
    assert c._primary_paused()


@pytest.mark.asyncio
async def test_a_connection_failure_pauses(tmp_path: Path) -> None:
    c = LLMClient(_settings(tmp_path), transport=_Failing(ConnectionRefusedError("refused")))
    _with_local(c)
    await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert c._primary_paused()


@pytest.mark.asyncio
async def test_a_pause_expires(tmp_path: Path) -> None:
    hosted = _Failing(_Status(429), times=1)
    c = LLMClient(_settings(tmp_path), transport=hosted)
    _with_local(c)
    await c.chat("fast", [{"role": "user", "content": "hi"}])
    assert c._primary_paused()
    c._paused_until = 0.0  # the pause ran out
    reply = await c.chat("fast", [{"role": "user", "content": "later"}])
    assert reply.usage.provider == "openai"


@pytest.mark.parametrize("provider", ["openai", "nebius"])
def test_an_empty_model_id_fails_at_startup_naming_the_variable(
    tmp_path: Path, provider: str
) -> None:
    with pytest.raises(ValueError, match="MODEL_FAST"):
        _settings(tmp_path, llm_provider=provider, model_fast="  ")


def test_an_empty_local_model_id_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LOCAL_LLM_MODEL"):
        _settings(tmp_path, llm_provider="local", local_llm_model="")
    # the other roles may be empty: they fall back to MODEL_FAST
    assert _settings(tmp_path, model_main="").model_for("main") == "big-model"
