"""Failure map contract: the red team's quality-diversity archive (docs/RAINBOW.md).

Built by `api.orchestrator.archive.Archive.snapshot`; streamed in `archive` session events,
kept in the session summary (`summary.archive`) and served at GET /sessions/{id}/archive.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FailureMapElite(BaseModel):
    """One simulated attack kept in a cell. Every number comes from its simulation."""

    attack_id: str
    title: str
    run_id: str
    severity: float  # physics score: ≥ 1.0 means the run breaks the plan
    is_break: bool
    round: int
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    parts: dict[str, float] = Field(default_factory=dict)  # the ratios behind the severity
    basis: str | None = None
    generated_by: str = "ai"
    fixed_by: str | None = None  # a kept fix that was simulated against this attack
    severity_after: float | None = None
    after_run_id: str | None = None


class FailureMapCell(BaseModel):
    """A (hazard kind × where) cell; empty when no attack has landed there yet."""

    kind: str
    where: str
    elites: list[FailureMapElite] = Field(default_factory=list)


class FailureMapAxis(BaseModel):
    id: str
    label: str


class FailureMapWhere(FailureMapAxis):
    exits: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)


class FailureMapRound(BaseModel):
    round: int
    coverage: float
    qd_score: float
    filled: int


class FailureMapAim(BaseModel):
    targeted: int = 0  # cells the red-team model was asked to fill
    hit: int = 0  # of those, cells one of its own attacks really landed in (rule fills excluded)


class FailureMap(BaseModel):
    """MAP-Elites grid: rows are hazard kinds, columns are places; only possible cells."""

    method: Literal["map_elites"] = "map_elites"
    per_cell: int = 2
    kinds: list[FailureMapAxis]
    wheres: list[FailureMapWhere]
    cells: list[FailureMapCell]
    cells_total: int
    filled: int
    coverage: float  # filled cells / cells
    qd_score: float  # sum of elite severities
    open_breaks: int  # cells whose strongest attack still breaks the plan as it stands
    aim: FailureMapAim = Field(default_factory=FailureMapAim)
    history: list[FailureMapRound] = Field(default_factory=list)
    fitness: str = ""

    @classmethod
    def of(cls, snapshot: dict[str, Any]) -> FailureMap:
        return cls.model_validate(snapshot)
