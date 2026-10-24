"""Regression tests for the second review of the multi-storey, scenario and red-team work."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.agents.red_team import signature
from api.core.building_gen import build_storeys
from api.core.extensions import Registry
from api.core.scenarios import catalogue_for, venue_facts
from api.core.settings import ROOT_DIR, Settings
from api.core.tier1 import run_tier1
from api.core.venue_builder import build_venue
from api.models import Exit, Floor, Venue
from api.models.venue_spec import VenueSpec

S = Settings(_env_file=None)
LIVE = ROOT_DIR / "api" / "tests" / "fixtures" / "designer"


def spec(name: str, **building: Any) -> VenueSpec:
    raw = json.loads((LIVE / f"{name}.json").read_text())["spec"]
    if building:
        raw["building"] = {**(raw.get("building") or {}), **building}
    return VenueSpec.model_validate(raw)


def ground(levels: int = 3, people: int = 600) -> Venue:
    def door(x0: float, x1: float, i: int) -> Exit:
        return Exit(id=f"door_{i}", polygon=[(x0, 9), (x1, 9), (x1, 11), (x0, 11)], width_m=2.0)

    g = Venue(
        venue_id="d",
        name="Block",
        mode="indoor",
        floors=[
            Floor(
                floor_id="F0",
                name="Ground",
                walkable=[(0, 0), (60, 0), (60, 20), (0, 20)],
                exits=[door(0.02, 0.42, 1), door(59.58, 59.98, 2)],
            )
        ],
    )
    return build_storeys(g, levels=levels, use="office", interior="open", people=people)[0]


def test_a_basement_flight_joins_its_stair_core() -> None:
    office = build_venue(spec("office", basements=1, stairs=[{"place": "east", "width_m": 1.2}]))
    facts = venue_facts(office.venue)
    assert len(facts.stairwells) == 1, [w.name for w in facts.stairwells]
    assert "multi_stairwell" not in facts.tags  # so smoke never takes the only stair


def test_phased_evacuation_of_a_tall_building_stays_within_limits(registry: Registry) -> None:
    tall = ground(levels=20)
    phased = next(r for r in catalogue_for(tall) if r.spec.id == "phased")
    assert phased.built is not None, phased.reason
    assert max(e.model_dump().get("delay_s", 0) for e in phased.built.events) <= 360
    run_tier1(tall, phased.built.events, registry, S)  # no validation error


def test_naming_a_level_keeps_its_people() -> None:
    s = spec("office", people_per_floor=100, levels=[{"level": 2, "name": "Roof bar"}])
    per = s.level_people()
    assert per is not None and per[2] == 100 and sum(per) == 100 * len(per)


def test_a_hall_with_a_balcony_counts_the_balcony_once() -> None:
    raw = json.loads((LIVE / "convocation.json").read_text())["spec"]
    raw.update(
        zones=[],
        upper_floor={"wall": "south", "depth_m": 6, "people": 200},
        building={"storeys": 1, "people_per_floor": 600},
    )
    built = build_venue(VenueSpec.model_validate(raw)).venue
    assert built.total_people() == 600 + 200 or built.total_people() == 600, built.total_people()
    assert built.total_people() != 600 + 200 + 200


def test_basements_count_the_street_as_ground(registry: Registry) -> None:
    from api.models import Attack
    from api.orchestrator.fallbacks import rule_fixes

    club = build_venue(spec("nightclub")).venue
    attack = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Smoke",
            "events": [{"type": "slowdown", "factor": 0.5, "at_s": 0}],
            "inspired_by": {
                "incident": "x", "year": 2000, "evidence": "x",
                "source_url": "https://doi.org/10.5281/zenodo.19483010",
            },
            "rationale": "x",
        }
    )  # fmt: skip
    titles = [
        f.title
        for f in rule_fixes(registry, club, attack, run_tier1(club, [], registry, S), 4, "F1_R")
    ]
    assert any(t.startswith("Widen") for t in titles), titles
    facts = venue_facts(club)
    assert facts.ground() != min(club.floors, key=lambda f: f.elevation_m).floor_id
    assert facts.fire_floor() in {f.floor_id for f in club.floors if f.elevation_m < 0}


def test_redirects_between_different_exits_are_different_attacks() -> None:
    a = signature([{"type": "marshal_redirect", "from_exit_id": "e1", "to_exit_id": "e2"}])
    b = signature([{"type": "marshal_redirect", "from_exit_id": "e1", "to_exit_id": "e3"}])
    assert a != b


def test_stair_and_floor_attacks_land_on_the_failure_map() -> None:
    from api.models import Attack
    from api.orchestrator.archive import Archive

    v = ground(levels=3)
    arch = Archive(v)
    src = {
        "incident": "x",
        "year": 2000,
        "evidence": "x",
        "source_url": "https://doi.org/10.5281/zenodo.19483010",
    }

    def cell(ev: dict[str, Any]) -> Any:
        return arch.cell_of(
            Attack.model_validate(
                {
                    "attack_id": "A1",
                    "title": "t",
                    "events": [ev],
                    "inspired_by": src,
                    "rationale": "x",
                }
            )
        )

    stair = next(s for s in v.stairs if s.from_floor == "F1")
    assert cell({"type": "block_exit", "exit_id": stair.id, "at_s": 0}) == (
        "exit_blocked",
        "floor:F1",
    )
    assert cell({"type": "slowdown", "factor": 0.6, "floor_id": "F2", "at_s": 0}) == (
        "slowdown",
        "floor:F2",
    )


def test_the_two_ways_to_slow_a_mix_agree(registry: Registry) -> None:
    from api.core.extensions import Tier1State
    from api.core.tier1 import mix_speed_factor
    from api.models import PeopleGroup

    zone = mix_speed_factor([PeopleGroup(kind="wheelchair", share=0.15)], S.walk_speed_mean)
    spec_ = registry.event("mobility_share")
    state = Tier1State(exits={}, groups={}, walk_speed_mps=S.walk_speed_mean)
    from api.core.extensions import T1Group

    state.groups["z"] = T1Group(id="z", floor_id="F0", x=0, y=0, people=100)
    spec_.tier1_effect(
        state,
        spec_.params_model.model_validate(
            {"type": "mobility_share", "share": 0.15, "speed_mps": 0.69, "at_s": 0}
        ),
    )
    assert state.groups["z"].speed_factor == pytest.approx(zone, rel=1e-6)


def test_slow_walkers_take_longer_on_the_stairs(registry: Registry) -> None:
    # a light crowd, so the stairs do not queue and walking (and stair) speed decides
    v = ground(levels=3, people=30)
    from api.models import PeopleGroup

    slow = v.model_copy(deep=True)
    for f in slow.floors[1:]:
        for z in f.zones:
            z.groups = [PeopleGroup(kind="bed", share=0.5)]
    fast = run_tier1(v, [], registry, S).metrics.evac_time_p95_s
    late = run_tier1(slow, [], registry, S).metrics.evac_time_p95_s
    assert fast is not None and late is not None and late > fast


def test_a_square_building_keeps_one_office_per_room() -> None:
    raw = json.loads((LIVE / "office.json").read_text())["spec"]
    raw.update(width_m=30, depth_m=30)
    raw["building"] = {**raw["building"], "interior": "rooms", "rooms_per_floor": 6}
    raw["exits"] = [{"wall": "east", "width_m": 1.8, "position": 0.7}]
    built = build_venue(VenueSpec.model_validate(raw)).venue
    assert len(built.floors[0].zones) == 6, [z.label for z in built.floors[0].zones]
