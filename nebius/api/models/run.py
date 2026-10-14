"""RunRequest and RunResult contracts (section 6.4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

SCHEMA_VERSION = 1

RunStatus = Literal["queued", "running", "ok", "partial", "timeout", "failed", "cancelled"]

ResultBasis = Literal[
    "instant_estimate", "partial_simulation", "completed_simulation", "preview", "unknown"
]
"""What kind of evidence a result is. Only `completed_simulation` satisfies a full-simulation
gate; `preview` comes from the mock sandbox and `unknown` from a run that did not finish."""

INCOMPLETE_STATUSES = frozenset({"queued", "running", "failed", "timeout", "cancelled"})


class RunRequest(BaseModel):
    """Everything needed to reproduce a run. Same request hash -> same run."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION
    run_id: str = "auto"
    venue_id: str
    venue_hash: str = ""
    attack_id: str | None = None
    fix_id: str | None = None
    tier: Literal[1, 2, 3] = 3
    seed: int = 42
    max_people: int = Field(default=3000, ge=1, le=20_000)
    max_sim_s: float = Field(default=900.0, gt=0, le=3600)
    max_wall_s: float = Field(default=240.0, gt=0, le=3600)
    intervention_at_s: float | None = Field(default=None, ge=0)
    # Rewind (single-floor venues): write checkpoint.json at this simulated time and go on;
    # with resume=true the sim starts from checkpoint.json in the work folder instead.
    checkpoint_at_s: float | None = Field(default=None, ge=0, le=3600)
    resume: bool = False
    engine: str = "jupedsim"
    metrics: list[str] = Field(default_factory=lambda: ["rset", "peak_density", "per_exit_flow"])
    parent_run_id: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class PerExit(BaseModel):
    """Load and flow through one exit."""

    exit_id: str
    people: int
    mean_flow_pps: float
    first_s: float | None = None
    last_s: float | None = None


class RunMetrics(BaseModel):
    """Headline metrics. Every number is computed by a formula or the simulator."""

    evac_time_p95_s: float | None = None
    evac_time_max_s: float | None = None
    peak_density_ppm2: float = 0.0
    time_above_danger_s: float = 0.0
    time_above_warning_s: float = 0.0
    agents_total: int = 0
    agents_evacuated: int = 0
    agents_not_evacuated: int = 0
    per_exit: list[PerExit] = Field(default_factory=list)
    extra: dict[str, float] = Field(default_factory=dict)


class Hotspot(BaseModel):
    """A cluster of grid cells over the warning threshold."""

    floor_id: str
    x: float
    y: float
    peak_density_ppm2: float
    t_s: float
    level: Literal["warning", "danger"] = "warning"
    near: str | None = None  # nearest exit or obstacle id


class RunArtifacts(BaseModel):
    """Paths (relative to the project root) of the run's binary artifacts."""

    trajectory: str | None = None
    trajectory_index: str | None = None
    density_grid: str | None = None
    density_index: str | None = None
    raw: str | None = None


class RunResult(BaseModel):
    """Output of any tier. Tier 1 has no artifacts."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION
    run_id: str
    tier: Literal[1, 2, 3]
    status: RunStatus
    engine: str = "jupedsim"
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    hotspots: list[Hotspot] = Field(default_factory=list)
    artifacts: RunArtifacts = Field(default_factory=RunArtifacts)
    runtime_s: float = 0.0
    provider: str = "docker"
    parent_run_id: str | None = None
    venue_hash: str = ""
    seed: int = 0
    attack_id: str | None = None
    fix_id: str | None = None
    sim_time_s: float = 0.0
    notes: list[str] = Field(default_factory=list)
    error: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _drop_derived(cls, data: Any) -> Any:
        """`basis` is derived from the other fields; stored copies may still carry it."""
        if isinstance(data, dict) and "basis" in data:
            return {k: v for k, v in data.items() if k != "basis"}
        return data

    @computed_field(title="ResultBasis")  # type: ignore[prop-decorator]
    @property
    def basis(self) -> ResultBasis:
        """Evidence basis, always derived (see `result_basis`), so it can never go stale."""
        return result_basis(self)


def result_basis(r: RunResult) -> ResultBasis:
    """The one definition of what kind of evidence a run result is.

    A run that did not finish is `unknown`; a formula result is an `instant_estimate`; the
    mock sandbox gives a `preview`; a simulation that stopped before everyone was out (time
    cap, people trapped or still inside) is a `partial_simulation`; only a simulation that
    ended normally with everyone out is a `completed_simulation`.

    `api.core.evidence` re-exports this function; it lives with the contract so the computed
    `RunResult.basis` field can use it without a circular import.
    """
    if r.status in INCOMPLETE_STATUSES:
        return "unknown"
    if r.tier == 1:
        return "instant_estimate"
    if r.provider == "fake" or r.engine == "fake":
        return "preview"
    if not r.engine:
        return "unknown"
    m = r.metrics
    if r.status == "partial" or m.agents_not_evacuated > 0 or "rset_extrapolated_s" in m.extra:
        return "partial_simulation"
    return "completed_simulation"
