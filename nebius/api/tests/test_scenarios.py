"""Scenario catalogue: entries, venue-specific events, Tier 1 effects and the routes."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.core.building_gen import build_storeys
from api.core.extensions import Registry
from api.core.scenarios import (
    CATALOGUE,
    CATEGORY_LABELS,
    LEGACY_SWEEP,
    catalogue_for,
    venue_facts,
)
from api.core.settings import Settings
from api.core.templates import get_template
from api.core.tier1 import run_tier1
from api.models import Exit, Floor, RunResult, Venue
from api.tests.test_api import client  # noqa: F401 - shared fixture

S = Settings(_env_file=None)
TEMPLATES = ("conference_hall_2f", "festival_field", "school_wing", "t_alley")
ICONS = {  # lucide-react names (checked against web/node_modules/lucide-react)
    "circle-check", "user-plus", "door-closed-locked", "cloud-rain", "cloud-rain-wind", "moon",
    "cloud-fog", "flame", "layers", "siren", "arrow-up-down", "accessibility", "zap-off",
    "trending-up", "arrow-down-up", "ban", "hourglass", "megaphone",
}  # fmt: skip
MULTI_STOREY = {"stair_smoke", "smoke_floor", "phased", "firefighters", "lift_out"}


def _block() -> Venue:
    def door(x0: float, x1: float, i: int) -> Exit:
        return Exit(id=f"door_{i}", polygon=[(x0, 9), (x1, 9), (x1, 11), (x0, 11)], width_m=2.0)

    ground = Floor(
        floor_id="F0",
        name="Ground",
        walkable=[(0, 0), (60, 0), (60, 20), (0, 20)],
        exits=[door(0.02, 0.42, 1), door(59.58, 59.98, 2)],
    )
    return Venue(venue_id="block", name="Block", mode="indoor", floors=[ground])


def storeys(levels: int = 3, people: int = 300) -> Venue:
    venue, _ = build_storeys(_block(), levels=levels, use="office", interior="open", people=people)
    return venue


VENUES = [*TEMPLATES, "storeys_3"]


def _venue(name: str) -> Venue:
    return storeys() if name == "storeys_3" else get_template(name)


def _baseline(registry: Registry, v: Venue) -> RunResult:
    return run_tier1(v, [], registry, S)


def _check_event(registry: Registry, venue: Venue, ev: dict[str, Any]) -> None:
    spec = registry.event(ev["type"])
    params = spec.params_model.model_validate(ev)
    assert spec.validate_refs(venue, params) == [], ev


def test_catalogue_entries_are_well_formed() -> None:
    assert len(CATALOGUE) >= 14
    ids = [s.id for s in CATALOGUE]
    assert len(set(ids)) == len(ids)
    assert set(LEGACY_SWEEP) <= set(ids)
    for s in CATALOGUE:
        assert 1 <= len(s.title.split()) <= 5, s.title
        assert len(s.description.split()) <= 12, s.description
        assert s.icon in ICONS, s.icon
        assert s.category in CATEGORY_LABELS
    assert {s.category for s in CATALOGUE} == set(CATEGORY_LABELS)
    assert set(ids) >= MULTI_STOREY


@pytest.mark.parametrize("name", VENUES)
def test_every_scenario_gives_valid_events_and_runs_tier1(registry: Registry, name: str) -> None:
    from api.core.estimates import scale_people

    venue = _venue(name)
    base = _baseline(registry, venue)
    resolved = catalogue_for(venue, base)
    assert [r.spec.id for r in resolved] == [s.id for s in CATALOGUE]
    applicable = [r for r in resolved if r.built is not None]
    assert len(applicable) >= 8, [(r.spec.id, r.reason) for r in resolved]
    for r in resolved:
        if r.built is None:
            assert r.reason, r.spec.id
            continue
        assert r.built.targets and all(isinstance(t, str) and t for t in r.built.targets)
        v = scale_people(venue, r.built.scale)
        for ev in r.built.events:
            _check_event(registry, v, ev.model_dump())
        res = run_tier1(v, list(r.built.events), registry, S)
        assert res.status in ("ok", "partial"), (r.spec.id, res.notes)
        pub = r.public()
        assert pub["applicable"] and pub["events"] == [e.model_dump() for e in r.built.events]


def test_multi_storey_scenarios_all_apply_to_a_three_storey_building(registry: Registry) -> None:
    venue = storeys()
    facts = venue_facts(venue, _baseline(registry, venue))
    assert {"multi_storey", "multi_stairwell", "indoor"} <= facts.tags
    assert [w.name for w in facts.stairwells] == ["Stair A", "Stair B"]
    assert all(len(w.flights) == 2 for w in facts.stairwells)
    resolved = {r.spec.id: r for r in catalogue_for(venue, _baseline(registry, venue))}
    for sid in MULTI_STOREY | {"mobility", "power_cut"}:
        assert resolved[sid].built is not None, (sid, resolved[sid].reason)
    smoke = resolved["stair_smoke"].built
    assert smoke is not None
    blocked = {e.model_dump()["exit_id"] for e in smoke.events}
    well = facts.main_stairwell()
    assert well is not None and blocked == {s.id for s in well.flights}
    assert smoke.targets == [f"{well.name} blocked on every floor (2 flights)"]
    phased = resolved["phased"].built
    assert phased is not None
    # fire floor F1 (lowest of the equally full upper floors) and F2 go first; ground waits
    assert facts.fire_floor() == "F1"
    assert {e.model_dump()["zone_id"] for e in phased.events} == {
        z.id for z in venue.floor("F0").zones
    }
    ff = resolved["firefighters"].built
    assert ff is not None
    assert [e.model_dump()["exit_id"] for e in ff.events] == [
        s.id for s in well.flights if s.from_floor == "F1"
    ]


def test_losing_a_stair_or_slower_people_raise_the_instant_estimate(registry: Registry) -> None:
    venue = storeys()
    base = _baseline(registry, venue)
    resolved = {r.spec.id: r for r in catalogue_for(venue, base)}
    t_plan = base.metrics.evac_time_p95_s
    assert t_plan
    # a small slow share only moves the mean speed: stair queues can still set the time
    for sid, strict in (
        ("stair_smoke", True),
        ("smoke_floor", True),
        ("power_cut", True),
        ("lift_out", False),
        ("mobility", False),
    ):
        built = resolved[sid].built
        assert built is not None
        t = run_tier1(venue, list(built.events), registry, S).metrics.evac_time_p95_s
        assert t is not None and (t > t_plan if strict else t >= t_plan), (sid, t, t_plan)


def test_single_stairwell_and_single_exit_are_skipped_honestly(registry: Registry) -> None:
    hall = get_template("conference_hall_2f")  # one stair, two doors, a stage
    resolved = {r.spec.id: r for r in catalogue_for(hall, _baseline(registry, hall))}
    assert resolved["stair_smoke"].built is None
    assert "Only one stairwell" in (resolved["stair_smoke"].reason or "")
    assert resolved["stage_surge"].built is not None
    assert resolved["firefighters"].built is not None
    field = get_template("festival_field")
    out = {r.spec.id: r for r in catalogue_for(field, _baseline(registry, field))}
    assert out["phased"].built is None and out["phased"].reason
    assert out["smoke_floor"].reason == "Applies to indoor venues."


def test_scenarios_route_lists_entries_for_a_project(client: TestClient) -> None:  # noqa: F811
    assert len(client.get("/api/v1/scenarios").json()["scenarios"]) == len(CATALOGUE)
    pid = client.post(
        "/api/v1/projects", json={"template_id": "conference_hall_2f", "name": "T"}
    ).json()["id"]
    body = client.get("/api/v1/scenarios", params={"project_id": pid}).json()
    assert body["default_sweep"] == list(LEGACY_SWEEP)
    ids = {s["id"] for s in body["scenarios"]}
    assert {"plan", "gate", "firefighters", "stage_surge"} <= ids
    assert "stair_smoke" in {s["id"] for s in body["not_applicable"]}
    gate = next(s for s in body["scenarios"] if s["id"] == "gate")
    assert gate["events"][0]["type"] == "block_exit" and gate["targets"][0].endswith("closed")
    assert client.get("/api/v1/scenarios", params={"project_id": "nope"}).status_code == 404


def test_sweep_default_is_the_original_six_and_accepts_catalogue_ids(
    client: TestClient,  # noqa: F811
) -> None:
    pid = client.post(
        "/api/v1/projects", json={"template_id": "conference_hall_2f", "name": "T"}
    ).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/sweep")
    assert r.status_code == 202, r.text
    items = r.json()["items"]
    assert [i["key"] for i in items] == list(LEGACY_SWEEP)
    assert [i["label"] for i in items] == [
        "As planned",
        "20% more people",
        "Main exit closed",
        "Rain: 85% walking speed",
        "Rain and main exit closed",
        "Late surge in the dark: 30% more, 70% speed",
    ]
    r = client.post(
        f"/api/v1/projects/{pid}/sweep",
        json={"scenarios": ["plan", "firefighters", "stair_smoke", "mobility"]},
    )
    assert r.status_code == 202, r.text
    items = {i["key"]: i for i in r.json()["items"]}
    assert items["firefighters"]["run_id"] and items["mobility"]["run_id"]
    assert items["stair_smoke"]["run_id"] is None and items["stair_smoke"]["skipped"]
    for _ in range(200):
        got = client.get(f"/api/v1/projects/{pid}/sweep").json()["items"]
        if all(i["status"] in ("ok", "partial", "skipped") for i in got):
            break
        time.sleep(0.05)
    assert {i["status"] for i in got} <= {"ok", "partial", "skipped"}
    bad = client.post(f"/api/v1/projects/{pid}/sweep", json={"scenarios": ["teleport"]})
    assert bad.status_code == 422 and bad.json()["code"] == "unknown_scenario"


def test_every_scenario_event_has_a_simulator_handler(registry: Registry) -> None:
    """Each registered ScenarioEvent type is handled inside the sandbox (sim/plugins/events.py),
    and a stair id or a floor id routes an event to the right floor run."""
    import importlib.util
    import sys
    from pathlib import Path

    sim = Path(__file__).resolve().parents[2] / "sim"
    sys.path.insert(0, str(sim))
    try:
        spec = importlib.util.spec_from_file_location("sim_events", sim / "plugins" / "events.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(sim))
    assert set(registry.keys("ScenarioEvent")) <= set(mod.HANDLERS)
    assert "floor_id" in mod.FLOOR_KEYS
