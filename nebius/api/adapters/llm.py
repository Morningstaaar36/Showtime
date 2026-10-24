"""LLM provider: any OpenAI-compatible endpoint (local llama.cpp, Nebius Token Factory or other).

- Roles (fast/long/main/judge) map to model ids from settings; nothing is hardcoded.
- Structured output: JSON schema via `response_format` when supported, otherwise
  "return only JSON" + extraction. Always validated with Pydantic; one repair call with
  the validation error; then the caller's safe default.
- Record/replay cache keyed by (provider, model, messages, schema, temperature).
- Token usage from the response `usage` field; cost = tokens × price per 1M (0 locally).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from api.adapters.cache import DiskCache, cache_key
from api.core.settings import LlmRole, Settings
from api.models import Usage

log = logging.getLogger("showtime.llm")
T = TypeVar("T", bound=BaseModel)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# key-shaped tokens (sk-..., sk-or-v1-..., Bearer ...) masked in errors shown to people
KEY_RE = re.compile(r"\b(sk-|Bearer\s+)[A-Za-z0-9_\-.*]{6,}")
# errors that mean "this key can't be used now" (out of credit, quota, rate limit, revoked)
QUOTA_RE = re.compile(
    r"\b(401|402|429)\b|credit|quota|rate.?limit|per.?day|insufficient|unauthori[sz]ed", re.I
)
HEALTH_TTL_OK_S = 300.0  # a working key is re-checked every 5 minutes
HEALTH_TTL_FAIL_S = 60.0  # a failing one every minute (fixing .env needs a restart anyway)


class LLMError(Exception):
    """The model could not be reached or answered unusably."""


class LLMOutputError(LLMError):
    """Output failed validation even after one repair attempt."""

    def __init__(self, message: str, raw: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.raw = raw
        self.usage = usage  # tokens spent on the invalid answers (still billed)


class LLMReplayMiss(LLMError):
    """Replay mode and no recorded response for this request."""


class BudgetExceeded(Exception):
    """A session token budget ran out; the orchestrator finishes gracefully."""


@dataclass
class Budget:
    """Per-session token budget shared by all agents in the session."""

    max_tokens: int
    used: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_role: dict[str, int] = field(default_factory=dict)

    def check(self) -> None:
        """Raise BudgetExceeded when no tokens are left."""
        if self.used >= self.max_tokens:
            raise BudgetExceeded(f"Token budget of {self.max_tokens:,} used.")

    def add(self, usage: Usage) -> None:
        """Account for one call."""
        n = usage.prompt_tokens + usage.completion_tokens
        self.used += n
        self.cost_usd += usage.cost_usd
        self.calls += 1
        self.by_role[usage.role] = self.by_role.get(usage.role, 0) + n


@dataclass
class LLMReply:
    """Parsed object (when a schema was given) or text, plus usage."""

    text: str
    parsed: Any | None
    usage: Usage
    repaired: bool = False
    reasoning: str = ""


def extract_json(text: str) -> str:
    """First balanced JSON object or array in `text` (ignores code fences and prose)."""
    text = THINK_RE.sub("", text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in the reply")
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unterminated JSON in the reply")


def _schema_for(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


class LLMClient:
    """Provider-agnostic chat client used by every agent."""

    def __init__(
        self,
        settings: Settings,
        on_usage: Callable[[Usage], None] | None = None,
        transport: Any | None = None,
    ) -> None:
        self.settings = settings
        self.provider: Literal["local", "nebius", "openai", "fake"] = settings.llm_provider
        self.cache = DiskCache(settings.cache_dir / "llm")
        self.on_usage = on_usage
        self._client = transport
        self.calls = 0
        self.lock = asyncio.Lock() if settings.llm_provider == "local" else None
        self._local_client: Any = None
        self._local_lock = asyncio.Lock()
        self._paused_until = 0.0
        self.fallback_reason: str | None = None
        # request features a hosted model rejected once ("schema", "extra"), per model:
        # later calls leave them out instead of failing again
        self._unsupported: set[tuple[str, str]] = set()
        self._on_spare_key = False  # switched to OPENAI_COMPAT_API_KEY_FALLBACK
        self._health_cache: tuple[float, dict[str, Any]] | None = None

    @property
    def base_url(self) -> str:
        """Endpoint for the active provider."""
        if self.provider == "nebius":
            return self.settings.nebius_base_url
        if self.provider == "openai":
            return self.settings.openai_compat_base_url
        return self.settings.local_llm_base_url

    @property
    def extra_body(self) -> dict[str, Any]:
        """Provider-specific request fields (LLM_EXTRA_BODY); never sent to llama-server."""
        return self.settings.llm_extra_body_dict if self.provider != "local" else {}

    @property
    def api_key(self) -> str:
        """Key for the active provider (llama-server needs none)."""
        if self.provider == "openai" and self._on_spare_key:
            return self.settings.openai_compat_api_key_fallback
        return {
            "nebius": self.settings.nebius_api_key,
            "openai": self.settings.openai_compat_api_key,
        }.get(self.provider, "local")

    def _switch_to_spare_key(self, reason: str) -> bool:
        """Move to the spare key when the first one ran out of credit or hit a quota."""
        spare = self.settings.openai_compat_api_key_fallback
        if self.provider != "openai" or self._on_spare_key or not spare:
            return False
        if not QUOTA_RE.search(reason):
            return False
        self._on_spare_key = True
        self._client = None
        self._health_cache = None
        log.warning(
            "first API key unavailable (%s); using the spare key", self.redact(reason)[:120]
        )
        return True

    @property
    def where(self) -> str:
        """Human name of the active endpoint, for errors."""
        return {
            "local": "local llama-server",
            "nebius": "Nebius Token Factory",
            "openai": f"{self.settings.llm_label} API ({self.settings.openai_compat_base_url})",
        }.get(self.provider, self.provider)

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "missing",
                timeout=self.settings.llm_timeout_s,
                max_retries=2,
            )
        return self._client

    def model_for(self, role: LlmRole) -> str:
        """Model id for a role."""
        return self.settings.model_for(role)

    def _directive(self, reasoning: bool, model: str = "") -> str:
        # Nemotron Nano 9B v2: "/think" or "/no_think" in the system prompt (model card).
        # Other model families would read it as noise, so it is sent to Nemotron only.
        if self.provider == "local" or "nemotron" in model.lower():
            return "/think" if reasoning else "/no_think"
        return ""

    async def health(self) -> dict[str, Any]:
        """Is the provider usable? Local: ping /models. Hosted: an auth-checked request.

        Some gateways (OpenRouter) list their models without a key, so a model listing alone
        reports an expired or revoked key as healthy. Hosted providers are therefore probed with
        a request that needs a valid key (OpenRouter: `GET /key`, others: `GET /models`), and
        the answer is cached for a few minutes so the badge does not hit the API on every poll.
        The detail never contains key material.
        """
        if self.provider == "fake":
            return {"ok": True, "detail": "Fake LLM (tests)"}
        if self.provider == "nebius" and not self.settings.nebius_api_key:
            return {"ok": False, "detail": "NEBIUS_API_KEY is not set."}
        if self.provider == "openai" and not (
            self.settings.openai_compat_base_url and self.settings.openai_compat_api_key
        ):
            return {
                "ok": False,
                "detail": "OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_API_KEY must be set.",
            }
        if self.provider == "local":
            return await self._local_health()
        now = time.monotonic()
        if self._health_cache is not None and now < self._health_cache[0]:
            out = dict(self._health_cache[1])
        else:
            out = await self._hosted_health()
            # an expired, revoked or empty first key: the spare key takes over here too, so the
            # badge (and the first-run checklist) tells the truth about what calls will use
            if not out["ok"] and self._switch_to_spare_key(str(out.get("detail", ""))):
                out = await self._hosted_health()
                if out["ok"]:
                    out["detail"] = f"{out['detail']} (spare key)"
            ttl = HEALTH_TTL_OK_S if out["ok"] else HEALTH_TTL_FAIL_S
            self._health_cache = (now + ttl, out)
            out = dict(out)
        if out["ok"] and self._primary_paused():
            return {
                "ok": True,
                "fallback": True,
                "detail": f"{self.settings.llm_label} paused ({self.fallback_reason}); "
                "using the local model",
            }
        return out

    async def _local_health(self) -> dict[str, Any]:
        try:
            models = await asyncio.wait_for(self._get_client().models.list(), timeout=5)
        except Exception as exc:
            return {
                "ok": False,
                "detail": f"{self.where} is not reachable ({type(exc).__name__}: "
                f"{self.redact(str(exc))[:160]}). Start it with: make llm-up",
            }
        ids = [m.id for m in getattr(models, "data", [])][:5]
        return {"ok": True, "detail": f"{self.provider}: {', '.join(ids) or 'ready'}"}

    async def _hosted_health(self) -> dict[str, Any]:
        label = self.settings.llm_label
        client = self._get_client()
        openrouter = "openrouter.ai" in self.base_url.lower()
        try:
            if openrouter:
                import httpx

                resp = await asyncio.wait_for(client.get("/key", cast_to=httpx.Response), 5)
                info = _json_or_empty(resp).get("data") or {}
                left = info.get("limit_remaining") if isinstance(info, dict) else None
                if isinstance(left, int | float) and left <= 0:
                    return {
                        "ok": False,
                        "auth": True,
                        "detail": f"{label}: the API key has no credit left.",
                    }
            else:
                await asyncio.wait_for(client.models.list(), timeout=5)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in (401, 403):
                env = "NEBIUS_API_KEY" if self.provider == "nebius" else "OPENAI_COMPAT_API_KEY"
                return {
                    "ok": False,
                    "auth": False,
                    "detail": f"{label} rejected the API key (HTTP {status}). "
                    f"Set a valid {env} in .env and restart.",
                }
            if status == 402:
                return {"ok": False, "auth": True, "detail": f"{label}: out of credit (HTTP 402)."}
            return {
                "ok": False,
                "detail": f"{self.where} is not reachable ({type(exc).__name__}: "
                f"{self.redact(str(exc))[:160]}).",
            }
        return {"ok": True, "auth": True, "detail": f"{label}: {self.model_for('main')}"}

    def redact(self, text: str) -> str:
        """`text` with the configured keys and anything key-shaped masked."""
        for key in (
            self.settings.nebius_api_key,
            self.settings.openai_compat_api_key,
            self.settings.openai_compat_api_key_fallback,
        ):
            if key and len(key) >= 6:
                text = text.replace(key, "***")
        return KEY_RE.sub(lambda m: m.group(1) + "***", text)

    async def chat(
        self,
        role: LlmRole,
        messages: list[dict[str, str]],
        schema: type[T] | None = None,
        *,
        agent: str = "",
        prompt_version: str = "",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        reasoning: bool = False,
        budget: Budget | None = None,
    ) -> LLMReply:
        """One chat call with validation, one repair retry, caching and accounting."""
        if budget is not None:
            budget.check()
        model = self.model_for(role)
        msgs = self._with_directive(messages, reasoning, schema, model)
        reply = await self._call(
            role, model, msgs, schema, agent, prompt_version, temperature, max_tokens, budget
        )
        if schema is None:
            return reply
        try:
            reply.parsed = self._parse(reply.text, schema)
            return reply
        except (ValueError, ValidationError) as exc:
            err = _short_error(exc)
            log.info("agent %s: invalid output, repairing (%s)", agent, err)
        repair = [
            *msgs,
            {"role": "assistant", "content": reply.text[:6000]},
            {
                "role": "user",
                "content": (
                    "Your reply was not valid. Problem: " + err + "\nReturn only the corrected "
                    "JSON object that matches the schema. No prose."
                ),
            },
        ]
        fixed = await self._call(
            role, model, repair, schema, agent, prompt_version, 0.0, max_tokens, budget
        )
        fixed.repaired = True
        fixed.usage.prompt_tokens += reply.usage.prompt_tokens
        fixed.usage.completion_tokens += reply.usage.completion_tokens
        fixed.usage.cost_usd += reply.usage.cost_usd
        try:
            fixed.parsed = self._parse(fixed.text, schema)
        except (ValueError, ValidationError) as exc:
            raise LLMOutputError(
                f"{agent}: output invalid after repair: {_short_error(exc)}",
                fixed.text,
                fixed.usage,
            ) from exc
        return fixed

    def _with_directive(
        self,
        messages: list[dict[str, str]],
        reasoning: bool,
        schema: type[BaseModel] | None,
        model: str = "",
    ) -> list[dict[str, str]]:
        msgs = [dict(m) for m in messages]
        directive = self._directive(reasoning, model)
        extra = ""
        if schema is not None and not self.settings.llm_supports_json_schema:
            extra = (
                "\nReturn only the JSON object with your answer, no prose. Its fields are "
                "described by this JSON schema (fill in values; do not repeat the schema):\n"
                + json.dumps(_schema_for(schema))
            )
        head = f"{directive}\n" if directive else ""
        if msgs and msgs[0]["role"] == "system":
            msgs[0]["content"] = f"{head}{msgs[0]['content']}{extra}"
        elif directive or extra:
            msgs.insert(0, {"role": "system", "content": f"{directive}{extra}".strip()})
        return msgs

    def _parse(self, text: str, schema: type[T]) -> T:
        raw = extract_json(text)
        try:
            return schema.model_validate_json(raw)
        except ValidationError:
            # Some models answer with the schema's shape: {"properties": {...the answer...}}
            data = json.loads(raw)
            inner = data.get("properties") if isinstance(data, dict) else None
            if isinstance(inner, dict) and not any(
                isinstance(v, dict) and "type" in v for v in inner.values()
            ):
                return schema.model_validate(inner)
            raise

    async def _call(
        self,
        role: LlmRole,
        model: str,
        msgs: list[dict[str, str]],
        schema: type[BaseModel] | None,
        agent: str,
        prompt_version: str,
        temperature: float,
        max_tokens: int,
        budget: Budget | None,
    ) -> LLMReply:
        mode = self.settings.llm_cache_mode
        parts: list[Any] = [
            self.provider,
            model,
            msgs,
            _schema_for(schema) if schema else None,  # schema content, not just name
            temperature,
            prompt_version,
        ]
        if self.extra_body:  # only when set, so existing recordings stay valid
            parts.append(self.extra_body)
        key = cache_key(*parts)
        if mode in ("replay", "record_replay"):
            hit = self.cache.get(key)
            if hit is not None:
                usage = Usage.model_validate({**hit["usage"], "cached": True, "cost_usd": 0.0})
                self._account(usage, budget)
                return LLMReply(
                    text=hit["text"], parsed=None, usage=usage, reasoning=hit.get("reasoning", "")
                )
            if mode == "replay":
                raise LLMReplayMiss(f"no recorded response for {agent} ({key[:12]})")
        if self.provider == "fake":
            raise LLMError("Fake provider: no live calls (use FakeLLM)")
        text, reasoning, usage = await self._live(
            role, model, msgs, schema, temperature, max_tokens
        )
        if mode in ("record", "record_replay") and usage.provider == self.provider:  # not fallbacks
            self.cache.put(
                key,
                {
                    "text": text,
                    "reasoning": reasoning,
                    "usage": usage.model_dump(),
                    "agent": agent,
                    "model": model,
                    "prompt_version": prompt_version,
                    "ts": time.time(),
                },
            )
        self._account(usage, budget)
        return LLMReply(text=text, parsed=None, usage=usage, reasoning=reasoning)

    async def _live(
        self,
        role: LlmRole,
        model: str,
        msgs: list[dict[str, str]],
        schema: type[BaseModel] | None,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, str, Usage]:
        if self.provider != "local" and self._primary_paused():
            return await self._fallback(role, msgs, schema, temperature, max_tokens)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.extra_body and ("extra", model) not in self._unsupported:
            kwargs["extra_body"] = self.extra_body
        if (
            schema is not None
            and self.settings.llm_supports_json_schema
            and ("schema", model) not in self._unsupported
        ):
            kwargs["response_format"] = _response_format(schema)
        elif schema is not None and self.settings.llm_supports_json_schema:
            kwargs["messages"] = _with_json_instruction(msgs, schema)
        try:
            return await self._adaptive(kwargs, role, model, schema)
        except LLMError as exc:
            if self._switch_to_spare_key(str(exc)):
                return await self._live(role, model, msgs, schema, temperature, max_tokens)
            spare_model = self.settings.model_fallback
            if (
                spare_model
                and spare_model != model
                and self.provider != "local"
                and not QUOTA_RE.search(str(exc))
            ):
                # the role's model failed at the provider (not a quota): one try on the other model
                log.warning(
                    "%s failed (%s); trying %s", model, self.redact(str(exc))[:100], spare_model
                )
                return await self._live(role, spare_model, msgs, schema, temperature, max_tokens)
            if self.provider == "local" or self.settings.llm_fallback != "local":
                raise
            self._pause_primary(str(exc))
            return await self._fallback(role, msgs, schema, temperature, max_tokens)

    async def _adaptive(
        self, kwargs: dict[str, Any], role: LlmRole, model: str, schema: type[BaseModel] | None
    ) -> tuple[str, str, Usage]:
        """One completion that adapts to what the hosted model accepts.

        Hosted models differ: some reject `response_format` (no JSON mode) or extra request
        fields such as `chat_template_kwargs`. Such a rejection is retried once without the
        feature (JSON then asked for in the prompt) and remembered for this model. A reply
        whose reasoning used up every token and left no answer is retried once with more room.
        """
        spent: Usage | None = None  # tokens of a reply that was all reasoning still count
        for _ in range(4):  # at most: drop the schema, drop the extra fields, give more room
            try:
                text, reasoning, usage = await self._complete(
                    self._get_client(), kwargs, role, self.provider, self.lock
                )
            except LLMError as exc:
                feature = _rejected_feature(exc, kwargs)
                if feature is None:
                    raise
                self._unsupported.add((feature, model))
                log.warning("%s rejected %s; retrying without it", model, feature)
                if feature == "schema":
                    kwargs.pop("response_format", None)
                    if schema is not None:
                        kwargs["messages"] = _with_json_instruction(kwargs["messages"], schema)
                else:
                    kwargs.pop("extra_body", None)
                continue
            if spent is not None:
                usage.prompt_tokens += spent.prompt_tokens
                usage.completion_tokens += spent.completion_tokens
                usage.cost_usd = round(usage.cost_usd + spent.cost_usd, 6)
            if not text and reasoning and int(kwargs["max_tokens"]) < REASONING_RETRY_TOKENS:
                log.warning("%s spent its reply on reasoning; retrying with more room", model)
                kwargs["max_tokens"] = REASONING_RETRY_TOKENS
                spent = usage
                continue
            return text, reasoning, usage
        raise LLMError("The language model did not give an answer.")

    async def _complete(
        self,
        client: Any,
        kwargs: dict[str, Any],
        role: LlmRole,
        provider: str,
        lock: asyncio.Lock | None,
    ) -> tuple[str, str, Usage]:
        try:
            # Total deadline: some gateways keep the connection alive with whitespace while a
            # slow model works, so the client's per-read timeout alone may never fire.
            call = client.chat.completions.create(**kwargs)
            if lock is not None:  # one request at a time on the local GPU server
                async with lock:
                    resp = await asyncio.wait_for(call, self.settings.llm_timeout_s)
            else:
                resp = await asyncio.wait_for(call, self.settings.llm_timeout_s)
        except Exception as exc:
            raise LLMError(
                "The language model did not answer: "
                f"{type(exc).__name__}: {self.redact(str(exc))[:200]}"
            ) from exc
        self.calls += 1
        msg = resp.choices[0].message
        text = THINK_RE.sub("", msg.content or "").strip()
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
        model = str(kwargs["model"])
        pin, pout = self.settings.price_for(role) if provider == self.provider else (0.0, 0.0)
        u = resp.usage
        ptok = int(getattr(u, "prompt_tokens", 0) or 0)
        ctok = int(getattr(u, "completion_tokens", 0) or 0)
        usage = Usage(
            role=role,
            model=model,
            prompt_tokens=ptok,
            completion_tokens=ctok,
            cost_usd=round((ptok * pin + ctok * pout) / 1_000_000, 6),
            provider=provider,
        )
        return text, reasoning, usage

    # --- fallback to the local model when the hosted one fails (quota, outage, timeout) ----

    def _primary_paused(self) -> bool:
        return self.settings.llm_fallback == "local" and time.time() < self._paused_until

    def _pause_primary(self, reason: str) -> None:
        """Skip the hosted model for a while: until midnight UTC for a daily quota, else 10 min."""
        now = time.time()
        if "per-day" in reason or "per day" in reason:
            self._paused_until = (now // 86_400 + 1) * 86_400
            self.fallback_reason = "daily free quota used up"
        else:
            self._paused_until = now + 600
            self.fallback_reason = reason.split(":")[1].strip() if ":" in reason else reason[:80]
        log.warning("hosted model unavailable (%s); using the local model", self.fallback_reason)

    async def _fallback(
        self,
        role: LlmRole,
        msgs: list[dict[str, str]],
        schema: type[BaseModel] | None,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, str, Usage]:
        if self._local_client is None:
            from openai import AsyncOpenAI

            self._local_client = AsyncOpenAI(
                base_url=self.settings.local_llm_base_url,
                api_key="local",
                timeout=self.settings.llm_timeout_s,
                max_retries=1,
            )
        local_msgs = [dict(m) for m in msgs]
        directive = "/no_think"  # Nemotron Nano v2: reasoning off for the fallback
        if local_msgs and local_msgs[0]["role"] == "system":
            if not local_msgs[0]["content"].startswith(directive):
                local_msgs[0]["content"] = f"{directive}\n{local_msgs[0]['content']}"
        else:
            local_msgs.insert(0, {"role": "system", "content": directive})
        kwargs: dict[str, Any] = {
            "model": self.settings.local_llm_model,
            "messages": local_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if schema is not None:
            kwargs["response_format"] = _response_format(schema)
        return await self._complete(
            self._local_client, kwargs, role, "local-fallback", self._local_lock
        )

    def _account(self, usage: Usage, budget: Budget | None) -> None:
        if budget is not None:
            budget.add(usage)
        if self.on_usage is not None:
            self.on_usage(usage)


REASONING_RETRY_TOKENS = 4096


def _with_json_instruction(
    msgs: list[dict[str, str]], schema: type[BaseModel]
) -> list[dict[str, str]]:
    """The prompt-only way to ask for JSON, for models without a JSON mode."""
    extra = (
        "\nReturn only the JSON object with your answer, no prose. Its fields are described "
        "by this JSON schema (fill in values; do not repeat the schema):\n"
        + json.dumps(_schema_for(schema))
    )
    out = [dict(m) for m in msgs]
    if out and out[0]["role"] == "system":
        if extra not in out[0]["content"]:
            out[0]["content"] = out[0]["content"] + extra
    else:
        out.insert(0, {"role": "system", "content": extra.strip()})
    return out


def _rejected_feature(exc: LLMError, kwargs: dict[str, Any]) -> str | None:
    """'schema' or 'extra' when a 400/422 reply blames that request feature, else None."""
    cause = exc.__cause__
    status = getattr(cause, "status_code", None)
    if status not in (400, 422):
        return None
    msg = str(cause).lower()
    if "response_format" in kwargs and any(
        w in msg for w in ("response_format", "json_schema", "json schema", "structured", "guided")
    ):
        return "schema"
    if "extra_body" in kwargs and any(
        w in msg
        for w in ("chat_template_kwargs", "enable_thinking", "reasoning", "extra", "unrecognized")
    ):
        return "extra"
    return None


def _response_format(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": schema.__name__, "schema": _schema_for(schema), "strict": True},
    }


def _json_or_empty(resp: Any) -> dict[str, Any]:
    try:
        data = resp.json()
    except Exception:  # not JSON: only the status mattered
        return {}
    return data if isinstance(data, dict) else {}


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:4]:
            loc = ".".join(str(x) for x in e["loc"])
            parts.append(f"{loc}: {e['msg']}")
        return "; ".join(parts)
    return str(exc)[:300]


class FakeLLM:
    """Scripted LLM for tests: responses keyed by agent name (callable or list)."""

    provider = "fake"

    def __init__(self, script: dict[str, Any], settings: Settings | None = None) -> None:
        self.script = script
        self.settings = settings
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "Fake LLM"}

    def model_for(self, role: LlmRole) -> str:
        return f"fake-{role}"

    async def chat(
        self,
        role: LlmRole,
        messages: list[dict[str, str]],
        schema: type[T] | None = None,
        *,
        agent: str = "",
        prompt_version: str = "",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        reasoning: bool = False,
        budget: Budget | None = None,
    ) -> LLMReply:
        if budget is not None:
            budget.check()
        self.calls.append((agent, messages))
        item = self.script.get(agent)
        if callable(item):
            item = item(messages)
        elif isinstance(item, list):
            item = item.pop(0) if item else None
        if item is None:
            raise LLMError(f"FakeLLM has no script for {agent}")
        text = item if isinstance(item, str) else json.dumps(item)
        usage = Usage(
            role=role,
            model=f"fake-{role}",
            prompt_tokens=100,
            completion_tokens=50,
            provider="fake",
        )
        if budget is not None:
            budget.add(usage)
        parsed = None
        if schema is not None:
            try:
                parsed = schema.model_validate_json(extract_json(text))
            except (ValueError, ValidationError) as exc:
                raise LLMOutputError(f"{agent}: {exc}", text, usage) from exc
        return LLMReply(text=text, parsed=parsed, usage=usage)


def recorded_count(cache_dir: Path) -> int:
    """How many responses are recorded (for the health/status page)."""
    root = cache_dir / "llm"
    return sum(1 for _ in root.rglob("*.json")) if root.exists() else 0
