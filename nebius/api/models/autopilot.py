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
AutopilotEventType = Literal["step", "project", "session", "cost", "log", "done"]
# why a delivered plan is partial: a session budget ran out, the organizer stopped it, the
# red-team session hit an error, or the server restarted mid-run
AutopilotPartialReason = Literal["budget", "stopped", "error", "restart"]

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

# where each step happens: graph nodes (orchestrator/copilot_graph.py) and, inside the
# `red_team` node, the phases of the red-team session (orchestrator/session.py)
STEP_NODES: dict[AutopilotStepKey, tuple[str, ...]] = {
    "understand": ("understand",),
    "venue": ("locate", "design", "layout"),
    "capacity": ("estimate", "create"),
    "simulate": ("simulate", "sweep"),
    "attack": ("red_team",),
    "fix": ("red_team",),
    "confirm": ("red_team",),
    "deliver": ("red_team", "deliver"),
}
STEP_PHASES: dict[AutopilotStepKey, tuple[str, ...]] = {
    "simulate": ("baseline",),
    "attack": ("red_team", "screening", "simulating"),
    "fix": ("blue_team",),
    "confirm": ("confirming",),
    "deliver": ("judging",),
}


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
    """What the run used. Intake (reading the request, building the venue) is metered on the
    run's own agent calls; the red-team part comes from the session's meter."""

    usd_total: float = 0.0
    tokens_total: int = 0
    llm_calls: int = 0
    simulations: int = 0
    intake_usd: float = 0.0
    intake_tokens: int = 0
    red_team_usd: float = 0.0
    red_team_tokens: int = 0
    detail: dict[str, Any] | None = None  # the session's own cost record, when it has one


class EvidenceSuggestion(BaseModel):
    """A web source about the briefed place or event for the organizer to check (never applied)."""

    topic: Literal["capacity", "attendance", "rules"]
    title: str
    url: str
    published: str | None = None
    sentence: str = ""


class AutopilotRun(BaseModel):
    """An Autopilot run as the API returns it."""

    id: str
    status: AutopilotStatus
    depth: AutopilotDepth
    text: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    session_id: str | None = None
    steps: list[AutopilotStep]
    report_url: str | None = None
    headline: str | None = None
    cost: AutopilotCost | None = None
    notes: list[str] = Field(default_factory=list)
    # what the web says about the place and event, to check (empty without live web search)
    evidence: list[EvidenceSuggestion] = Field(default_factory=list)
    ai_outage: bool = False  # the AI model was unreachable; standard methods were used
    partial_reason: AutopilotPartialReason | None = None
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
