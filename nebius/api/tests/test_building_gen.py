"""Multi-storey buildings from one imported floor (api/core/building_gen.py)."""

from __future__ import annotations

import pytest

from api.core.building_gen import (
    build_storeys,
    default_interior,
    floor_name,
    infer_use,
    map_levels,
)
from api.core.geometry import validate_venue
from api.models import Exit, Floor, Venue


def ground(walkable: list[tuple[float, float]], exits: list[Exit]) -> Venue:
    return Venue(
        venue_id="draft",
        name="Imported building",
        mode="indoor",
        floors=[Floor(floor_id="F0", name="Ground", walkable=walkable, exits=exits)],
    )


def door(x0: float, y0: float, x1: float, y1: float, i: int = 1) -> Exit:
    return Exit(id=f"door_{i}", polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], width_m=2.0)


@pytest.fixture
def block() -> Venue:
    """A 60 × 20 m block with doors at both short ends."""
    return ground(
        [(0, 0), (60, 0), (60, 20), (0, 20)],
        [door(0.02, 9, 0.42, 11, 1), door(59.58, 9, 59.98, 11, 2)],
    )


@pytest.fixture
def ell() -> Venue:
    """An L-shaped wing with doors on both arms."""
    return ground(
        [(0, 0), (50, 0), (50, 18), (18, 18), (18, 45), (0, 45)],
        [door(49.58, 8, 49.98, 10, 1), door(8, 44.58, 10, 44.98, 2)],
    )


def errors(v: Venue) -> list[str]:
    return [c.message for c in validate_venue(v).checks if c.severity == "error"]


@pytest.mark.parametrize("levels", [1, 3, 12])
def test_storeys_stack_and_connect(block: Venue, levels: int) -> None:
    v, _ = build_storeys(block, levels=levels, use="office", floor_height_m=3.5)
    assert [f.floor_id for f in v.floors] == [f"F{i}" for i in range(levels)]
    assert [f.elevation_m for f in v.floors] == [i * 3.5 for i in range(levels)]
    assert v.floors[0].exits and all(not f.exits for f in v.floors[1:])
    # two stairs from every upper floor to the one below
    for i in range(1, levels):
        down = [s for s in v.stairs if s.from_floor == f"F{i}"]
        assert len(down) == 2 and {s.to_floor for s in down} == {f"F{i - 1}"}
    assert all(f.zones for f in v.floors), "every floor has people"
    assert errors(v) == []
    assert v.event_kind == "office"
    assert v.extensions["building"]["levels"] == levels


def test_rooms_have_walls_doors_and_people(block: Venue) -> None:
    v, notes = build_storeys(block, levels=2, use="hospital", interior="rooms")
    f0 = v.floors[0]
    walls = [o for o in f0.obstacles if o.kind == "wall"]
    assert len(walls) >= 4
    assert len(f0.zones) >= 6, "rooms on both sides of the corridor"
    assert v.extensions["building"]["interior"] == "rooms"
    kinds = {g.kind for g in f0.zones[0].groups}
    assert {"bed", "staff"} <= kinds
    assert any("typical plan" in n for n in notes)
    assert errors(v) == []


def test_headcount_follows_use_and_is_split_over_floors(block: Venue) -> None:
    v, _ = build_storeys(block, levels=3, use="office", interior="open", people=600)
    assert v.total_people() == 600
    per_floor = [sum(z.people for z in f.zones) for f in v.floors]
    assert max(per_floor) - min(per_floor) <= 2
    school, _ = build_storeys(block, levels=1, use="school", interior="open")
    office, _ = build_storeys(block, levels=1, use="office", interior="open")
    assert school.total_people() > office.total_people()  # classrooms are denser


def test_l_shape_works(ell: Venue) -> None:
    v, _ = build_storeys(ell, levels=4, use="school")
    assert len(v.floors) == 4
    assert errors(v) == []


def test_shallow_building_falls_back_to_open_floors() -> None:
    thin = ground([(0, 0), (40, 0), (40, 8), (0, 8)], [door(0.02, 3, 0.42, 5)])
    v, notes = build_storeys(thin, levels=2, use="office", interior="rooms")
    assert v.extensions["building"]["interior"] == "open"
    assert any("too shallow" in n for n in notes)
    assert errors(v) == []


def test_unknown_use_is_refused(block: Venue) -> None:
    with pytest.raises(ValueError):
        build_storeys(block, levels=2, use="spaceport")  # type: ignore[arg-type]


def test_map_tags() -> None:
    assert infer_use({"building": "hospital"}) == "hospital"
    assert infer_use({"building": "yes", "amenity": "school"}) == "school"
    assert infer_use({"building": "yes", "amenity": "place_of_worship"}) == "religious"
    assert infer_use({"building": "yes"}) is None
    assert map_levels({"building:levels": "6"}) == 6
    assert map_levels({"building:levels": "2.5"}) == 2
    assert map_levels({"building:levels": "many"}) is None
    assert map_levels({"building:levels": "120"}) == 40
    assert default_interior("hospital") == "rooms" and default_interior("concert") == "open"
    assert [floor_name(i) for i in (0, 1, 2, 3, 11, 21)] == [
        "Ground",
        "1st floor",
        "2nd floor",
        "3rd floor",
        "11th floor",
        "21st floor",
    ]
