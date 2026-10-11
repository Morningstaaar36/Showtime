"""P2-01 acceptance cases. Prepared for execution after implementation review."""

from __future__ import annotations

import math

import pytest

from api.core.scene import SceneInputError, inspect_scene, scene_snapshot
from api.core.templates import list_templates
from api.core.venue_ops import venue_hash
from api.models.scene import SceneFacts, SceneSnapshot
from api.models.venue import Exit, Floor, Obstacle, Stair, Venue, Zone


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def room() -> Venue:
    return Venue(
        venue_id="room",
        name="Analytic room",
        mode="indoor",
        floors=[
            Floor(
                floor_id="F0",
                walkable=rect(0, 0, 10, 8),
                exits=[Exit(id="E1", polygon=rect(9.6, 3, 9.98, 5), width_m=2)],
                zones=[Zone(id="Z1", polygon=rect(1, 2, 3, 6), people=20)],
            )
        ],
    )


def wall(venue: Venue, *, bottom: float = 0, top: float = 8) -> None:
    venue.floors[0].obstacles.append(
        Obstacle(
            id="wall",
            kind="wall",
            polygon=rect(4, bottom, 6, top),
        )
    )


def test_room_area_route_and_clearance() -> None:
    facts = inspect_scene(room(), project_id="project", version=1)
    assert facts.identity.venue_version == 1
    assert facts.floors[0].usable_area_m2 == pytest.approx(80)
    assert not any(issue.severity == "error" for issue in facts.issues)
    zone = facts.zones[0]
    assert zone.reachability == "reachable"
    assert zone.reachable_exit_ids == ["E1"]
    assert zone.parts[0].point_clearance_m == pytest.approx(2)
    route = zone.parts[0].route
    assert route.status == "computed"
    assert route.exit_id == "E1"
    assert route.distance_m == pytest.approx(7.79)
    assert facts.exits[0].nearest_obstacle_distance_m is None


def test_blocked_exit_retains_demand_and_marks_unreachable() -> None:
    venue = room()
    venue.floors[0].exits[0].blocked = True
    facts = inspect_scene(venue)
    assert facts.zones[0].people == 20
    assert facts.zones[0].reachability == "unreachable"
    assert facts.zones[0].parts[0].route.status == "unreachable"
    assert facts.zones[0].parts[0].route.distance_m is None
    assert not facts.exits[0].available_in_geometry


def test_partition_and_gap() -> None:
    venue = room()
    wall(venue)
    facts = inspect_scene(venue)
    assert len(facts.components) == 2
    assert facts.zones[0].reachability == "unreachable"
    venue.floors[0].obstacles[0].polygon = rect(4, 1, 6, 7)
    opened = inspect_scene(venue)
    assert len(opened.components) == 1
    assert opened.zones[0].reachability == "reachable"
    route = opened.zones[0].parts[0].route
    assert route.status == "computed"
    assert route.distance_m is not None and route.distance_m > 7.79


def test_split_occupied_zone_does_not_hide_trapped_portion() -> None:
    venue = room()
    wall(venue)
    venue.floors[0].zones[0].polygon = rect(2, 2, 8, 6)
    zone = inspect_scene(venue).zones[0]
    assert zone.reachability == "partially_reachable"
    assert zone.usable_area_m2 == pytest.approx(16)
    assert zone.reachable_area_m2 == pytest.approx(8)
    assert zone.unreachable_area_m2 == pytest.approx(8)
    assert zone.excluded_area_m2 == pytest.approx(8)
    assert sorted(len(part.reachable_exit_ids) for part in zone.parts) == [0, 1]
    assert zone.people == 20  # do not invent an allocation of people by area
    assert any(issue.code == "zone_partially_unreachable" for issue in inspect_scene(venue).issues)


def test_overlapping_obstacles_are_subtracted_once_and_holes_retained() -> None:
    venue = room()
    venue.floors[0].obstacles = [
        Obstacle(id="A", polygon=rect(4, 2, 6, 6)),
        Obstacle(id="B", polygon=rect(5, 2, 7, 6)),
    ]
    facts = inspect_scene(venue)
    assert facts.floors[0].obstacle_area_within_floor_m2 == pytest.approx(12)
    assert facts.floors[0].usable_area_m2 == pytest.approx(68)
    assert len(facts.components[0].geometry.holes) == 1


def test_zone_outside_scene_is_unplaced_not_zero_demand() -> None:
    venue = room()
    venue.floors[0].zones[0].polygon = rect(20, 20, 22, 22)
    zone = inspect_scene(venue).zones[0]
    assert zone.reachability == "unplaced"
    assert zone.placement == "unplaced"
    assert zone.people == 20
    assert zone.excluded_area_m2 == pytest.approx(4)
    assert not zone.parts


def test_partial_zone_placement_is_explicit() -> None:
    venue = room()
    venue.floors[0].zones[0].polygon = rect(-2, 3, 2, 5)
    facts = inspect_scene(venue)
    zone = facts.zones[0]
    assert zone.reachability == "reachable"  # only the modeled usable area
    assert zone.placement == "partially_placed"
    assert zone.excluded_area_m2 == pytest.approx(4)
    assert zone.people == 20
    assert any(issue.code == "zone_demand_not_fully_placed" for issue in facts.issues)


def test_complete_floor_obstruction_returns_empty_facts() -> None:
    venue = room()
    venue.floors[0].obstacles = [Obstacle(id="cover", polygon=rect(0, 0, 10, 8))]
    facts = inspect_scene(venue)
    assert facts.floors[0].usable_area_m2 == 0
    assert not facts.components
    assert facts.zones[0].reachability == "unplaced"


def test_directed_stairs_support_long_chains_and_cycles() -> None:
    venue = room()
    floor = venue.floors[0]
    venue.floors = [
        Floor(
            floor_id=f"F{i}",
            walkable=floor.walkable,
            exits=floor.exits if i == 0 else [],
            zones=floor.zones if i == 7 else [],
        )
        for i in range(8)
    ]
    venue.stairs = [
        Stair(
            id=f"S{i}",
            from_floor=f"F{i}",
            to_floor=f"F{i - 1}",
            top_polygon=rect(3, 3, 5, 5),
            bottom_polygon=rect(3, 3, 5, 5),
            width_m=1,
            length_m=3,
        )
        for i in range(1, 8)
    ]
    venue.stairs.append(
        Stair(
            id="cycle",
            from_floor="F0",
            to_floor="F1",
            top_polygon=rect(3, 3, 5, 5),
            bottom_polygon=rect(3, 3, 5, 5),
            width_m=1,
            length_m=3,
        )
    )
    facts = inspect_scene(venue)
    assert facts.zones[0].reachable_exit_ids == ["E1"]
    assert facts.zones[0].parts[0].route.distance_m == pytest.approx(28.79)
    assert not any(issue.code == "zone_no_exit" for issue in facts.issues)


def test_stairs_do_not_implicitly_enable_upward_travel() -> None:
    venue = room()
    venue.floors.append(Floor(floor_id="F1", walkable=rect(0, 0, 10, 8)))
    venue.floors[1].exits = venue.floors[0].exits
    venue.floors[0].exits = []
    venue.stairs = [
        Stair(
            id="S",
            from_floor="F1",
            to_floor="F0",
            top_polygon=rect(3, 3, 5, 5),
            bottom_polygon=rect(3, 3, 5, 5),
            width_m=1,
            length_m=3,
        )
    ]
    assert inspect_scene(venue).zones[0].reachability == "unreachable"


@pytest.mark.parametrize(
    "bad", ["duplicate", "bow_tie", "nonfinite", "unknown_floor", "short_stair"]
)
def test_invalid_geometry_is_explicitly_rejected(bad: str) -> None:
    venue = room()
    if bad == "duplicate":
        venue.floors[0].zones[0].id = "E1"
    elif bad == "bow_tie":
        venue.floors[0].walkable = [(0, 0), (10, 8), (0, 8), (10, 0)]
    elif bad == "nonfinite":
        venue.floors[0].walkable[0] = (math.nan, 0)
    else:
        stair = Stair(
            id="S",
            from_floor="F0",
            to_floor="unknown",
            top_polygon=rect(1, 1, 2, 2),
            bottom_polygon=rect(1, 1, 2, 2),
            width_m=1,
            length_m=3,
        )
        if bad == "short_stair":
            stair.to_floor = "F0"
            stair.top_polygon = [(1, 1), (2, 2)]
        venue.stairs = [stair]
    with pytest.raises(SceneInputError):
        inspect_scene(venue)


def test_provenance_hash_and_lossless_snapshot() -> None:
    venue = room()
    original = scene_snapshot(venue, version=1)
    assert all(obj.provenance.basis == "unknown" for obj in original.objects)
    venue.extensions["scene_metadata"] = {
        "fields": {
            "E1": {
                "width_m": {
                    "basis": "measured",
                    "source": "Organizer's tape measurement",
                    "recorded_at": "2026-10-11T10:00:00+06:00",
                }
            }
        }
    }
    updated = scene_snapshot(venue, version=2)
    assert updated.identity.scene_hash != original.identity.scene_hash
    assert updated.identity.venue_hash == original.identity.venue_hash
    assert SceneSnapshot.model_validate(updated.model_dump(mode="json")).venue == venue
    assert updated.objects[1].fields["width_m"].basis == "measured"


@pytest.mark.parametrize(
    "metadata",
    [
        {"objects": {"unknown": {"basis": "assumed"}}},
        {"fields": {"E1": {"nonexistent": {"basis": "assumed"}}}},
        {"objects": {"E1": {"basis": "measured"}}},
    ],
)
def test_invalid_provenance_rejected(metadata: dict[str, object]) -> None:
    venue = room()
    venue.extensions["scene_metadata"] = metadata
    with pytest.raises(SceneInputError):
        scene_snapshot(venue)


def test_inspection_is_deterministic_and_does_not_mutate_scene() -> None:
    venue = room()
    before = venue.model_dump(mode="json")
    first = inspect_scene(venue)
    assert first == inspect_scene(venue)
    assert venue.model_dump(mode="json") == before
    assert first.identity.venue_hash == venue_hash(venue)
    assert SceneFacts.model_validate(first.model_dump(mode="json")) == first


@pytest.mark.parametrize(
    ("limit", "reason"),
    [
        ("MAX_VISIBILITY_CHECKS", "visibility_check_budget_exceeded"),
        ("MAX_ROUTE_NODES_PER_COMPONENT", "component_node_budget_exceeded"),
    ],
)
def test_route_budget_does_not_erase_connectivity(
    monkeypatch: pytest.MonkeyPatch,
    limit: str,
    reason: str,
) -> None:
    monkeypatch.setattr(f"api.core.scene.{limit}", 0)
    facts = inspect_scene(room())
    assert facts.zones[0].reachability == "reachable"
    assert facts.zones[0].parts[0].route.status == "not_computed"
    assert facts.zones[0].parts[0].route.distance_m is None
    assert facts.route_budget_reason == reason


def test_routes_can_be_disabled() -> None:
    facts = inspect_scene(room(), include_routes=False)
    assert not facts.routes_computed
    assert facts.zones[0].reachability == "reachable"
    assert facts.zones[0].parts[0].route.reason == "routes_disabled"


def test_existing_templates_keep_full_geometry_and_ids() -> None:
    for venue in list_templates():
        snapshot = scene_snapshot(venue)
        assert snapshot.venue.model_dump(mode="json") == venue.model_dump(mode="json")
        assert {obj.id for obj in snapshot.objects} == set(venue.all_ids())
        assert inspect_scene(venue, include_routes=False).identity == snapshot.identity
