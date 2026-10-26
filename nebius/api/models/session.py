"""Session events streamed to the UI (section 6.5) and API error shape."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SessionEventType = Literal[
    "agent_call",
    "tool_call",
    "run_started",
    "run_finished",
    "attack_card",
    "fix_card",
    "branch_node",
    "score",
    "cost",
    "countdown",
    "log",
    "status",
    "marshal",
    "archive",
    "sandbox",  # a run's sandbox lifecycle: queued, running, finished, refused, killed, ...
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionEvent(BaseModel):
    """One event in a red-team session stream."""

    seq: int = 0
    type: SessionEventType
    ts: str = Field(default_factory=_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApiError(BaseModel):
    """Consistent error body for every non-2xx response."""

    code: str
    message: str
    hint: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    """Token usage and cost of one LLM call."""

    role: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    provider: str = "local"


class Countdown(BaseModel):
    """Latest safe time to start evacuating: T_latest = T_hazard - (T_pre + RSET x SF)."""

    status: Literal["ok", "too_late", "no_hazard", "unknown"]
    t_hazard_s: float | None = None
    t_hazard_iso: str | None = None
    t_latest_s: float | None = None
    t_latest_iso: str | None = None
    rset_s: float | None = None
    pre_movement_s: float
    safety_factor: float
    hazard_source: str | None = None
    hazard_explanation: str = ""
    rset_source: str = ""
    formula: str = "T_latest = T_hazard − (T_pre_movement + RSET × safety factor)"
