"""Plan validation shared by user edits, rules, agents, persistence, and runs.

The typed plan lives in Venue.extensions so existing version history and exports
retain the complete state. Legacy venues without this extension remain editable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import ValidationError

from api.core.extensions import Registry
from api.models.plan import EvidenceReference, ObjectConstraint, PlanAction, PlanData, PlanIssue
from api.models.scenario import ScenarioEventIn
from api.models.venue import Exit, Obstacle, Venue, Zone

PLAN_KEY = "organizer_plan"
STAFF_MEASURES = {"marshal_redirect", "one_way", "staggered_release"}


class PlanError(Exception):
    def __init__(self, issues: list[PlanIssue]) -> None:
        self.issues = issues
        self.problems = [i.message for i in issues]
        super().__init__("; ".join(self.problems))


class PlanConflict(Exception):
    """The proposal was made for a different saved version."""


def fail(code: str, message: str, *targets: str) -> PlanIssue:
    return PlanIssue(code=code, message=message, target_ids=list(targets))


def plan_data(venue: Venue) -> PlanData:
    try:
        return PlanData.model_validate(venue.extensions.get(PLAN_KEY, {}))
    except ValidationError as exc:
        raise PlanError([fail("invalid_plan", str(exc))]) from exc


def with_plan(venue: Venue, data: PlanData) -> Venue:
    out = venue.model_copy(deep=True)
    payload = data.model_dump(mode="python")
    try:
        json.dumps(payload, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise PlanError([fail("invalid_plan_json", "Plan data must be finite JSON.")]) from exc
    try:
        checked = PlanData.model_validate(payload)
    except ValidationError as exc:
        raise PlanError([fail("invalid_plan", str(exc))]) from exc
    out.extensions[PLAN_KEY] = checked.model_dump(mode="json")
    return out


def plan_hash(venue: Venue) -> str:
    """Conservative identity of geometry, operations, policy, and environmental inputs.

    Project IDs and display names are excluded so a duplicate can reproduce a plan.
    No evidence records are stored in this identity; applicability is derived at read time.
    """
    data = venue.model_dump(mode="python", exclude={"venue_id", "name", "description"})
    data["plan_configured"] = PLAN_KEY in venue.extensions
    data["extensions"][PLAN_KEY] = plan_data(venue).model_dump(mode="python")
    try:
        blob = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise PlanError([fail("invalid_plan_json", "Plan data must be finite JSON.")]) from exc
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def evidence_reference(
    run_id: str,
    status: str,
    recorded_hash: str | None,
    current_hash: str,
    has_candidate_fix: bool = False,
) -> EvidenceReference:
    state: Literal["unknown", "current", "stale"]
    if recorded_hash is None:
        state, reason = "unknown", "Legacy run has no complete plan identity."
    elif has_candidate_fix:
        state, reason = (
            "unknown",
            "Run includes an additional candidate fix; compare its full inputs before reuse.",
        )
    elif recorded_hash == current_hash:
        state, reason = (
            "current",
            "Run inputs reference this complete plan; execution status is separate.",
        )
    else:
        state, reason = "stale", "Geometry, operations, policy, or environmental inputs changed."
    return EvidenceReference(
        run_id=run_id,
        run_status=status,
        plan_hash=recorded_hash,
        applicability=state,
        reason=reason,
    )


def _objects(venue: Venue) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for floor in venue.floors:
        out[floor.floor_id] = {
            "walkable": floor.walkable,
            "elevation_m": floor.elevation_m,
        }
        items: list[Obstacle | Exit | Zone] = [*floor.obstacles, *floor.exits, *floor.zones]
        for item in items:
            out[item.id] = {**item.model_dump(), "floor_id": floor.floor_id}
    for stair in venue.stairs:
        out[stair.id] = stair.model_dump()
    return out


def _approvals(data: PlanData, ids: list[str], target: str) -> list[PlanIssue]:
    issues = []
    for aid in ids:
        approval = data.constraints.approvals.get(aid)
        if approval is None or approval.status != "approved":
            issues.append(
                fail("approval_required", f"{target} requires approved permission '{aid}'.", target)
            )
    return issues


def _access(data: PlanData, target: str) -> list[PlanIssue]:
    policy = data.constraints.objects.get(target)
    if policy is None:
        return []
    if policy.access == "unavailable":
        return [fail("access_unavailable", f"Access to '{target}' is unavailable.", target)]
    if policy.access == "restricted" and not policy.required_approvals:
        return [
            fail(
                "approval_required",
                f"Restricted access '{target}' needs a permission reference.",
                target,
            )
        ]
    return _approvals(data, policy.required_approvals, target)


def _construction(data: PlanData, policy: ObjectConstraint, target: str) -> list[PlanIssue]:
    if not data.constraints.allow_construction:
        return [
            fail(
                "construction_not_allowed",
                f"Construction at '{target}' is not permitted by this plan.",
                target,
            )
        ]
    if not policy.required_approvals:
        return [
            fail(
                "approval_required",
                f"Construction at '{target}' needs a permission reference.",
                target,
            )
        ]
    return _approvals(data, policy.required_approvals, target)


def edit_issues(venue: Venue, op: dict[str, Any]) -> list[PlanIssue]:
    if PLAN_KEY not in venue.extensions or not plan_data(venue).enforce_constraints:
        return []
    data = plan_data(venue)
    issues: list[PlanIssue] = []
    allowed = data.constraints.allowed_ops
    if allowed is not None and op["op"] not in allowed:
        issues.append(fail("operation_not_allowed", f"Operation '{op['op']}' is not permitted."))
    target = (
        op.get("target")
        or op.get("exit_id")
        or op.get("zone_id")
        or op.get("obstacle_id")
        or op.get("id")
    )
    if op["op"] == "set_stage_param":
        for floor in venue.floors:
            for obstacle in floor.obstacles:
                policy = data.constraints.objects.get(obstacle.id)
                if obstacle.kind == "stage" and policy:
                    if policy.locked:
                        issues.append(
                            fail("object_locked", f"Stage '{obstacle.id}' is locked.", obstacle.id)
                        )
                    elif policy.placement == "fixed":
                        issues.extend(_construction(data, policy, obstacle.id))
    for oid in {str(t) for t in (target, op.get("floor_id")) if t is not None}:
        policy = data.constraints.objects.get(oid)
        if policy and policy.locked and oid in venue.all_ids():
            issues.append(fail("object_locked", f"Object '{oid}' is locked.", oid))
    policy = data.constraints.objects.get(str(target))
    if (
        policy
        and policy.placement == "fixed"
        and op["op"]
        in {
            "move",
            "resize",
            "remove_exit",
            "remove_obstacle",
            "remove_zone",
        }
    ):
        issues.extend(_construction(data, policy, str(target)))
    if op["op"] == "add_exit":
        if policy is None or policy.origin != "proposed":
            issues.append(
                fail(
                    "new_exit_status_required",
                    "A new exit must be declared as proposed construction.",
                    str(target),
                )
            )
        else:
            issues.extend(_construction(data, policy, str(target)))
    if op["op"] == "block_exit" and not op.get("blocked", True):
        issues.extend(_access(data, str(target)))
    return issues


def transition_issues(before: Venue, after: Venue) -> list[PlanIssue]:
    """Enforce saved policies on full replacements as well as individual operations."""
    if PLAN_KEY not in before.extensions or not plan_data(before).enforce_constraints:
        return []
    old, new = plan_data(before), plan_data(after)
    policy: ObjectConstraint | None
    issues = []
    if PLAN_KEY not in after.extensions:
        issues.append(fail("policy_changed", "Edit bundles cannot remove the organizer plan."))
    # Only the explicit organizer configuration command may relax existing policy.
    old_policy = old.constraints.model_dump(exclude={"objects"})
    new_policy = new.constraints.model_dump(exclude={"objects"})
    if old_policy != new_policy:
        issues.append(fail("policy_changed", "Edit bundles cannot change organizer policy."))
    for oid, policy in old.constraints.objects.items():
        if new.constraints.objects.get(oid) != policy and oid in after.all_ids():
            issues.append(
                fail("policy_changed", f"Edit bundles cannot change policy for '{oid}'.", oid)
            )
    b, a = _objects(before), _objects(after)
    kinds = before.all_ids()
    allowed = old.constraints.allowed_ops
    for oid, obj in b.items():
        policy = old.constraints.objects.get(oid)
        floor_policy = old.constraints.objects.get(str(obj.get("floor_id", "")))
        if obj == a.get(oid):
            continue
        if allowed is not None:
            needed: set[str] = set()
            if oid not in a:
                needed.add(
                    {
                        "exit": "remove_exit",
                        "zone": "remove_zone",
                        "obstacle": "remove_obstacle",
                    }.get(kinds[oid], "unsupported_change")
                )
            else:
                if obj.get("people") != a[oid].get("people"):
                    needed.add("set_people")
                if obj.get("blocked") != a[oid].get("blocked"):
                    needed.add("block_exit")
                if obj.get("polygon") != a[oid].get("polygon"):
                    old_points, new_points = obj.get("polygon", []), a[oid].get("polygon", [])
                    deltas = {
                        (round(x2 - x1, 6), round(y2 - y1, 6))
                        for (x1, y1), (x2, y2) in zip(old_points, new_points, strict=False)
                    }
                    translation = len(old_points) == len(new_points) and len(deltas) == 1
                    needed.add("move" if translation else "resize")
                if kinds[oid] in {"floor", "stair"}:
                    needed.add("unsupported_change")
            for operation in needed - set(allowed):
                issues.append(
                    fail(
                        "operation_not_allowed",
                        f"Change to '{oid}' requires disallowed operation '{operation}'.",
                        oid,
                    )
                )
        if (policy and policy.locked) or (floor_policy and floor_policy.locked):
            issues.append(fail("object_locked", f"Object '{oid}' or its floor is locked.", oid))
        geometry_fields = {
            "polygon",
            "line",
            "width_m",
            "height_m",
            "walkable",
            "elevation_m",
            "floor_id",
            "top_polygon",
            "bottom_polygon",
            "length_m",
        }
        changed_geometry = oid not in a or any(obj.get(k) != a[oid].get(k) for k in geometry_fields)
        if policy and policy.placement == "fixed" and changed_geometry:
            issues.extend(_construction(old, policy, oid))
    exits_before = {e.id for f in before.floors for e in f.exits}
    if before.stage != after.stage:
        if allowed is not None and "set_stage_param" not in allowed:
            issues.append(
                fail("operation_not_allowed", "Stage parameter changes are not permitted.")
            )
        for floor in before.floors:
            for obstacle in floor.obstacles:
                policy = old.constraints.objects.get(obstacle.id)
                if obstacle.kind == "stage" and policy:
                    if policy.locked:
                        issues.append(
                            fail("object_locked", f"Stage '{obstacle.id}' is locked.", obstacle.id)
                        )
                    elif policy.placement == "fixed":
                        issues.extend(_construction(old, policy, obstacle.id))
    for oid in a.keys() - b.keys():
        if allowed is not None:
            kind = after.all_ids()[oid]
            operation = {"exit": "add_exit", "zone": "add_zone", "obstacle": "add_obstacle"}.get(
                kind, "unsupported_change"
            )
            if kind == "obstacle" and a[oid].get("line") and "add_obstacle" not in allowed:
                operation = "add_barrier_line"
            if operation not in allowed:
                issues.append(
                    fail(
                        "operation_not_allowed",
                        f"Adding '{oid}' requires disallowed operation '{operation}'.",
                        oid,
                    )
                )
        policy = old.constraints.objects.get(str(a[oid].get("floor_id", "")))
        if policy and policy.locked:
            issues.append(fail("object_locked", f"Floor of '{oid}' is locked.", oid))
    if not new.enforce_constraints:
        issues.append(fail("policy_changed", "Edit bundles cannot disable organizer constraints."))
    if before.location != after.location and allowed is not None and "set_event" not in allowed:
        issues.append(fail("operation_not_allowed", "Event/location changes are not permitted."))
    for floor in after.floors:
        for exit_ in floor.exits:
            if exit_.id not in exits_before:
                policy = new.constraints.objects.get(exit_.id)
                if policy is None or policy.origin != "proposed":
                    issues.append(
                        fail(
                            "new_exit_status_required",
                            "A new exit must be declared as proposed construction.",
                            exit_.id,
                        )
                    )
                else:
                    issues.extend(_construction(new, policy, exit_.id))
    return issues


def event_issues(venue: Venue, event: ScenarioEventIn, registry: Registry) -> list[PlanIssue]:
    if not registry.has("ScenarioEvent", event.type):
        return [fail("unknown_event", f"Unknown scenario event '{event.type}'.")]
    spec = registry.event(event.type)
    try:
        params = spec.params_model.model_validate(event.model_dump())
        return [fail("invalid_event_reference", p) for p in spec.validate_refs(venue, params)]
    except ValidationError as exc:
        return [fail("invalid_event", str(exc))]


def _action_issues(
    venue: Venue, data: PlanData, action: PlanAction, registry: Registry
) -> list[PlanIssue]:
    issues = _approvals(data, action.required_approvals, action.action_id)
    refs = set(action.target_ids)
    if action.event:
        issues.extend(event_issues(venue, action.event, registry))
        event = action.event.model_dump()
        refs.update(
            str(event[k])
            for k in ("exit_id", "zone_id", "from_exit_id", "to_exit_id", "target_zone_id")
            if event.get(k)
        )
        if action.event.type == "staggered_release" and action.end_s < action.start_s + float(
            event.get("delay_s", 0)
        ):
            issues.append(
                fail(
                    "action_interval_too_short",
                    "Staff must cover the entire staggered-release delay.",
                    action.action_id,
                )
            )
        if action.event.type in STAFF_MEASURES and data.constraints.require_staff_for_measures:
            staff = sum(
                r.quantity
                for r in action.resources
                if r.resource_id in data.constraints.resources
                and data.constraints.resources[r.resource_id].kind == "staff"
            )
            if staff < 1:
                issues.append(
                    fail(
                        "staff_required",
                        f"Action '{action.action_id}' needs a staff allocation.",
                        action.action_id,
                    )
                )
    for oid in sorted(refs):
        if oid not in venue.all_ids():
            issues.append(
                fail(
                    "unknown_action_target",
                    f"Unknown action target '{oid}'.",
                    action.action_id,
                    oid,
                )
            )
        else:
            issues.extend(_access(data, oid))
    for allocation in action.resources:
        pool = data.constraints.resources.get(allocation.resource_id)
        if pool is None:
            issues.append(
                fail(
                    "unknown_resource",
                    f"Unknown resource '{allocation.resource_id}'.",
                    action.action_id,
                )
            )
        elif action.start_s < pool.available_from_s or action.end_s > pool.available_until_s:
            issues.append(
                fail(
                    "resource_unavailable",
                    f"'{allocation.resource_id}' is unavailable for the full action interval.",
                    action.action_id,
                )
            )
    return issues


def validate_plan(venue: Venue, registry: Registry) -> PlanData:
    # Scene inspection uses the legacy venue hash from venue_ops; defer this import
    # so venue_ops can also call the shared plan validator without an import cycle.
    from api.core.scene import SceneInputError, scene_snapshot

    data = plan_data(venue)
    if PLAN_KEY not in venue.extensions:
        return data
    issues: list[PlanIssue] = []
    try:
        scene_snapshot(venue)
    except SceneInputError as exc:
        issues.extend(fail(i.code, i.message, *i.target_ids) for i in exc.issues)
    plan_hash(venue)  # rejects nonfinite nested event or extension JSON
    ids = venue.all_ids()
    policy: ObjectConstraint | None
    for oid, policy in data.constraints.objects.items():
        if oid not in ids:
            issues.append(
                fail("unknown_policy_object", f"Unknown constrained object '{oid}'.", oid)
            )
        for aid in policy.required_approvals:
            if aid not in data.constraints.approvals:
                issues.append(fail("unknown_approval", f"Unknown permission '{aid}'.", oid))
    for floor in venue.floors if data.enforce_constraints else []:
        for exit_ in floor.exits:
            policy = data.constraints.objects.get(exit_.id)
            if not exit_.blocked:
                issues.extend(_access(data, exit_.id))
                if policy and policy.origin == "proposed":
                    issues.extend(_construction(data, policy, exit_.id))
    actions = {a.action_id: a for a in data.actions}
    if len(actions) != len(data.actions):
        issues.append(fail("duplicate_action_id", "Action IDs must be unique."))
    graph: dict[str, list[str]] = {}
    for action in data.actions:
        issues.extend(_action_issues(venue, data, action, registry))
        graph[action.action_id] = action.depends_on
        for dep in action.depends_on:
            if dep not in actions:
                issues.append(
                    fail(
                        "missing_dependency",
                        f"Action '{action.action_id}' requires missing action '{dep}'.",
                        action.action_id,
                    )
                )
            elif actions[dep].end_s > action.start_s:
                issues.append(
                    fail(
                        "dependency_not_completed",
                        f"'{dep}' must finish before '{action.action_id}' starts.",
                        action.action_id,
                        dep,
                    )
                )
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(aid: str) -> None:
        if aid in visiting:
            issues.append(fail("dependency_cycle", "Action dependencies contain a cycle.", aid))
            return
        if aid in visited:
            return
        visiting.add(aid)
        for dep in graph.get(aid, []):
            visit(dep)
        visiting.remove(aid)
        visited.add(aid)

    for aid in graph:
        visit(aid)
    for rid, pool in data.constraints.resources.items():
        changes: list[tuple[float, int]] = []
        for action in data.actions:
            quantity = sum(r.quantity for r in action.resources if r.resource_id == rid)
            if quantity:
                changes.extend([(action.start_s, quantity), (action.end_s, -quantity)])
        used = 0
        for at_s, delta in sorted(changes):  # end before start at equal timestamps
            used += delta
            if used > pool.count:
                issues.append(
                    fail(
                        "resource_overallocated",
                        f"'{rid}' needs {used} units at {at_s:g} s; only {pool.count} available.",
                        rid,
                    )
                )
                break
    if issues:
        raise PlanError(issues)
    return data


def saved_events(venue: Venue, registry: Registry) -> list[ScenarioEventIn]:
    return [a.event for a in validate_plan(venue, registry).actions if a.event is not None]


def validate_run_horizon(venue: Venue, horizon_s: float, registry: Registry) -> None:
    data = validate_plan(venue, registry)
    for action in data.actions:
        if (
            action.event
            and action.event.type in {"marshal_redirect", "one_way"}
            and action.end_s < horizon_s
        ):
            raise PlanError(
                [
                    fail(
                        "action_coverage_too_short",
                        f"Action '{action.action_id}' must cover {horizon_s:g} s; "
                        "this simulator does not end its effect automatically.",
                        action.action_id,
                    )
                ]
            )


def validate_operational(venue: Venue, events: list[ScenarioEventIn], registry: Registry) -> None:
    """Unallocated agent measures cannot bypass a configured organizer plan.

    Structured actions are submitted through the plan-bundle API. Saved actions are
    automatically included in runs; callers must not inject them a second time.
    """
    if PLAN_KEY in venue.extensions and plan_data(venue).enforce_constraints and events:
        raise PlanError(
            [
                fail(
                    "structured_actions_required",
                    "Submit operational measures as plan actions with resources and intervals.",
                )
            ]
        )
    issues = [p for event in events for p in event_issues(venue, event, registry)]
    if issues:
        raise PlanError(issues)


def append_legacy_measures(
    venue: Venue, events: list[ScenarioEventIn], registry: Registry
) -> Venue:
    """Persist old session measures explicitly without inventing staff allocations."""
    validate_operational(venue, events, registry)
    if not events:
        return venue
    data = plan_data(venue)
    data.enforce_constraints = False
    data.constraints.require_staff_for_measures = False
    known = {a.action_id for a in data.actions}
    for i, event in enumerate(events):
        aid = f"session_measure_{i + 1}"
        while aid in known:
            aid += "_"
        known.add(aid)
        payload = event.model_dump()
        end = max(3600.0, event.at_s + float(payload.get("delay_s", 0)) + 1)
        data.actions.append(
            PlanAction(action_id=aid, event=event, start_s=event.at_s, end_s=end, source="agent")
        )
    out = with_plan(venue, data)
    validate_plan(out, registry)
    return out
