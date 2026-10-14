"""Versioned organizer constraints, actions, and atomic plan-edit contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.models.scenario import ScenarioEventIn, VenuePatch
from api.models.venue import Venue


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Approval(PlanModel):
    status: Literal["pending", "approved", "rejected"] = "pending"
    source: str = ""
    recorded_by: str = ""

    @model_validator(mode="after")
    def approved_source(self) -> Approval:
        if self.status == "approved" and (not self.source.strip() or not self.recorded_by.strip()):
            raise ValueError("approved permissions need a source and recorded_by")
        return self


class ObjectConstraint(PlanModel):
    locked: bool = False
    placement: Literal["fixed", "movable"] = "movable"
    origin: Literal["existing", "proposed"] = "existing"
    access: Literal["allowed", "restricted", "unavailable"] = "allowed"
    required_approvals: list[str] = Field(default_factory=list)
    estimated_cost: float | None = Field(default=None, ge=0)


class ResourcePool(PlanModel):
    kind: Literal["staff", "equipment"]
    count: int = Field(ge=0, le=100_000)
    available_from_s: float = Field(default=0, ge=0)
    available_until_s: float = Field(default=3600, gt=0)

    @model_validator(mode="after")
    def interval(self) -> ResourcePool:
        if self.available_until_s <= self.available_from_s:
            raise ValueError("resource availability must end after it starts")
        return self


class ResourceAllocation(PlanModel):
    resource_id: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=100_000)


class PlanAction(PlanModel):
    action_id: str = Field(min_length=1, max_length=100)
    label: str = ""
    event: ScenarioEventIn | None = None
    start_s: float = Field(default=0, ge=0)
    end_s: float = Field(default=3600, gt=0)
    target_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    resources: list[ResourceAllocation] = Field(default_factory=list)
    estimated_cost: float | None = Field(default=None, ge=0)
    source: Literal["user", "agent", "rules", "imported"] = "user"

    @model_validator(mode="after")
    def interval(self) -> PlanAction:
        if self.end_s <= self.start_s:
            raise ValueError("action end_s must be greater than start_s")
        if self.event is not None and self.event.at_s != self.start_s:
            raise ValueError("event at_s must equal action start_s")
        return self


class PlanConstraints(PlanModel):
    budget_limit: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    allow_construction: bool = False
    allowed_ops: list[str] | None = None
    require_staff_for_measures: bool = True
    objects: dict[str, ObjectConstraint] = Field(default_factory=dict)
    approvals: dict[str, Approval] = Field(default_factory=dict)
    resources: dict[str, ResourcePool] = Field(default_factory=dict)


class PlanData(PlanModel):
    schema_version: Literal[1] = 1
    enforce_constraints: bool = True
    constraints: PlanConstraints = Field(default_factory=PlanConstraints)
    actions: list[PlanAction] = Field(default_factory=list, max_length=100)


class PlanUpdate(PlanModel):
    expected_version: int = Field(ge=1)
    plan: PlanData
    message: str = "Updated organizer plan"


class PlanBundle(PlanModel):
    expected_version: int = Field(ge=1)
    patch: VenuePatch = Field(default_factory=VenuePatch)
    actions: list[PlanAction] = Field(default_factory=list, max_length=100)
    replace_actions: list[PlanAction] = Field(default_factory=list, max_length=100)
    remove_action_ids: list[str] = Field(default_factory=list, max_length=100)
    new_objects: dict[str, ObjectConstraint] = Field(default_factory=dict)
    message: str = "Applied plan bundle"
    source: Literal["user", "agent", "rules"] = "user"


class PlanIssue(PlanModel):
    code: str
    message: str
    target_ids: list[str] = Field(default_factory=list)


class PlanSnapshot(PlanModel):
    schema_version: Literal[1] = 1
    project_id: str
    version: int
    plan_hash: str
    configured: bool
    venue: Venue
    plan: PlanData


class BundlePreview(PlanModel):
    valid: bool
    issues: list[PlanIssue] = Field(default_factory=list)
    candidate: PlanSnapshot | None = None


class EvidenceReference(PlanModel):
    run_id: str
    run_status: str
    plan_hash: str | None = None
    applicability: Literal["current", "stale", "unknown"]
    reason: str


class PlanEvidence(PlanModel):
    project_id: str
    version: int
    plan_hash: str
    runs: list[EvidenceReference]
