"""Simulator validation exhibit: `api/data/validation.json` (scripts/validate_bottleneck.py).

Measured flow through a real bottleneck experiment next to the simulated flow for the same
geometry and headcount, both measured with the same PedPy method. Nothing here is tuned.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeedRun(_Strict):
    """One simulation of one width."""

    seed: int
    run_id: str
    flow_ps: float = Field(gt=0)
    crossings: int = Field(ge=0)
    window_s: list[float] = Field(default_factory=list)


class FlowRange(_Strict):
    """Simulated flow over the seeds (persons/s)."""

    median: float = Field(gt=0)
    min: float = Field(gt=0)
    max: float = Field(gt=0)
    runs: list[SeedRun] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> FlowRange:
        if not (self.min <= self.median <= self.max):
            raise ValueError("expected min <= median <= max")
        return self


class ValidationWidth(_Strict):
    """One bottleneck width: the experiment run against the simulated runs."""

    run_name: str
    b_m: float = Field(gt=0)
    l_m: float = Field(gt=0)
    n_people: int = Field(gt=0)
    measured_flow_ps: float = Field(gt=0)
    measured_specific_flow: float = Field(gt=0)
    measured_window_s: list[float] = Field(default_factory=list)
    simulated_flow_ps: FlowRange
    simulated_specific_flow: float = Field(gt=0)
    error_pct: float  # (simulated median - measured) / measured x 100, signed


class Reference(_Strict):
    """A citation."""

    label: str
    url: str


class ValidationMeta(_Strict):
    """Where the numbers come from and how they were computed."""

    dataset: str
    dataset_doi: str
    dataset_licence: str
    funding: str
    papers: list[Reference]
    method: str
    measurement_line: str
    steady_window: str
    engine: str
    model: str
    pedpy_version: str
    sim_image: str
    agent_radius_m: float
    walk_speed: str
    sim_dt_s: float
    frame_hz: float
    seeds: list[int] = Field(min_length=1)
    app_defaults: bool
    generated_at: str
    assumptions: list[str]
    experimental_repeat: str = ""


class SimulatorValidation(_Strict):
    """The whole exhibit."""

    schema_version: int = 1
    meta: ValidationMeta
    widths: list[ValidationWidth] = Field(min_length=1)
    median_abs_error_pct: float = Field(ge=0)
    mean_error_pct: float  # signed: > 0 means the simulator is faster than people
