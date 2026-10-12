"""Analytical constraints and plan identity; no LLM or crowd simulation required."""

from __future__ import annotations

import pytest

from api.agents.blue_team import check_fix
from api.core.extensions import Registry
from api.core.plan import PlanError, plan_data, plan_hash, validate_plan, with_plan
from api.core.venue_ops import apply_patch
from api.models import Venue, VenuePatch
from api.models.plan import ObjectConstraint, PlanData
from api.tests.test_scene import room


def organizer_plan(**changes: object) -> PlanData:
    payload = {
        "constraints": {
            "objects": {"E1": {"placement": "fixed"}},
            "resources": {
                "stewards": {"kind": "staff", "count": 2},
                "radios": {"kind": "equipment", "count": 1},
            },
        },
        **changes,
    }
    return PlanData.model_validate(payload)


def action(
    aid: str = "hold", *, start: float = 10, end: float = 30, quantity: int = 1, **changes: object
) -> dict:
    return {
        "action_id": aid,
        "event": {"type": "staggered_release", "zone_id": "Z1", "at_s": start, "delay_s": 10},
        "start_s": start,
        "end_s": end,
        "resources": [{"resource_id": "stewards", "quantity": quantity}],
        **changes,
    }


def configured(**changes: object) -> Venue:
    return with_plan(room(), organizer_plan(**changes))


def codes(exc: pytest.ExceptionInfo[PlanError]) -> set[str]:
    return {i.code for i in exc.value.issues}


def test_plan_identity_tracks_operations_and_policy_not_display_name(registry: Registry) -> None:
    venue = configured()
    original = plan_hash(venue)
    renamed = venue.model_copy(
        update={"name": "Another name", "venue_id": "another project"}, deep=True
    )
    assert plan_hash(renamed) == original
    changed = configured(actions=[action()])
    assert plan_hash(changed) != original
    assert validate_plan(changed, registry).actions[0].event.type == "staggered_release"
    data = plan_data(changed)
    data.constraints.resources["stewards"].count = 3
    assert plan_hash(with_plan(changed, data)) != plan_hash(changed)


@pytest.mark.parametrize(
    "op",
    [
        {"op": "move", "target": "E1", "dx": 0, "dy": 1},
        {"op": "resize", "target": "E1", "width_m": 3},
        {"op": "remove_exit", "exit_id": "E1"},
    ],
)
def test_fixed_exit_changes_require_construction(registry: Registry, op: dict) -> None:
    with pytest.raises(PlanError) as exc:
        apply_patch(configured(), VenuePatch.model_validate({"ops": [op]}), registry)
    assert "construction_not_allowed" in codes(exc)


def test_locked_floor_rejects_child_changes(registry: Registry) -> None:
    venue = configured()
    data = plan_data(venue)
    data.constraints.objects["F0"] = ObjectConstraint(locked=True)
    venue = with_plan(venue, PlanData.model_validate(data.model_dump()))
    with pytest.raises(PlanError) as exc:
        apply_patch(
            venue,
            VenuePatch.model_validate(
                {"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]}
            ),
            registry,
        )
    assert "object_locked" in codes(exc)


@pytest.mark.parametrize(
    "actions, expected",
    [
        ([action(resources=[])], "staff_required"),
        ([action(quantity=3)], "resource_overallocated"),
        ([action("a"), action("b"), action("c")], "resource_overallocated"),
        ([action(resources=[{"resource_id": "ghost", "quantity": 1}])], "unknown_resource"),
        ([action(end=15)], "action_interval_too_short"),
        ([action(depends_on=["ghost"])], "missing_dependency"),
        ([action("a", depends_on=["b"]), action("b", depends_on=["a"])], "dependency_cycle"),
        ([action("a"), action("a")], "duplicate_action_id"),
        ([action(target_ids=["ghost"])], "unknown_action_target"),
        ([action(required_approvals=["permit"])], "approval_required"),
        (
            [
                action(
                    event={
                        "type": "staggered_release",
                        "zone_id": "ghost",
                        "at_s": 10,
                        "delay_s": 10,
                    }
                )
            ],
            "invalid_event_reference",
        ),
        ([action(event={"type": "made_up", "at_s": 10})], "unknown_event"),
    ],
)
def test_invalid_actions_rejected(registry: Registry, actions: list, expected: str) -> None:
    with pytest.raises(PlanError) as exc:
        validate_plan(configured(actions=actions), registry)
    assert expected in codes(exc)


def test_resource_boundary_and_dependency_order(registry: Registry) -> None:
    actions = [
        action("a", start=0, end=20, quantity=2),
        action("b", start=20, end=40, quantity=2, depends_on=["a"]),
    ]
    assert len(validate_plan(configured(actions=actions), registry).actions) == 2
    actions[1]["start_s"] = 10
    actions[1]["event"]["at_s"] = 10
    with pytest.raises(PlanError) as exc:
        validate_plan(configured(actions=actions), registry)
    assert {"dependency_not_completed", "resource_overallocated"} <= codes(exc)


def test_equipment_and_staff_availability(registry: Registry) -> None:
    data = organizer_plan(
        actions=[
            action(
                resources=[
                    {"resource_id": "stewards", "quantity": 1},
                    {"resource_id": "radios", "quantity": 2},
                ]
            )
        ]
    )
    with pytest.raises(PlanError) as exc:
        validate_plan(with_plan(room(), data), registry)
    assert "resource_overallocated" in codes(exc)
    data.actions[0].resources.pop()
    data.constraints.resources["stewards"].available_from_s = 20
    with pytest.raises(PlanError) as exc:
        validate_plan(with_plan(room(), data), registry)
    assert "resource_unavailable" in codes(exc)


def test_access_policy_blocks_unapproved_open_exit(registry: Registry) -> None:
    data = organizer_plan()
    data.constraints.objects["E1"].access = "restricted"
    with pytest.raises(PlanError) as exc:
        validate_plan(with_plan(room(), data), registry)
    assert "approval_required" in codes(exc)
    data.constraints.objects["E1"].access = "unavailable"
    with pytest.raises(PlanError) as exc:
        validate_plan(with_plan(room(), data), registry)
    assert "access_unavailable" in codes(exc)


def test_rules_and_ai_share_constraint_validation(registry: Registry) -> None:
    venue = configured()
    ops = [{"op": "resize", "target": "E1", "width_m": 3}]
    assert any("Construction" in p for p in check_fix(registry, venue, ops, []))
    assert any(
        "plan actions" in p
        for p in check_fix(registry, venue, [], [{"type": "one_way", "exit_id": "E1"}])
    )


def test_approval_record_needs_attribution_and_nested_nan_rejected(registry: Registry) -> None:
    with pytest.raises(ValueError):
        organizer_plan(constraints={"approvals": {"permit": {"status": "approved"}}})
    data = organizer_plan(
        actions=[action(event={"type": "slowdown", "factor": float("nan"), "at_s": 10})]
    )
    with pytest.raises(PlanError) as exc:
        validate_plan(with_plan(room(), data), registry)
    assert "invalid_plan_json" in codes(exc)


def test_movable_zone_and_allowed_operations(registry: Registry) -> None:
    data = organizer_plan()
    data.constraints.allowed_ops = ["set_people"]
    venue = with_plan(room(), data)
    result = apply_patch(
        venue,
        VenuePatch.model_validate({"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]}),
        registry,
    )
    assert result.venue.total_people() == 10
    with pytest.raises(PlanError) as exc:
        apply_patch(
            venue,
            VenuePatch.model_validate({"ops": [{"op": "move", "target": "Z1", "dx": 1}]}),
            registry,
        )
    assert "operation_not_allowed" in codes(exc)
    data.constraints.allowed_ops = ["move"]
    result = apply_patch(
        with_plan(room(), data),
        VenuePatch.model_validate({"ops": [{"op": "move", "target": "Z1", "dx": 0.5}]}),
        registry,
    )
    assert result.venue.floors[0].zones[0].polygon[0][0] == 1.5
