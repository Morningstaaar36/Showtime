"""Apply a VenuePatch through the PatchOp registry, with validation and undo."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from pydantic import ValidationError

from api.core.extensions import Registry
from api.core.geometry import Check, validate_venue
from api.core.plan import (
    PLAN_KEY,
    PlanError,
    edit_issues,
    plan_data,
    transition_issues,
    validate_plan,
    with_plan,
)
from api.models import PatchOpIn, Venue, VenuePatch

HASH_EXCLUDE = {"name", "description", "extensions"}


class PatchError(Exception):
    """A patch could not be applied. `problems` are user-facing sentences."""

    def __init__(self, problems: list[str], op_index: int | None = None) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems
        self.op_index = op_index


@dataclass
class PatchResult:
    """Outcome of applying a patch."""

    venue: Venue
    inverse: VenuePatch
    new_errors: list[Check] = field(default_factory=list)
    warnings: list[Check] = field(default_factory=list)


def venue_hash(venue: Venue) -> str:
    """Stable sha256 over everything that affects a simulation."""
    data = venue.model_dump(mode="json", exclude=HASH_EXCLUDE)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def _readable(exc: ValidationError, op: str) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        out.append(f"'{op}': {loc} {err['msg'].lower()}")
    return out


def apply_patch(
    venue: Venue,
    patch: VenuePatch,
    registry: Registry,
    *,
    allow_new_errors: bool = False,
    organizer_edit: bool = False,
) -> PatchResult:
    """Apply all ops atomically. Raises PatchError on any invalid op.

    The patch is rejected if it introduces geometry errors that were not there before,
    unless `allow_new_errors` is set (used for "Break it yourself", which blocks exits).
    """
    if not patch.ops:
        raise PatchError(["The patch has no operations."])
    before_errors = {(c.code, tuple(c.target_ids)) for c in validate_venue(venue).errors}
    current = venue
    policy_base = venue.model_copy(deep=True)
    inverse_ops: list[PatchOpIn] = []
    for i, raw in enumerate(patch.ops):
        if not registry.has("PatchOp", raw.op):
            known = ", ".join(sorted(registry.keys("PatchOp")))
            raise PatchError([f"Unknown operation '{raw.op}'. Allowed: {known}."], i)
        op = registry.patch_op(raw.op)
        organizer_only = getattr(op, "user_only", False)
        if organizer_only and not organizer_edit:
            raise PatchError([f"Operation '{raw.op}' is reserved for organizer edits."], i)
        if not organizer_only:
            policy_issues = edit_issues(current, raw.model_dump())
            if policy_issues:
                raise PlanError(policy_issues)
        try:
            params = op.params_model.model_validate(raw.model_dump())
        except ValidationError as exc:
            raise PatchError(_readable(exc, raw.op), i) from exc
        problems = op.validate(current, params)
        if problems:
            raise PatchError(problems, i)
        inverse_ops = op.invert(current, params) + inverse_ops
        try:
            current = op.apply(current, params)
        except (ValueError, ValidationError) as exc:
            raise PatchError([f"'{raw.op}' failed: {exc}"], i) from exc
        if organizer_only:
            # The explicit organizer command may change policy. Geometry edits
            # in the same bundle still pass the resulting policy guards.
            for key in (PLAN_KEY, "plan_annotations"):
                if key in current.extensions:
                    policy_base.extensions[key] = current.model_copy(deep=True).extensions[key]
                else:
                    policy_base.extensions.pop(key, None)
    report = validate_venue(current)
    new_errors = [c for c in report.errors if (c.code, tuple(c.target_ids)) not in before_errors]
    if new_errors and not allow_new_errors:
        raise PatchError([f"{c.message} {c.hint}".strip() for c in new_errors])
    warnings = [c for c in report.checks if c.severity == "warning"]
    if PLAN_KEY in current.extensions:
        data = plan_data(current)
        data.constraints.objects = {
            oid: policy
            for oid, policy in data.constraints.objects.items()
            if oid in current.all_ids()
        }
        current = with_plan(current, data)
        validate_plan(current, registry)
    policy_issues = transition_issues(policy_base, current)
    if policy_issues:
        raise PlanError(policy_issues)
    return PatchResult(
        venue=current, inverse=VenuePatch(ops=inverse_ops), new_errors=new_errors, warnings=warnings
    )


def describe_ops(registry: Registry) -> list[dict[str, object]]:
    """JSON schemas of every registered op (given to the Venue agent)."""
    out: list[dict[str, object]] = []
    for op in registry.all("PatchOp"):
        schema = op.params_model.model_json_schema()
        props = {k: v for k, v in schema.get("properties", {}).items() if k != "op"}
        out.append(
            {
                "op": op.name,
                "description": op.description,
                "params": props,
                "required": [r for r in schema.get("required", []) if r != "op"],
            }
        )
    return out
