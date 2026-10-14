"""Patch, attack, fix and scenario-event contracts (sections 6.2 and 6.3).

Patch ops and scenario events are open-ended: each carries a `type`/`op` string
and is validated against the model registered for it by a plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

if TYPE_CHECKING:
    from api.models.plan import ObjectConstraint, PlanAction

SCHEMA_VERSION = 1


class PatchOpIn(BaseModel):
    """One edit operation; validated by the `PatchOp` plugin registered for `op`."""

    model_config = ConfigDict(extra="allow")
    op: str


class VenuePatch(BaseModel):
    """A list of edit operations applied atomically to a venue."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION
    ops: list[PatchOpIn] = Field(default_factory=list, max_length=50)


class ScenarioEventIn(BaseModel):
    """One timed event; validated by the `ScenarioEvent` plugin registered for `type`."""

    model_config = ConfigDict(extra="allow")
    type: str
    at_s: float = Field(default=0.0, ge=0)


class InspiredBy(BaseModel):
    """The real incident an attack is grounded in. `source_url` is mandatory."""

    model_config = ConfigDict(extra="forbid")
    incident: str
    year: int | None = None
    source_url: HttpUrl
    evidence: str = ""
    dataset_row: int | None = None


class Attack(BaseModel):
    """A red-team scenario."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION
    attack_id: str
    title: str
    events: list[ScenarioEventIn] = Field(min_length=1, max_length=8)
    inspired_by: InspiredBy
    rationale: str = ""
    extensions: dict[str, Any] = Field(default_factory=dict)


class Fix(BaseModel):
    """A blue-team fix: a venue patch and/or operational measures."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION
    fix_id: str
    for_attack: str
    title: str
    patch: VenuePatch = Field(default_factory=VenuePatch)
    operational: list[ScenarioEventIn] = Field(default_factory=list, max_length=8)
    actions: list[PlanAction] = Field(default_factory=list, max_length=100)
    replace_actions: list[PlanAction] = Field(default_factory=list, max_length=100)
    remove_action_ids: list[str] = Field(default_factory=list, max_length=100)
    new_objects: dict[str, ObjectConstraint] = Field(default_factory=dict)
    rationale: str = ""
    cost_label: Literal["low", "medium", "high"] = "medium"
    extensions: dict[str, Any] = Field(default_factory=dict)
