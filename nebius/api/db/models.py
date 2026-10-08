"""SQLite tables (SQLModel). Schema changes go through Alembic migrations only."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware now (stored as UTC)."""
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    """An event or a building being planned."""

    id: str = Field(primary_key=True)
    name: str
    description: str = ""
    template_id: str | None = None
    current_version: int = 0
    redo_stack: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    sample: bool = False
    archived: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class VenueVersion(SQLModel, table=True):
    """Every save is a version: full snapshot plus the patch that produced it."""

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(index=True, foreign_key="project.id")
    version: int = Field(index=True)
    venue: dict[str, Any] = Field(sa_column=Column(JSON))
    venue_hash: str = ""
    base_version: int | None = None  # the state this version was derived from (for undo)
    patch: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    inverse: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    message: str = ""
    author: str = "user"  # user | agent | system
    created_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    """A simulation or instant estimate. `id` is derived from the request hash."""

    id: str = Field(primary_key=True)
    project_id: str | None = Field(default=None, index=True)
    session_id: str | None = Field(default=None, index=True)
    venue_version: int | None = None
    venue_hash: str = ""
    tier: int = 3
    status: str = "queued"
    label: str = ""
    attack_id: str | None = None
    fix_id: str | None = None
    parent_run_id: str | None = None
    request: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    progress: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class RedTeamSession(SQLModel, table=True):
    """A Red Team Night session."""

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    venue_version: int = 0
    status: str = "queued"  # queued | running | finished | stopped | failed
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    summary: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class SessionEventRow(SQLModel, table=True):
    """One streamed session event (replayable)."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    seq: int
    type: str
    ts: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class AuditEntry(SQLModel, table=True):
    """Audit log: every agent call, tool call and decision, with model and prompt version."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(default=None, index=True)
    project_id: str | None = Field(default=None, index=True)
    ts: datetime = Field(default_factory=utcnow)
    kind: str  # agent_call | tool_call | decision | edit
    agent: str = ""
    model: str = ""
    prompt_version: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class UserSetting(SQLModel, table=True):
    """Settings changed in the UI (budgets, units, theme...)."""

    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow)
