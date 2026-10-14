"""Autopilot (N13): one request taken to a tested plan. Contracts for the API and the UI.

Autopilot never applies fixes on its own: it stops at a tested plan and the organizer
accepts (or not) on Your plan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

AutopilotDepth = Literal["quick", "thorough"]
AutopilotStatus = Literal["queued", "running", "finished", "stopped", "failed"]
AutopilotStepKey = Literal[
    "understand", "venue", "capacity", "simulate", "attack", "fix", "confirm", "deliver"
]
AutopilotStepStatus = Literal["pending", "running", "done", "skipped", "failed"]
AutopilotEventType = Literal["step", "project", "session", "log", "done"]

# the steps an organizer sees, in order, with plain labels
STEP_LABELS: dict[AutopilotStepKey, str] = {
    "understand": "Understanding your event",
    "venue": "Building the venue",
    "capacity": "Checking capacity and staff",
    "simulate": "Simulating the crowd",
    "attack": "Trying what could go wrong",
    "fix": "Fixing the weak spots",
    "confirm": "Confirming the fixes",
    "deliver": "Writing your plan",
}
STEP_ORDER: tuple[AutopilotStepKey, ...] = tuple(STEP_LABELS)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AutopilotRequest(BaseModel):
    """A sentence about the event, or an existing project, and how deep to test."""

    text: str | None = Field(default=None, min_length=8, max_length=1500)
    project_id: str | None = None
    depth: AutopilotDepth = "quick"

    @model_validator(mode="after")
    def _one_input(self) -> AutopilotRequest:
        has_text = bool(self.text and self.text.strip())
        if has_text == bool(self.project_id):
            raise ValueError("Give either a sentence about the event or a project, not both.")
        return self


class AutopilotStep(BaseModel):
    """One plain-language step and where it is."""

    key: AutopilotStepKey
    label: str
    status: AutopilotStepStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    detail: str | None = None


class AutopilotCost(BaseModel):
    """What the run used. Intake is measured on the app's usage meter while the request was
    read and the venue built; the red-team part comes from the session's own meter."""

    usd_total: float = 0.0
    tokens_total: int = 0
    llm_calls: int = 0
    simulations: int = 0
    intake: dict[str, float] = Field(default_factory=dict)
    red_team: dict[str, float] = Field(default_factory=dict)
    detail: dict[str, Any] | None = None  # the session's richer cost record, when it has one


class AutopilotRun(BaseModel):
    """An Autopilot run as the API returns it."""

    id: str
    status: AutopilotStatus
    depth: AutopilotDepth
    text: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    steps: list[AutopilotStep]
    report_url: str | None = None
    headline: str | None = None
    cost: AutopilotCost | None = None
    notes: list[str] = Field(default_factory=list)
    partial_reason: str | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None


class AutopilotEvent(BaseModel):
    """One event in an Autopilot stream (same framing as session events)."""

    seq: int = 0
    type: AutopilotEventType
    ts: str = Field(default_factory=_now)
    payload: dict[str, Any] = Field(default_factory=dict)


def initial_steps() -> list[AutopilotStep]:
    """Every step, pending."""
    return [AutopilotStep(key=k, label=STEP_LABELS[k]) for k in STEP_ORDER]
