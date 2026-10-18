"""Designer: descriptions with storeys, basements, rooms and atriums → solved, checked venues.

Hand-written specs stand in for what the model writes for each probe description
(docs: the designer probe); the solver must build every one exactly and route everyone out.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from typing import Any

import pytest

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.agents.venue_designer import check_spec, design_venue
from api.core.estimates import capacity
from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.core.settings import ROOT_DIR, Settings
from api.core.tier1 import run_tier1
from api.core.venue_builder import build_venue
from api.models import Venue
from api.models.venue_spec import VenueSpec

S = Settings(_env_file=None)


def _door(wall: str, width: float = 2.0, position: float = 0.5, **kw: Any) -> dict[str, Any]:
    return {"wall": wall, "width_m": width, "position": position, **kw}


OFFICE: dict[str, Any] = {
    "name": "Office",
    "width_m": 40,
    "depth_m": 20,
    "exits": [_door("south", 2.4, label="Main exit")],
    "building": {
        "storeys": 5,
        "use": "office",
        "people_per_floor": 150,
        "stairs": [{"place": "west"}, {"place": "east"}],
    },
}
HOSPITAL: dict[str, Any] = {
    "name": "Hospital",
    "width_m": 60,
    "depth_m": 25,
    "exits": [_door("south", 2.4, label="Main entrance")],
    "building": {
        "storeys": 4,
        "use": "hospital",
        "interior": "rooms",
        "people_per_floor": 40,
        "stairs": [{"place": "west", "width_m": 1.5}, {"place": "east", "width_m": 1.5}],
    },
}
MALL: dict[str, Any] = {
    "name": "Mall",
    "width_m": 60,
    "depth_m": 40,
    "exits": [_door(w, 3.0) for w in ("north", "south", "east", "west")],
    "features": [
        {"kind": "escalator", "label": "Escalators", "place": "centre", "width_m": 8, "depth_m": 3}
    ],
    "building": {"storeys": 3, "use": "mall", "interior": "atrium", "people_per_floor": 600},
}
SCHOOL: dict[str, Any] = {
    "name": "School",
    "width_m": 40,
    "depth_m": 18,
    "exits": [_door("west"), _door("east")],
    "building": {
        "storeys": 3,
        "use": "school",
        "interior": "rooms",
        "rooms_per_floor": 8,
        "people_per_floor": 320,
        "stairs": [{"place": "west"}, {"place": "east"}],
    },
}
NIGHTCLUB: dict[str, Any] = {
    "name": "Club",
    "width_m": 25,
    "depth_m": 15,
    "exits": [
        _door("south", 1.0, label="Stair to street", level=-1),
        _door("north", 0.9, label="Fire exit", level=-1),
    ],
    "features": [{"kind": "bar", "label": "Bar", "place": "east", "width_m": 6, "depth_m": 2}],
    "building": {"storeys": 1, "basements": 1, "levels": [{"level": -1, "people": 300}]},
}
CONCERT: dict[str, Any] = {
    "name": "Rock concert",
    "mode": "outdoor",
    "width_m": 120,
    "depth_m": 80,
    "stage": {"wall": "north", "width_m": 24, "depth_m": 10},
    "front_barrier": True,
    "exits": [_door("south", 6.0, p, label="South gate") for p in (0.2, 0.5, 0.8)],
    "zones": [{"label": "Fans", "people": 8000, "region": "whole"}],
    "features": [
        {"kind": "bar", "place": "east"},
        {"kind": "bar", "place": "east"},
        {"kind": "toilets", "place": "east"},
    ],
}
PANDAL: dict[str, Any] = {
    "name": "Durga Puja pandal",
    "mode": "outdoor",
    "width_m": 50,
    "depth_m": 40,
    "stage": {"wall": "center", "width_m": 10, "depth_m": 8},
    "exits": [_door("west", 4.0, label="Entry gate"), _door("east", 4.0, label="Exit gate")],
    "zones": [{"label": "Visitors", "people": 3000, "region": "whole"}],
}
CONVOCATION: dict[str, Any] = {
    "name": "Convocation hall",
    "width_m": 50,
    "depth_m": 40,
    "stage": {"wall": "north", "width_m": 20, "depth_m": 8},
    "exits": [
        *[_door("south", 1.8, p) for p in (0.2, 0.4, 0.6, 0.8)],
        _door("east", 1.2, label="Fire exit"),
        _door("west", 1.2, label="Fire exit"),
    ],
    "zones": [{"label": "Graduates and guests", "people": 2000, "region": "whole"}],
}
HOTEL: dict[str, Any] = {
    "name": "Hotel",
    "width_m": 45,
    "depth_m": 18,
    "exits": [_door("south", 2.4, label="Main entrance"), _door("north", 1.2, label="Service")],
    "building": {
        "storeys": 10,
        "use": "residential",
        "interior": "rooms",
        "room_label": "Guest rooms",
        "people_per_floor": 60,
        "levels": [{"level": 0, "people": 120, "name": "Lobby"}],
        "stairs": [{"place": "west"}, {"place": "east"}],
    },
}
CONCOURSE: dict[str, Any] = {
    "name": "Stadium concourse",
    "width_m": 150,
    "depth_m": 15,
    "exits": [_door("south", 4.0, p, label="Gate") for p in (0.15, 0.4, 0.6, 0.85)],
    "features": [{"kind": "booth", "label": "Kiosks", "place": "north", "width_m": 20, "level": 1}],
    "building": {
        "storeys": 2,
        "use": "sports",
        "levels": [{"level": 1, "people": 2500, "name": "Concourse"}],
        "stairs": [{"place": "west", "width_m": 2.4}, {"place": "east", "width_m": 2.4}]
        + [{"place": "centre", "width_m": 2.4}] * 2,
    },
}
MOSQUE: dict[str, Any] = {
    "name": "Mosque",
    "width_m": 40,
    "depth_m": 30,
    "exits": [_door("east", 2.4), _door("north", 2.4)],
    "zones": [{"label": "Prayer hall", "people": 1200, "region": "whole"}],
    "upper_floor": {"along": "south", "depth_m": 10, "people": 300, "label": "Women's gallery"},
}
METRO: dict[str, Any] = {
    "name": "Metro station",
    "width_m": 120,
    "depth_m": 14,
    "exits": [_door("west", 3.0, label="West exit"), _door("east", 3.0, label="East exit")],
    "building": {
        "storeys": 1,
        "basements": 1,
        "use": "transit",
        "levels": [
            {"level": -1, "people": 800, "name": "Platform"},
            {"level": 0, "name": "Ticket hall"},
        ],
        "stairs": [{"place": p, "width_m": 3.0} for p in ("west", "centre", "east")],
    },
}

# spec, floors, stairs (flights), people per floor in venue order (street level first)
CASES: dict[str, tuple[dict[str, Any], int, int, list[int]]] = {
    "office": (OFFICE, 5, 8, [150] * 5),
    "hospital": (HOSPITAL, 4, 6, [40] * 4),
    "mall": (MALL, 3, 4, [600] * 3),
    "school": (SCHOOL, 3, 4, [320] * 3),
    "nightclub": (NIGHTCLUB, 2, 2, [0, 300]),
    "concert": (CONCERT, 1, 0, [8000]),
    "pandal": (PANDAL, 1, 0, [3000]),
    "convocation": (CONVOCATION, 1, 0, [2000]),
    "hotel": (HOTEL, 10, 18, [120, *[60] * 9]),
    "concourse": (CONCOURSE, 2, 4, [0, 2500]),
    "mosque": (MOSQUE, 2, 1, [1200, 300]),
    "metro": (METRO, 2, 3, [0, 800]),
}


def _errors(v: Venue) -> list[str]:
    return [c.message for c in validate_venue(v).checks if c.severity == "error"]


@pytest.mark.parametrize("case", list(CASES))
def test_described_venue_builds_exactly_and_everyone_gets_out(
    case: str, registry: Registry
) -> None:
    raw, floors, flights, per_floor = CASES[case]
    spec = VenueSpec.model_validate(raw)
    built, problems = check_spec(spec)
    v = built.venue
    assert problems == [] and _errors(v) == []
    assert len(v.floors) == floors and len(v.stairs) == flights
    assert [sum(z.people for z in f.zones) for f in v.floors] == per_floor
    assert v.total_people() == spec.total_people() == sum(per_floor)
    labels = [e.label for f in v.floors for e in f.exits]
    assert len(set(labels)) == len(labels), "every exit has its own name"
    t1 = run_tier1(v, [], registry, S)
    assert t1.metrics.agents_not_evacuated == 0 and t1.status == "ok"
    assert not any("no usable route" in n for n in t1.notes)


def test_office_storeys_stack_with_stairs_at_both_ends() -> None:
    v = build_venue(VenueSpec.model_validate(OFFICE)).venue
    assert [f.floor_id for f in v.floors] == ["F0", "F1", "F2", "F3", "F4"]
    assert [f.elevation_m for f in v.floors] == [0, 3.5, 7, 10.5, 14]
    assert v.floors[0].exits and not any(f.exits for f in v.floors[1:])
    xs = sorted({round(geo.centroid(s.top_polygon)[0]) for s in v.stairs})
    assert len(xs) == 2 and xs[0] < 10 and xs[1] > 30, "one core near each end"
    assert v.event_kind == "office" and v.extensions["building"]["levels"] == 5


def test_rooms_follow_the_description() -> None:
    school = build_venue(VenueSpec.model_validate(SCHOOL)).venue
    f0 = school.floors[0]
    assert [z.label for z in f0.zones] == [f"Classroom {i}" for i in range(1, 9)]
    assert [z.people for z in f0.zones] == [40] * 8, "8 classrooms of 40"
    assert sum(o.kind == "wall" for o in f0.obstacles) >= 8
    # doors in a long wall open into a room, never onto the wall between two rooms
    north = dict(SCHOOL, exits=[_door("north", 2.4, p) for p in (0.25, 0.5)])
    v = build_venue(VenueSpec.model_validate(north)).venue
    assert [z.people for z in v.floors[0].zones] == [40] * 8
    hospital = build_venue(VenueSpec.model_validate(HOSPITAL)).venue
    assert hospital.floors[1].zones[0].label == "Ward A · 1st floor"
    assert {"bed", "staff"} <= {g.kind for g in hospital.floors[0].zones[0].groups}
    hotel = build_venue(VenueSpec.model_validate(HOTEL)).venue
    assert hotel.floors[3].zones[0].label.startswith("Guest rooms A")
    assert hotel.floors[0].name == "Lobby" and hotel.floors[0].zones[0].label.endswith("· Lobby")


def test_basement_exits_are_stairs_up_to_street_doors() -> None:
    res = build_venue(VenueSpec.model_validate(NIGHTCLUB))
    v = res.venue
    street, basement = v.floors
    assert (street.floor_id, basement.floor_id) == ("F0", "B1")
    assert basement.elevation_m == -3.5 and basement.name == "Basement"
    assert not basement.exits and [e.label for e in street.exits] == [
        "Stair to street",
        "Fire exit",
    ]
    # each stair rises from the basement and lands beside its own street door
    assert all(s.from_floor == "B1" and s.to_floor == "F0" for s in v.stairs)
    assert sorted(s.width_m for s in v.stairs) == [0.9, 1.0]
    for door in street.exits:
        near = min(
            geo.to_polygon(s.bottom_polygon).distance(geo.to_polygon(door.polygon))
            for s in v.stairs
        )
        assert near < 2.0
    assert [o.label for o in basement.obstacles] == ["Bar"], "features go where the people are"
    assert not street.zones


def test_atrium_is_open_to_below_and_escalators_run_through_every_level() -> None:
    v = build_venue(VenueSpec.model_validate(MALL)).venue
    voids = [[o for o in f.obstacles if o.label == "Atrium (open to below)"] for f in v.floors]
    assert [len(x) for x in voids] == [0, 1, 1]
    assert all(any(o.label == "Escalators" for o in f.obstacles) for f in v.floors)
    void = geo.to_polygon(voids[1][0].polygon)
    for z in v.floors[1].zones:
        assert geo.to_polygon(z.polygon).intersection(void).area < 0.5
    assert any(
        "Escalators are drawn as obstacles" in a for a in v.extensions["generated"]["assumptions"]
    )


def test_centre_stage_stands_in_the_middle_with_people_all_round() -> None:
    v = build_venue(VenueSpec.model_validate(PANDAL)).venue
    cx, cy = geo.centroid(v.floors[0].obstacles[0].polygon)
    assert abs(cx - 25) < 0.1 and abs(cy - 20) < 0.1
    zones = v.floors[0].zones
    assert len(zones) == 2 and sum(z.people for z in zones) == 3000  # two halves, no holes
    assert all(not geo.to_polygon(z.polygon).interiors for z in zones)


def test_repeated_exit_names_are_numbered() -> None:
    v = build_venue(VenueSpec.model_validate(CONCERT)).venue
    assert [e.label for e in v.floors[0].exits] == ["South gate 1", "South gate 2", "South gate 3"]
    hall = build_venue(VenueSpec.model_validate(CONVOCATION)).venue
    assert {"Fire exit 1", "Fire exit 2"} <= {e.label for e in hall.floors[0].exits}


def test_features_go_on_their_level_and_upper_exits_are_stairs_to_the_street() -> None:
    v = build_venue(VenueSpec.model_validate(CONCOURSE)).venue
    assert [o.label for o in v.floors[1].obstacles] == ["Kiosks"]
    assert len({tuple(s.top_polygon[0]) for s in v.stairs}) == 4, "four separate stairs"
    escape = dict(
        CONCOURSE, exits=[*CONCOURSE["exits"], _door("west", 1.4, label="Escape stair", level=1)]
    )
    v2 = build_venue(VenueSpec.model_validate(escape)).venue
    assert not v2.floors[1].exits and "Escape stair" in [e.label for e in v2.floors[0].exits]
    extra = [s for s in v2.stairs if s.width_m == 1.4]
    assert len(extra) == 1 and (extra[0].from_floor, extra[0].to_floor) == ("F1", "F0")
    # in a 4-storey office an escape stair from the top floor serves every floor below it
    office = dict(OFFICE, exits=[*OFFICE["exits"], _door("north", 1.0, label="Escape", level=3)])
    v3 = build_venue(VenueSpec.model_validate(office)).venue
    assert sorted(s.from_floor for s in v3.stairs if s.width_m == 1.0) == ["F1", "F2", "F3"]


def test_an_empty_storey_on_top_of_a_basement_venue_is_left_out() -> None:
    metro = dict(METRO, building={**METRO["building"], "storeys": 2})
    res = build_venue(VenueSpec.model_validate(metro))
    assert [f.floor_id for f in res.venue.floors] == ["F0", "B1"]
    assert any("Dropped the empty 1st floor" in n for n in res.notes)


def test_headcount_problems_are_sent_back_with_a_fix() -> None:
    zones_only = dict(OFFICE, building={**OFFICE["building"], "people_per_floor": None})
    zones_only["zones"] = [{"label": "Staff", "people": 750}]
    built, problems = check_spec(VenueSpec.model_validate(zones_only))
    assert any("people_per_floor" in p and "5 levels" in p for p in problems)
    assert built.venue.total_people() == 750  # spread evenly meanwhile
    wrong = dict(
        NIGHTCLUB, building={**NIGHTCLUB["building"], "levels": [{"level": -2, "people": 300}]}
    )
    _, problems = check_spec(VenueSpec.model_validate(wrong))
    assert any("lists level -2" in p and "2 levels, -1 to 0" in p for p in problems)
    outdoor = dict(OFFICE, mode="outdoor", zones=[{"people": 100}])
    _, problems = check_spec(VenueSpec.model_validate(outdoor))
    assert any("open-air site has one level" in p for p in problems)
    bad_level = dict(OFFICE, exits=[_door("south", level=7)])
    _, problems = check_spec(VenueSpec.model_validate(bad_level))
    assert any("levels run from 0 to 4" in p for p in problems)


def test_geometry_errors_name_the_zone_and_level_not_ids() -> None:
    crowded = dict(SCHOOL, building={**SCHOOL["building"], "people_per_floor": 3200})
    _, problems = check_spec(VenueSpec.model_validate(crowded))
    assert problems and all("f1_zone" not in p for p in problems)
    assert any("“Classroom 1” on the 1st floor" in p and "width_m" in p for p in problems)


def test_old_specs_without_a_building_still_build() -> None:
    old = {
        "width_m": 30,
        "depth_m": 20,
        "exits": [{"wall": "south"}],
        "zones": [{"people": 300}],
    }
    built, problems = check_spec(VenueSpec.model_validate(old))
    assert problems == [] and [f.floor_id for f in built.venue.floors] == ["F0"]
    _, problems = check_spec(VenueSpec.model_validate(dict(old, zones=[])))
    assert problems == ["No people: add a zone with the headcount."]


def test_one_open_level_is_built_as_a_hall_with_its_stage_front() -> None:
    hall = dict(CONVOCATION, zones=[], building={"storeys": 1, "people_per_floor": 2000})
    v = build_venue(VenueSpec.model_validate(hall)).venue
    assert len(v.floors) == 1 and v.total_people() == 2000
    assert v.floors[0].zones[0].label == "People" and v.floors[0].obstacles[0].kind == "stage"


def test_prompt_examples_build_cleanly() -> None:
    text = (ROOT_DIR / "api/agents/prompts/venue_designer.md").read_text()
    examples = re.findall(r'^Example: "(.*?)"\n(\{.*?\})\n\n', text, re.S | re.M)
    assert len(examples) >= 4
    for _, raw in examples:
        spec = VenueSpec.model_validate(json.loads(raw))
        built, problems = check_spec(spec)
        assert problems == [] and built.venue.total_people() == spec.total_people()


def test_capacity_counts_basement_people_on_the_stairs_up() -> None:
    v = build_venue(VenueSpec.model_validate(NIGHTCLUB)).venue
    from api.core.plugins import load_plugins

    reg = load_plugins(ROOT_DIR).registry
    cap = capacity(v, reg, S)
    assert cap.limited_by == "stairs", "two narrow stairs carry all 300 people"


def test_simulation_runs_a_basement_before_the_street_level() -> None:
    sys.path.insert(0, str(ROOT_DIR / "sim"))
    try:
        jps_build = importlib.import_module("jps_build")
    finally:
        sys.path.remove(str(ROOT_DIR / "sim"))
    club = build_venue(VenueSpec.model_validate(NIGHTCLUB)).venue.model_dump(mode="json")
    assert [f["floor_id"] for f in jps_build.floor_run_order(club)] == ["B1", "F0"]
    office = build_venue(VenueSpec.model_validate(OFFICE)).venue.model_dump(mode="json")
    assert [f["floor_id"] for f in jps_build.floor_run_order(office)] == [
        "F4",
        "F3",
        "F2",
        "F1",
        "F0",
    ]


# --- the agent: describe → solve → check → repair -------------------------------------------


async def test_designer_repairs_a_building_given_as_zones() -> None:
    first = dict(OFFICE, building={**OFFICE["building"], "people_per_floor": None})
    first["zones"] = [{"label": "Office staff", "people": 150, "region": "whole"}]
    llm = FakeLLM({"designer": [first, OFFICE]})
    out = await design_venue(
        AgentEnv(llm=llm, audit=False),
        "A 5-storey office building, 40 by 20 m, 150 people per floor, two stairwells at each end.",
    )
    assert len(llm.calls) == 2
    fix = llm.calls[1][1][-1]["content"]
    assert "people_per_floor" in fix and "building.levels" in fix
    assert out.status == "built" and out.venue is not None
    assert out.venue.total_people() == 750 and len(out.venue.floors) == 5
    assert out.problems == []


async def test_designer_keeps_a_basement_stair_as_the_way_out() -> None:
    llm = FakeLLM({"designer": [NIGHTCLUB]})
    out = await design_venue(AgentEnv(llm=llm, audit=False), "Nightclub in a basement ...")
    assert len(llm.calls) == 1 and out.status == "built" and out.venue is not None
    assert {s.from_floor for s in out.venue.stairs} == {"B1"}
    assert out.venue.total_people() == 300


async def test_designer_reports_what_is_still_wrong_after_one_repair() -> None:
    crowded = dict(SCHOOL, building={**SCHOOL["building"], "people_per_floor": 3200})
    llm = FakeLLM({"designer": [crowded, crowded]})
    out = await design_venue(AgentEnv(llm=llm, audit=False), "A packed school")
    assert len(llm.calls) == 2 and out.status == "needs_fixes"
    assert out.problems and "Classroom" in llm.calls[1][1][-1]["content"]


# --- what the real model wrote (scripts/design_probe.py --fixtures), replayed offline -------

LIVE = ROOT_DIR / "api" / "tests" / "fixtures" / "designer"
# floors, people per floor (by floor id); every other floor holds nobody
EXPECTED: dict[str, tuple[int, dict[str, int]]] = {
    "office": (5, {f"F{i}": 150 for i in range(5)}),
    "hospital": (4, {f"F{i}": 40 for i in range(4)}),
    "convocation": (1, {"F0": 2000}),
    "concert": (1, {"F0": 8000}),
    "mall": (3, {f"F{i}": 600 for i in range(3)}),
    "nightclub": (2, {"B1": 300}),
    "pandal": (1, {"F0": 3000}),
    "school": (3, {f"F{i}": 320 for i in range(3)}),
    "hotel": (10, {"F0": 120, **{f"F{i}": 60 for i in range(1, 10)}}),
    "concourse": (2, {"F1": 2500}),
    "mosque": (2, {"F0": 1200, "F1": 300}),
    "metro": (2, {"B1": 800}),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
async def test_recorded_model_specs_build_the_described_venue(
    name: str, registry: Registry
) -> None:
    data = json.loads((LIVE / f"{name}.json").read_text())
    llm = FakeLLM({"designer": [data["spec"]]})
    out = await design_venue(AgentEnv(llm=llm, audit=False), data["description"])
    assert out.status == "built" and out.problems == [] and out.venue is not None
    v = out.venue
    floors, people = EXPECTED[name]
    assert len(v.floors) == floors
    assert {f.floor_id: sum(z.people for z in f.zones) for f in v.floors} == {
        f.floor_id: people.get(f.floor_id, 0) for f in v.floors
    }
    labels = [e.label for f in v.floors for e in f.exits]
    assert len(set(labels)) == len(labels)
    t1 = run_tier1(v, [], registry, S)
    assert t1.metrics.agents_not_evacuated == 0
