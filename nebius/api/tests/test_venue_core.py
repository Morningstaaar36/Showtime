"""Templates, geometry validation, patch ops (with undo) and the plugin registry."""

from __future__ import annotations

import pytest

from api.core.extensions import Registry
from api.core.geometry import validate_venue
from api.core.plugins import PluginHost
from api.core.templates import list_templates
from api.core.venue_ops import PatchError, apply_patch, venue_hash
from api.models import Venue, VenuePatch
from api.tests.conformance.suites import check_patch_op, check_scenario_event


def test_four_templates_validate() -> None:
    templates = list_templates()
    assert {t.venue_id for t in templates} == {
        "conference_hall_2f",
        "school_wing",
        "festival_field",
        "t_alley",
    }
    for t in templates:
        report = validate_venue(t)
        assert report.ok, (t.venue_id, [c.message for c in report.errors])


def test_template_headcounts() -> None:
    counts = {t.venue_id: t.total_people() for t in list_templates()}
    assert counts["conference_hall_2f"] == 1200
    assert counts["school_wing"] == 400
    assert counts["festival_field"] == 6000
    assert 1500 <= counts["t_alley"] <= 2500


def test_plugins_loaded(host: PluginHost) -> None:
    for pid in ("ops_core", "events_core"):
        st = host.statuses[pid]
        assert st.enabled and st.healthy, st.error
    ops = set(host.registry.keys("PatchOp"))
    assert {
        "move",
        "resize",
        "add_exit",
        "remove_exit",
        "block_exit",
        "add_obstacle",
        "remove_obstacle",
        "add_barrier_line",
        "set_people",
        "add_zone",
        "set_stage_param",
    } <= ops
    assert {
        "block_exit",
        "unblock_exit",
        "surge",
        "slowdown",
        "counterflow",
        "staggered_release",
        "marshal_redirect",
    } <= set(host.registry.keys("ScenarioEvent"))


PATCH_SAMPLES: list[tuple[str, dict[str, object]]] = [
    ("conference_hall_2f", {"op": "move", "target": "stage", "dx": 0, "dy": -2}),
    ("festival_field", {"op": "resize", "target": "stage", "width_m": 16}),
    ("conference_hall_2f", {"op": "resize", "target": "door_s1", "width_m": 3}),
    (
        "conference_hall_2f",
        {
            "op": "add_exit",
            "floor_id": "F0",
            "id": "door_e1",
            "wall": "east",
            "center": 8,
            "width_m": 2,
        },
    ),
    ("conference_hall_2f", {"op": "remove_exit", "exit_id": "door_s2"}),
    ("conference_hall_2f", {"op": "block_exit", "exit_id": "door_s2"}),
    (
        "festival_field",
        {
            "op": "add_obstacle",
            "floor_id": "F0",
            "id": "food_truck",
            "kind": "booth",
            "polygon": [[60, 30], [66, 30], [66, 33], [60, 33]],
        },
    ),
    ("festival_field", {"op": "remove_obstacle", "obstacle_id": "foh_tent"}),
    (
        "festival_field",
        {"op": "add_barrier_line", "floor_id": "F0", "id": "split", "points": [[40, 3], [40, 12]]},
    ),
    ("school_wing", {"op": "set_people", "zone_id": "room_1", "people": 30}),
    (
        "festival_field",
        {
            "op": "add_zone",
            "floor_id": "F0",
            "id": "vip",
            "polygon": [[62, 34], [70, 34], [70, 38], [62, 38]],
            "people": 60,
        },
    ),
    ("festival_field", {"op": "set_stage_param", "param": "ballast_kg_per_leg", "value": 3500}),
    (
        "festival_field",
        {"op": "set_event", "duration_h": 8, "alcohol": True, "audience": "standing"},
    ),
    (
        "conference_hall_2f",
        {
            "op": "add_exit",
            "floor_id": "F0",
            "id": "door_s9",
            "wall": "south",
            "center": 9.0,
            "width_m": 2.0,
        },
    ),  # on top of door_s1: moves along
]


@pytest.mark.parametrize(("template", "params"), PATCH_SAMPLES)
def test_patch_op_conformance(registry: Registry, template: str, params: dict[str, object]) -> None:
    from api.core.templates import get_template

    check_patch_op(registry, get_template(template), params)


EVENT_SAMPLES: list[dict[str, object]] = [
    {"type": "block_exit", "exit_id": "door_s1", "at_s": 60},
    {"type": "unblock_exit", "exit_id": "door_s1", "at_s": 120},
    {"type": "surge", "zone_id": "mezzanine", "extra_people": 200, "at_s": 0},
    {"type": "slowdown", "factor": 0.5, "at_s": 30},
    {"type": "counterflow", "exit_id": "door_s2", "people": 80, "at_s": 10},
    {"type": "staggered_release", "zone_id": "mezzanine", "delay_s": 45},
    {"type": "marshal_redirect", "to_exit_id": "door_s2", "from_exit_id": "door_s1", "at_s": 20},
]


@pytest.mark.parametrize("params", EVENT_SAMPLES)
def test_event_conformance(registry: Registry, hall: Venue, params: dict[str, object]) -> None:
    check_scenario_event(registry, hall, params)


def test_unknown_op_rejected(registry: Registry, hall: Venue) -> None:
    with pytest.raises(PatchError) as err:
        apply_patch(hall, VenuePatch.model_validate({"ops": [{"op": "teleport"}]}), registry)
    assert "Unknown operation" in err.value.problems[0]


def test_bad_params_rejected(registry: Registry, hall: Venue) -> None:
    with pytest.raises(PatchError):
        apply_patch(
            hall,
            VenuePatch.model_validate(
                {"ops": [{"op": "set_people", "zone_id": "audience", "people": -5}]}
            ),
            registry,
        )
    with pytest.raises(PatchError):
        apply_patch(
            hall,
            VenuePatch.model_validate({"ops": [{"op": "move", "target": "ghost", "dx": 1}]}),
            registry,
        )


def test_patch_is_atomic(registry: Registry, hall: Venue) -> None:
    before = venue_hash(hall)
    with pytest.raises(PatchError) as err:
        apply_patch(
            hall,
            VenuePatch.model_validate(
                {
                    "ops": [
                        {"op": "set_people", "zone_id": "audience", "people": 500},
                        {"op": "remove_exit", "exit_id": "nope"},
                    ]
                }
            ),
            registry,
        )
    assert err.value.op_index == 1
    assert venue_hash(hall) == before


def test_patch_rejects_new_geometry_errors(registry: Registry, hall: Venue) -> None:
    # removing both doors traps everyone
    with pytest.raises(PatchError) as err:
        apply_patch(
            hall,
            VenuePatch.model_validate(
                {
                    "ops": [
                        {"op": "remove_exit", "exit_id": "door_s1"},
                        {"op": "remove_exit", "exit_id": "door_s2"},
                    ]
                }
            ),
            registry,
        )
    assert any("exit" in p for p in err.value.problems)


def test_stage_cannot_be_removed(registry: Registry, field: Venue) -> None:
    with pytest.raises(PatchError):
        apply_patch(
            field,
            VenuePatch.model_validate({"ops": [{"op": "remove_obstacle", "obstacle_id": "stage"}]}),
            registry,
        )


def test_validation_flags_problems(hall: Venue) -> None:
    v = hall.model_copy(deep=True)
    v.floors[0].exits[0].polygon = [(100, 100), (102, 100), (102, 101), (100, 101)]
    v.floors[0].zones[0].people = 5000
    report = validate_venue(v)
    codes = {c.code for c in report.errors}
    assert "exit_outside" in codes
    assert "zone_overfull" in codes
    assert not report.ok


def test_zone_without_exit_detected(school: Venue) -> None:
    v = school.model_copy(deep=True)
    for e in v.floors[0].exits:
        e.blocked = True
    codes = {c.code for c in validate_venue(v).errors}
    assert "zone_no_exit" in codes or "no_open_exit" in codes


def test_mezzanine_reaches_exit_via_stair(hall: Venue) -> None:
    v = hall.model_copy(deep=True)
    v.stairs = []
    codes = {c.code for c in validate_venue(v).errors}
    assert "zone_no_exit" in codes  # mezzanine is trapped without its stair


def test_venue_hash_ignores_name(hall: Venue) -> None:
    v = hall.model_copy(deep=True)
    v.name = "Renamed"
    assert venue_hash(v) == venue_hash(hall)
    v.floors[0].zones[0].people += 1
    assert venue_hash(v) != venue_hash(hall)


def test_exit_on_wall_defaults_to_middle_and_explains_range() -> None:
    import pytest as _pytest

    from api.core.extensions.geometry import exit_on_wall

    room = [(0.0, 0.0), (40.0, 0.0), (40.0, 12.0), (0.0, 12.0)]
    rect = exit_on_wall(room, "east", None, 2.0)
    ys = [p[1] for p in rect]
    assert min(ys) == _pytest.approx(5.0) and max(ys) == _pytest.approx(7.0)
    with _pytest.raises(ValueError, match=r"runs from y = 0.0 to 12.0 m"):
        exit_on_wall(room, "east", 39.4, 2.0)


def test_new_exit_never_overlaps_an_existing_one(registry: Registry) -> None:
    from api.core.extensions import geometry as geo
    from api.core.templates import get_template
    from api.core.venue_ops import apply_patch
    from api.models import VenuePatch

    hall = get_template("conference_hall_2f")
    ops = [{"op": "add_exit", "floor_id": "F0", "id": f"door_e{i}", "wall": "east",
            "center": 12.5, "width_m": 3.0} for i in (1, 2)]  # fmt: skip
    v = apply_patch(hall, VenuePatch.model_validate({"ops": ops}), registry).venue
    polys = {e.id: geo.to_polygon(e.polygon) for e in v.floors[0].exits}
    assert not polys["door_e1"].intersects(polys["door_e2"])
