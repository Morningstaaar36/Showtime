"""Building ops: floors, stairs, walls, doors, rooms, people profiles, routes, event kind.

Each op must pass the PatchOp conformance suite (validate, apply without mutating its input,
undo exactly) and leave a venue whose zones still reach an exit.
"""

from __future__ import annotations

from typing import Any

import pytest
from shapely.geometry import Point
from shapely.geometry import Polygon as P

from api.core.extensions import Registry
from api.core.geometry import validate_venue
from api.core.venue_ops import PatchError, apply_patch
from api.models import Venue, VenuePatch
from api.tests.conformance.suites import check_patch_op


def patch(registry: Registry, venue: Venue, *ops: dict[str, Any]) -> Venue:
    return apply_patch(venue, VenuePatch.model_validate({"ops": list(ops)}), registry).venue


def errors(venue: Venue) -> list[str]:
    return [c.message for c in validate_venue(venue).checks if c.severity == "error"]


@pytest.mark.parametrize(
    "params",
    [
        {"op": "add_floor", "name": "Second floor", "height_m": 3.5},
        {"op": "remove_floor", "floor_id": "F1"},
        {"op": "add_wall", "floor_id": "F0", "points": [[20, 2], [20, 12]]},
        {
            "op": "add_room",
            "floor_id": "F0",
            "x": 2,
            "y": 2,
            "width_m": 6,
            "depth_m": 4,
            "door_wall": "north",
            "people": 10,
            "label": "Green room",
        },
        {
            "op": "set_zone_profile",
            "zone_id": "audience",
            "pre_movement_s": 90,
            "groups": [{"kind": "wheelchair", "share": 0.05}, {"kind": "staff", "share": 0.02}],
        },
        {"op": "add_route", "floor_id": "F0", "points": [[5, 10], [35, 10]], "label": "Parade"},
        {"op": "set_event_kind", "event_kind": "conference"},
    ],
)
def test_building_op_conformance(registry: Registry, hall: Venue, params: dict[str, Any]) -> None:
    check_patch_op(registry, hall, params)


def test_remove_stair_conformance_and_last_way_down(registry: Registry, hall: Venue) -> None:
    v = patch(
        registry,
        hall,
        {
            "op": "add_stair",
            "id": "stair_w",
            "from_floor": "F1",
            "to_floor": "F0",
            "x": 2.5,
            "y": 20,
            "run_m": 3,
            "direction": "south",
        },
    )
    check_patch_op(registry, v, {"op": "remove_stair", "stair_id": "stair_w"})
    with pytest.raises(PatchError, match="cannot reach"):  # the mezzanine's only way down
        patch(registry, hall, {"op": "remove_stair", "stair_id": "stair_ne"})


def test_add_floor_stacks_on_top_and_copies_walls(registry: Registry, school: Venue) -> None:
    v = patch(registry, school, {"op": "add_floor", "height_m": 4.0})
    top = v.floors[-1]
    assert top.elevation_m == pytest.approx(school.floors[-1].elevation_m + 4.0)
    assert top.walkable == school.floors[-1].walkable
    assert not top.exits and not top.zones
    walls = [o for o in school.floors[-1].obstacles if o.kind == "wall"]
    assert len([o for o in top.obstacles if o.kind == "wall"]) == len(walls)
    assert len({o.id for f in v.floors for o in f.obstacles}) == sum(
        len(f.obstacles) for f in v.floors
    ), "copied walls need their own ids"


def test_a_new_floor_with_a_stair_and_people_validates(registry: Registry, hall: Venue) -> None:
    v = patch(registry, hall, {"op": "add_floor", "floor_id": "F2", "height_m": 3.5})
    v = patch(
        registry,
        v,
        {
            "op": "add_stair",
            "from_floor": "F2",
            "to_floor": "F1",
            "x": 37.5,
            "y": 20,
            "width_m": 1.5,
            "run_m": 3,
            "direction": "south",
        },
        {
            "op": "add_zone",
            "floor_id": "F2",
            "id": "gallery",
            "polygon": [[5, 17], [25, 17], [25, 23], [5, 23]],
            "people": 40,
        },
    )
    stair = next(s for s in v.stairs if s.from_floor == "F2")
    assert stair.to_floor == "F1"
    assert stair.length_m > 3  # the slope is longer than the run
    assert errors(v) == []


def test_people_on_a_floor_without_a_stair_are_refused(registry: Registry, hall: Venue) -> None:
    v = patch(registry, hall, {"op": "add_floor", "floor_id": "F2", "copy_walls": False})
    with pytest.raises(PatchError, match="cannot reach"):
        patch(
            registry,
            v,
            {
                "op": "add_zone",
                "floor_id": "F2",
                "id": "gallery",
                "polygon": [[5, 17], [25, 17], [25, 23], [5, 23]],
                "people": 40,
            },
        )


def test_stairs_must_go_down(registry: Registry, hall: Venue) -> None:
    with pytest.raises(PatchError):
        patch(
            registry,
            hall,
            {"op": "add_stair", "from_floor": "F0", "to_floor": "F1", "x": 5, "y": 20},
        )


def test_remove_floor_takes_its_stairs_and_refuses_the_last(
    registry: Registry, hall: Venue, school: Venue
) -> None:
    v = patch(registry, hall, {"op": "remove_floor", "floor_id": "F1"})
    assert [f.floor_id for f in v.floors] == ["F0"]
    assert v.stairs == []
    with pytest.raises(PatchError):
        patch(registry, school, {"op": "remove_floor", "floor_id": school.floors[0].floor_id})


def test_a_door_splits_a_wall_into_a_passage(registry: Registry, hall: Venue) -> None:
    v = patch(
        registry,
        hall,
        {"op": "add_wall", "floor_id": "F0", "id": "wall_x", "points": [[20, 1], [20, 14]]},
    )
    v = patch(
        registry,
        v,
        {"op": "add_door", "floor_id": "F0", "wall_id": "wall_x", "x": 20, "y": 7, "width_m": 1.2},
    )
    pieces = [o for o in v.floors[0].obstacles if o.id.startswith("wall_x")]
    assert len(pieces) == 2
    assert all(o.kind == "wall" for o in pieces)
    ys = sorted(y for o in pieces for _, y in o.polygon)
    gap = [y for y in ys if 6.4 < y < 7.6]
    assert gap == [], "nothing of the wall may remain inside the door opening"
    with pytest.raises(PatchError):  # a door wider than the remaining piece
        patch(
            registry,
            v,
            {
                "op": "add_door",
                "floor_id": "F0",
                "wall_id": "wall_x",
                "x": 20,
                "y": 2,
                "width_m": 30,
            },
        )


def test_a_room_has_walls_a_door_and_people_who_can_leave(registry: Registry, hall: Venue) -> None:
    v = patch(
        registry,
        hall,
        {
            "op": "add_room",
            "floor_id": "F0",
            "id": "office",
            "x": 2,
            "y": 2,
            "width_m": 6,
            "depth_m": 4,
            "door_wall": "north",
            "people": 12,
        },
    )
    walls = [o for o in v.floors[0].obstacles if o.kind == "wall" and o.id.startswith("office")]
    assert walls, "the room is enclosed by walls"
    # the north wall has an opening: a point in the door gap is not covered by any wall

    door = Point(5, 6)
    assert not any(P(o.polygon).buffer(0.05).contains(door) for o in walls)
    assert any(P(o.polygon).distance(Point(2, 4)) < 0.2 for o in walls)  # west wall exists
    zone = next(z for z in v.floors[0].zones if z.people == 12)
    assert zone.polygon
    assert errors(v) == []


def test_zone_profile_sets_and_clears(registry: Registry, hall: Venue) -> None:
    v = patch(
        registry,
        hall,
        {
            "op": "set_zone_profile",
            "zone_id": "audience",
            "groups": [{"kind": "elderly", "share": 0.3}],
            "pre_movement_s": 120,
        },
    )
    z = next(z for z in v.floors[0].zones if z.id == "audience")
    assert z.groups[0].kind == "elderly" and z.pre_movement_s == 120
    v = patch(
        registry,
        v,
        {"op": "set_zone_profile", "zone_id": "audience", "pre_movement_s": None, "groups": []},
    )
    z = next(z for z in v.floors[0].zones if z.id == "audience")
    assert z.pre_movement_s is None and z.groups == []
    with pytest.raises(PatchError):
        patch(
            registry,
            v,
            {
                "op": "set_zone_profile",
                "zone_id": "audience",
                "groups": [{"kind": "bed", "share": 0.7}, {"kind": "staff", "share": 0.6}],
            },
        )


def test_removing_a_route_frees_the_zones_that_followed_it(registry: Registry, hall: Venue) -> None:
    v = patch(
        registry,
        hall,
        {"op": "add_route", "floor_id": "F0", "id": "parade", "points": [[5, 10], [35, 10]]},
    )
    v = patch(registry, v, {"op": "set_zone_profile", "zone_id": "audience", "route_id": "parade"})
    assert next(z for z in v.floors[0].zones if z.id == "audience").route_id == "parade"
    v = patch(registry, v, {"op": "remove_route", "route_id": "parade"})
    assert v.routes == []
    assert next(z for z in v.floors[0].zones if z.id == "audience").route_id is None
    with pytest.raises(PatchError):
        patch(registry, v, {"op": "set_zone_profile", "zone_id": "audience", "route_id": "nowhere"})


def test_event_kind_is_set_and_validated(registry: Registry, hall: Venue) -> None:
    assert (
        patch(registry, hall, {"op": "set_event_kind", "event_kind": "hospital"}).event_kind
        == "hospital"
    )
    with pytest.raises(PatchError):
        patch(registry, hall, {"op": "set_event_kind", "event_kind": "spaceport"})


def test_people_nine_storeys_up_can_still_reach_an_exit(registry: Registry, hall: Venue) -> None:
    """Reachability follows any number of stairs (it used to give up after five)."""
    v = hall
    for i in range(2, 9):
        v = patch(registry, v, {"op": "add_floor", "floor_id": f"F{i}", "copy_walls": False})
        v = patch(
            registry,
            v,
            {"op": "add_stair", "id": f"stair_{i}", "from_floor": f"F{i}",
             "to_floor": f"F{i - 1}", "x": 37.5 if i % 2 else 31.5, "y": 20, "run_m": 3,
             "direction": "south"},
        )  # fmt: skip
    v = patch(
        registry,
        v,
        {
            "op": "add_zone",
            "floor_id": "F8",
            "id": "roof_bar",
            "polygon": [[5, 17], [25, 17], [25, 23], [5, 23]],
            "people": 30,
        },
    )
    assert len(v.floors) == 9 and errors(v) == []
