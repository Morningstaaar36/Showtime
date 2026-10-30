"""Extension points (section 7A.1). Plugins implement these; core only talks to them.

Every extension point is a `Protocol`, so a plugin object only needs the right
attributes and methods; no inheritance from core classes is required.
"""

from __future__ import annotations

import builtins
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from api.core.extensions.breaks import BreakRule
from api.models import Attack, Countdown, Fix, PatchOpIn, RunResult, ScenarioEventIn, Venue

API_VERSION = "1"


# ---------------------------------------------------------------------------
# Venue editing and import
# ---------------------------------------------------------------------------


@runtime_checkable
class PatchOp(Protocol):
    """An edit operation on a venue (`move`, `add_exit`, ...)."""

    name: str
    description: str
    params_model: type[BaseModel]

    def validate(self, venue: Venue, params: Any) -> list[str]:
        """Return human-readable problems; empty list means the op can be applied."""

    def apply(self, venue: Venue, params: Any) -> Venue:
        """Return a new venue with the op applied (never mutate the input)."""

    def invert(self, before: Venue, params: Any) -> list[PatchOpIn]:
        """Ops that undo this op when applied to the venue produced by `apply`."""


@runtime_checkable
class VenueImporter(Protocol):
    """Turn an uploaded file into a Venue."""

    id: str
    label: str
    file_extensions: tuple[str, ...]

    def import_bytes(self, data: bytes, filename: str) -> Venue:
        """Parse bytes or raise ValueError with a readable message."""


# ---------------------------------------------------------------------------
# Scenario events and Tier 1
# ---------------------------------------------------------------------------


@dataclass
class T1Exit:
    """An exit or stair entrance as seen by the Tier 1 flow model."""

    id: str
    floor_id: str
    x: float
    y: float
    width_m: float
    capacity_pps: float
    kind: Literal["exit", "stair"] = "exit"
    blocked_from_s: float | None = None
    leads_to_floor: str | None = None
    stair_delay_s: float = 0.0
    label: str = ""


@dataclass
class T1Group:
    """A group of people starting together (one zone, or a surge)."""

    id: str
    floor_id: str
    x: float
    y: float
    people: int
    release_s: float = 0.0
    speed_factor: float = 1.0
    counterflow: bool = False


@dataclass
class Tier1State:
    """Mutable input of the Tier 1 model; scenario events adjust it before solving."""

    exits: dict[str, T1Exit]
    groups: dict[str, T1Group]
    walk_speed_mps: float
    notes: list[str] = field(default_factory=list)
    global_speed_factor: float = 1.0


@runtime_checkable
class ScenarioEvent(Protocol):
    """A timed event in an attack or fix (`block_exit`, `surge`, ...)."""

    type: str
    label: str
    description: str
    params_model: builtins.type[BaseModel]

    def validate_refs(self, venue: Venue, params: Any) -> list[str]:
        """Problems with ids referenced by the event (unknown exit, zone, ...)."""

    def tier1_effect(self, state: Tier1State, params: Any) -> None:
        """Adjust the Tier 1 state to reflect this event."""


# ---------------------------------------------------------------------------
# Simulation engines and metrics
# ---------------------------------------------------------------------------


@runtime_checkable
class SimEngine(Protocol):
    """Describes an engine available inside the sandbox image."""

    id: str
    label: str
    tiers: tuple[int, ...]
    metrics: tuple[str, ...]
    citation: str


@runtime_checkable
class Metric(Protocol):
    """Describes a metric computed sim-side from trajectories."""

    id: str
    label: str
    unit: str
    formula: str


# ---------------------------------------------------------------------------
# Hazards, rules, incidents
# ---------------------------------------------------------------------------


class HazardResult(BaseModel):
    """When the venue becomes unsafe, and why. `t_hazard_s` is seconds after event start."""

    source: str
    t_hazard_s: float | None = None
    t_hazard_iso: str | None = None
    explanation: str
    details: dict[str, Any] = {}
    label: str = "screening estimate"


@dataclass
class HazardContext:
    """What a hazard source may read. Providers are injected as plain callables."""

    venue: Venue
    attack: Attack | None = None
    manual: dict[str, float] = field(default_factory=dict)
    # (lat, lon, start date ISO, IANA time zone) -> {"times", "gust_ms", "source", ...}
    get_forecast: Callable[[float, float, str, str], Awaitable[dict[str, Any]]] | None = None
    settings: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class HazardSource(Protocol):
    """Produces `T_hazard` and its explanation."""

    id: str
    label: str
    modes: tuple[str, ...]

    async def evaluate(self, ctx: HazardContext) -> HazardResult | None:
        """Return a hazard time, or None when this source does not apply."""


class RuleFinding(BaseModel):
    """Result of checking one rule against a venue."""

    rule_id: str
    status: Literal["pass", "fail", "unknown"]
    message: str
    metric: str
    value: float | None = None
    limit: float | None = None
    unit: str = ""
    source_url: str | None = None
    target_id: str | None = None
    confirmed: bool = False


@runtime_checkable
class RulesPack(Protocol):
    """A set of checkable rules (data + checker)."""

    id: str
    label: str

    def check(self, venue: Venue, tier1: RunResult | None) -> list[RuleFinding]:
        """Run all rules; never raises for a valid venue."""


class IncidentRecord(BaseModel):
    """One real crowd incident from a dataset."""

    row_id: int
    year: int | None
    country: str = ""
    city: str = ""
    event_type: str = ""
    deaths: int | None = None
    injuries: int | None = None
    keywords: list[str] = []
    description: str = ""
    source_url: str
    setting: str = ""  # indoor | outdoor | street | stadium | religious | ...
    name: str = ""  # display name ("Seoul Halloween crowd crush"); generated when empty
    date: str | None = None
    crowd_size: int | None = None
    origin: str = "dataset"  # dataset (the incident list) | tavily (a live web search hit)
    dataset_url: str | None = None  # DOI link to the dataset row
    dataset: str = ""  # which dataset or list the record comes from


@runtime_checkable
class IncidentSource(Protocol):
    """Incident records for the red team."""

    id: str
    label: str

    def search(self, features: dict[str, Any], limit: int) -> list[IncidentRecord]:
        """Incidents most relevant to the venue features."""

    def count(self) -> int:
        """Number of records available (0 when the dataset is not downloaded)."""


# ---------------------------------------------------------------------------
# Agents, tools, providers, exporters
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentSpec(Protocol):
    """An LLM role: prompt file, output schema, model role."""

    name: str
    role: Literal["fast", "long", "main", "judge", "vision"]
    prompt_file: str
    prompt_version: str
    output_model: type[BaseModel]
    temperature: float
    max_tokens: int


@runtime_checkable
class Tool(Protocol):
    """A function agents may call."""

    name: str
    description: str
    params_model: type[BaseModel]

    async def run(self, ctx: Any, params: Any) -> dict[str, Any]:
        """Execute the tool and return JSON-serialisable output."""


@runtime_checkable
class Provider(Protocol):
    """A backend for llm | sandbox | search | weather."""

    kind: Literal["llm", "sandbox", "search", "weather"]
    id: str
    label: str


class ReportBundle(BaseModel):
    """Everything an exporter needs. Built by core from stored results only."""

    project_name: str
    venue: Venue
    venue_version: int
    baseline: RunResult | None = None
    final: RunResult | None = None
    attacks: list[Attack] = []
    fixes: list[Fix] = []
    results: dict[str, RunResult] = {}
    accepted_fix_ids: list[str] = []
    countdown: Countdown | None = None
    hazard: HazardResult | None = None
    rules: list[RuleFinding] = []
    assumptions: list[dict[str, str]] = []
    sources: list[dict[str, str]] = []
    exit_assignment: dict[str, dict[str, int]] = {}
    summary_text: str = ""
    generated_at: str
    session_id: str | None = None
    disclaimer: str = "Planning aid, not a safety certification."
    density_danger_ppm2: float = 5.0
    density_warn_ppm2: float = 3.5
    # the server's break and at-risk rules (settings): exporters judge runs with these only
    break_rule: BreakRule | None = None
    provider_label: str = "LOCAL"
    tokens_total: int = 0
    cost_usd: float = 0.0
    scoreboard: list[dict[str, Any]] = []
    recommendations: list[str] = []
    worst_attack_id: str | None = None
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    fixed_venue: Venue | None = None
    stair_assignment: dict[str, dict[str, int]] = {}
    calibration: dict[str, Any] = {}
    extras: dict[str, Any] = {}  # e.g. extras["map_svg"] rendered by another exporter


@runtime_checkable
class Exporter(Protocol):
    """An output format for a report bundle."""

    id: str
    label: str
    media_type: str
    file_ext: str

    def render(self, bundle: ReportBundle) -> bytes:
        """Render the bundle to bytes."""


__all__ = [
    "API_VERSION",
    "AgentSpec",
    "Exporter",
    "HazardContext",
    "HazardResult",
    "HazardSource",
    "IncidentRecord",
    "IncidentSource",
    "Metric",
    "PatchOp",
    "Provider",
    "ReportBundle",
    "RuleFinding",
    "RulesPack",
    "ScenarioEvent",
    "ScenarioEventIn",
    "SimEngine",
    "T1Exit",
    "T1Group",
    "Tier1State",
    "Tool",
    "VenueImporter",
]
