"""Common agent runner: prompt files, schema-validated calls, id checks, audit, events.

Every agent = one prompt file (`prompts/<name>.md`, with a version header), one Pydantic
output model, a model role, temperature ≤ 0.3 and a token cap. Domain validators reject
references to ids that do not exist; the model gets one chance to fix them.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

from api.adapters.llm import Budget, BudgetExceeded, LLMError, LLMOutputError, LLMReplayMiss
from api.db.models import AuditEntry
from api.db.session import db_session
from api.models import Usage

log = logging.getLogger("showtime.agents")
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
Role = Literal["fast", "long", "main", "judge"]
T = TypeVar("T", bound=BaseModel)


class AgentUnavailable(Exception):
    """The language model could not be reached; callers show a clear error."""


@lru_cache(maxsize=64)
def _read_prompt(filename: str) -> tuple[dict[str, str], str]:
    raw = (PROMPT_DIR / filename).read_text()
    meta: dict[str, str] = {}
    body = raw
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        body = raw[m.end() :]
    return meta, body.strip()


@dataclass
class AgentDef:
    """Implements the `Agent` extension point (AgentSpec)."""

    name: str
    role: Role
    prompt_file: str
    output_model: type[BaseModel]
    temperature: float = 0.2
    max_tokens: int = 1200
    description: str = ""

    @property
    def prompt_version(self) -> str:
        meta, _ = _read_prompt(self.prompt_file)
        return f"{self.name}@{meta.get('version', '0')}"

    def system_prompt(self, values: dict[str, str]) -> str:
        """Prompt body with {{placeholders}} filled in."""
        _, body = _read_prompt(self.prompt_file)
        for key, val in values.items():
            body = body.replace("{{" + key + "}}", val)
        return body


@dataclass
class AgentEnv:
    """What an agent call needs from the app (session-aware when used by Red Team Night)."""

    llm: Any
    budget: Budget | None = None
    emit: Callable[[str, dict[str, Any]], Any] | None = None
    project_id: str | None = None
    session_id: str | None = None
    db_url: str | None = None
    audit: bool = True
    on_usage: Callable[[Usage], None] | None = None


@dataclass
class AgentCall(Generic[T]):
    """Outcome of one agent call (after the optional repair round)."""

    output: T | None
    ok: bool
    usage: Usage | None = None
    problems: list[str] = field(default_factory=list)
    repaired: bool = False
    ms: float = 0.0
    error: str | None = None
    model: str = ""


def _merge(a: Usage | None, b: Usage | None) -> Usage | None:
    if a is None:
        return b
    if b is None:
        return a
    return a.model_copy(
        update={
            "prompt_tokens": a.prompt_tokens + b.prompt_tokens,
            "completion_tokens": a.completion_tokens + b.completion_tokens,
            "cost_usd": a.cost_usd + b.cost_usd,
            "cached": a.cached and b.cached,
        }
    )


async def call_agent(
    env: AgentEnv,
    spec: AgentDef,
    values: dict[str, str],
    user: str,
    *,
    output_model: type[T] | None = None,
    validate: Callable[[T], list[str]] | None = None,
    summarize: Callable[[T], str] | None = None,
    reasoning: bool = False,
) -> AgentCall[T]:
    """Run one agent: call, validate ids, one repair round, audit, emit `agent_call`."""
    model_cls: type[T] = output_model or spec.output_model  # type: ignore[assignment]
    messages = [
        {"role": "system", "content": spec.system_prompt(values)},
        {"role": "user", "content": user},
    ]
    t0 = time.perf_counter()
    usage: Usage | None = None
    repaired = False
    try:
        reply = await env.llm.chat(
            spec.role,
            messages,
            model_cls,
            agent=spec.name,
            prompt_version=spec.prompt_version,
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
            reasoning=reasoning,
            budget=env.budget,
        )
        usage = reply.usage
        repaired = reply.repaired
        out: T | None = reply.parsed
        problems = validate(out) if (validate and out is not None) else []
        if problems:
            fix_msgs = [
                *messages,
                {"role": "assistant", "content": reply.text[:6000]},
                {
                    "role": "user",
                    "content": "Fix these problems and return the "
                    "complete corrected JSON only:\n- " + "\n- ".join(problems[:8]),
                },
            ]
            reply2 = await env.llm.chat(
                spec.role,
                fix_msgs,
                model_cls,
                agent=spec.name,
                prompt_version=spec.prompt_version,
                temperature=0.0,
                max_tokens=spec.max_tokens,
                budget=env.budget,
            )
            usage = _merge(usage, reply2.usage)
            out2 = reply2.parsed
            problems2 = validate(out2) if (validate and out2 is not None) else []
            if out2 is not None and len(problems2) <= len(problems):
                out, problems = out2, problems2
                repaired = True
        result: AgentCall[T] = AgentCall(
            output=out, ok=not problems, usage=usage, problems=problems, repaired=repaired
        )
    except LLMOutputError as exc:
        result = AgentCall(output=None, ok=False, usage=usage, error=str(exc), repaired=True)
    except (BudgetExceeded, LLMReplayMiss):
        raise
    except LLMError as exc:
        _finish(
            env,
            spec,
            AgentCall(output=None, ok=False, error=str(exc)),
            t0,
            "unreachable",
            summarize,
        )
        raise AgentUnavailable(str(exc)) from exc
    result.model = usage.model if usage else ""
    _finish(env, spec, result, t0, None, summarize)
    return result


def _finish(
    env: AgentEnv,
    spec: AgentDef,
    res: AgentCall[Any],
    t0: float,
    note: str | None,
    summarize: Callable[[Any], str] | None,
) -> None:
    res.ms = round((time.perf_counter() - t0) * 1000, 1)
    u = res.usage
    summary = ""
    if res.output is not None and summarize is not None:
        try:
            summary = summarize(res.output)
        except Exception:  # summaries are cosmetic
            summary = ""
    if not summary:
        summary = note or (res.error or "; ".join(res.problems[:2]) or "ok")[:200]
    payload: dict[str, Any] = {
        "agent": spec.name,
        "role": spec.role,
        "model": u.model if u else "",
        "prompt_version": spec.prompt_version,
        "tokens_in": u.prompt_tokens if u else 0,
        "tokens_out": u.completion_tokens if u else 0,
        "cost_usd": round(u.cost_usd, 6) if u else 0.0,
        "ms": res.ms,
        "ok": res.ok,
        "summary": summary[:300],
        "repaired": res.repaired,
        "cached": bool(u and u.cached),
    }
    if env.emit is not None:
        env.emit("agent_call", payload)
    if u is not None and env.on_usage is not None:
        env.on_usage(u)
    if env.audit:
        try:
            with db_session(env.db_url) as s:
                s.add(
                    AuditEntry(
                        session_id=env.session_id,
                        project_id=env.project_id,
                        kind="agent_call",
                        agent=spec.name,
                        model=payload["model"],
                        prompt_version=spec.prompt_version,
                        tokens_in=payload["tokens_in"],
                        tokens_out=payload["tokens_out"],
                        cost_usd=payload["cost_usd"],
                        payload={
                            "summary": payload["summary"],
                            "ok": res.ok,
                            "problems": res.problems[:10],
                            "error": res.error,
                            "repaired": res.repaired,
                            "ms": res.ms,
                        },
                    )
                )
                s.commit()
        except Exception:  # auditing must never break the product flow
            log.exception("audit write failed")


def audit_decision(env: AgentEnv, agent: str, decision: str, details: dict[str, Any]) -> None:
    """Record a decision (attack discarded, fix accepted...) in the audit log."""
    if not env.audit:
        return
    try:
        with db_session(env.db_url) as s:
            s.add(
                AuditEntry(
                    session_id=env.session_id,
                    project_id=env.project_id,
                    kind="decision",
                    agent=agent,
                    payload={"decision": decision, **details},
                )
            )
            s.commit()
    except Exception:
        log.exception("audit write failed")
