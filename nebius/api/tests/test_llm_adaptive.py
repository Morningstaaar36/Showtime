"""Hosted models that reject JSON mode or extra request fields, or reason until the budget ends."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from api.adapters.llm import LLMClient
from api.core.settings import Settings


class Answer(BaseModel):
    word: str


class _Rejected(Exception):
    """Like openai.BadRequestError: carries the HTTP status."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class _Transport:
    """Replies from a script; each entry is an exception to raise or (content, reasoning)."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.sent: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.sent.append({k: v for k, v in kwargs.items()})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        content, reasoning = step
        msg = SimpleNamespace(content=content, reasoning_content=reasoning)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def _client(tmp_path: Path, transport: _Transport, **kw: Any) -> LLMClient:
    s = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_compat_base_url="https://llm.example/v1",
        openai_compat_api_key="k",
        model_fast="nvidia/nemotron-3-super-120b-a12b",
        price_fast_in=1.0,
        price_fast_out=1.0,
        llm_cache_mode="off",
        llm_fallback="none",
        cache_dir=tmp_path,
        **kw,
    )
    return LLMClient(s, transport=transport)


@pytest.mark.asyncio
async def test_model_without_json_mode_gets_json_by_prompt_and_is_remembered(
    tmp_path: Path,
) -> None:
    t = _Transport(
        [
            _Rejected("response_format json_schema is not supported for this model"),
            ('{"word": "ready"}', None),
            ('{"word": "again"}', None),
        ]
    )
    c = _client(tmp_path, t)
    reply = await c.chat("fast", [{"role": "user", "content": "Say ready."}], Answer)
    assert reply.parsed == Answer(word="ready")
    assert "response_format" in t.sent[0] and "response_format" not in t.sent[1]
    assert "Return only the JSON object" in t.sent[1]["messages"][0]["content"]
    await c.chat("fast", [{"role": "user", "content": "Again."}], Answer)
    assert "response_format" not in t.sent[2]  # remembered: no second rejection


@pytest.mark.asyncio
async def test_rejected_extra_fields_are_dropped(tmp_path: Path) -> None:
    t = _Transport([_Rejected("Unrecognized request argument: chat_template_kwargs"), ("ok", None)])
    c = _client(tmp_path, t, llm_extra_body='{"chat_template_kwargs": {"enable_thinking": false}}')
    reply = await c.chat("fast", [{"role": "user", "content": "Hi"}])
    assert reply.text == "ok"
    assert "extra_body" in t.sent[0] and "extra_body" not in t.sent[1]


@pytest.mark.asyncio
async def test_reply_that_is_only_reasoning_is_retried_with_more_room(tmp_path: Path) -> None:
    t = _Transport([("", "thinking about it at length"), ("ready", "short")])
    c = _client(tmp_path, t)
    reply = await c.chat("fast", [{"role": "user", "content": "Say ready."}], max_tokens=64)
    assert reply.text == "ready"
    assert t.sent[1]["max_tokens"] > t.sent[0]["max_tokens"]
    assert reply.usage.prompt_tokens == 200  # the wasted call still counts


@pytest.mark.asyncio
async def test_other_errors_are_not_retried(tmp_path: Path) -> None:
    t = _Transport([_Rejected("invalid api key", status_code=401)])
    c = _client(tmp_path, t)
    with pytest.raises(Exception, match="did not answer"):
        await c.chat("fast", [{"role": "user", "content": "Hi"}])
    assert len(t.sent) == 1
