"""New venues from a description (designer + solver) and from OpenStreetMap features."""

from __future__ import annotations

from typing import Any

import pytest

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.agents.venue_designer import design_venue
from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.core.osm_venue import Projector, venue_from_osm
from api.core.venue_builder import build_venue
from api.models.venue_spec import VenueSpec

HALL: dict[str, Any] = {
    "name": "Hall",
    "mode": "indoor",
    "width_m": 45,
    "depth_m": 30,
    "stage": {"wall": "north", "width_m": 14, "depth_m": 6},
    "exits": [
        {"wall": "south", "width_m": 3, "position": 0.25},
        {"wall": "south", "width_m": 3, "position": 0.75},
        {"wall": "north", "width_m": 2, "position": 0.5},  # behind the stage: must move
    ],
    "zones": [
        {"label": "Main floor", "people": 1150, "region": "whole"},
        {"label": "Balcony audience", "people": 350, "region": "back"},  # duplicate of upper floor
    ],
    "features": [{"kind": "bar", "place": "west", "width_m": 6, "depth_m": 2}],
    "upper_floor": {"along": "south", "depth_m": 8, "people": 350, "label": "Balcony"},
}


def _errors(venue: Any) -> list[str]:
    return [c.message for c in validate_venue(venue).checks if c.severity == "error"]


def test_spec_builds_a_valid_two_floor_hall() -> None:
    res = build_venue(VenueSpec.model_validate(HALL))
    v = res.venue
    assert _errors(v) == []
    assert [f.floor_id for f in v.floors] == ["F0", "F1"] and len(v.stairs) == 1
    assert v.total_people() == 1500  # the balcony is counted once
    stage = geo.to_polygon(v.floors[0].obstacles[0].polygon)
    for e in v.floors[0].exits:
        assert not geo.to_polygon(e.polygon).buffer(0.5).intersects(stage)
    assert any("Moved the north exit" in n for n in res.notes)


@pytest.mark.parametrize("wall", ["north", "south", "east", "west"])
def test_stage_on_any_wall_gives_valid_open_air_site(wall: str) -> None:
    exit_wall = {"north": "south", "south": "north", "east": "west", "west": "east"}[wall]
    spec = VenueSpec.model_validate(
        {
            "mode": "outdoor",
            "width_m": 120,
            "depth_m": 80,
            "stage": {"wall": wall, "width_m": 20, "depth_m": 8, "roof_height_m": 12},
            "front_barrier": True,
            "exits": [{"wall": exit_wall, "width_m": 6, "position": p} for p in (0.3, 0.7)],
            "zones": [
                {"label": "Front", "people": 2000, "region": "front"},
                {"label": "Rest", "people": 3000, "region": "whole"},
            ],
            "features": [{"kind": "bar", "place": "middle", "width_m": 8, "depth_m": 4}],
        }
    )
    v = build_venue(spec).venue
    assert _errors(v) == [] and v.stage is not None and v.total_people() == 5000
    zones = [geo.to_polygon(z.polygon) for z in v.floors[0].zones]
    assert zones[0].intersection(zones[1]).area < 0.01  # zones never overlap


async def test_designer_builds_from_model_spec_and_repairs_once() -> None:
    bad = dict(HALL, exits=[{"wall": "north", "width_m": 2, "position": 0.5}], upper_floor=None)
    bad["width_m"] = 16  # stage fills the north wall: the only exit cannot be placed
    good = dict(HALL)
    llm = FakeLLM({"designer": [bad, good]})
    out = await design_venue(AgentEnv(llm=llm, audit=False), "a hall with a balcony")
    assert len(llm.calls) == 2 and "No room for exit" in llm.calls[1][1][-1]["content"]
    assert out.status == "built" and out.venue is not None and out.venue.total_people() == 1500


# --- OpenStreetMap -------------------------------------------------------------------------

LAT0, LON0 = 23.7260, 90.3920
PR = Projector(LAT0, LON0)


def _ll(x: float, y: float) -> list[float]:
    lat, lon = PR.latlon(x, y)
    return [lat, lon]


def _ring(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [_ll(x0, y0), _ll(x1, y0), _ll(x1, y1), _ll(x0, y1), _ll(x0, y0)]


FEATURES: list[dict[str, Any]] = [
    {"id": "w1", "kind": "building", "name": "Library", "tags": {"building:levels": "3"},
     "coords": _ring(40, 40, 60, 55), "closed": True},
    {"id": "w2", "kind": "path", "name": "Main walk", "tags": {"highway": "footway"},
     "coords": [_ll(50, -20), _ll(50, 20)], "closed": False},
    {"id": "n1", "kind": "entrance", "name": "", "tags": {"entrance": "main"},
     "coords": [_ll(50, 40)], "closed": False},
]  # fmt: skip


def test_open_area_gets_buildings_as_obstacles_and_paths_as_exits() -> None:
    imp = venue_from_osm(FEATURES, _ring(0, 0, 100, 80), mode="outdoor", name="Campus", people=3000)
    f = imp.venue.floors[0]
    assert _errors(imp.venue) == []
    assert [o.label for o in f.obstacles] == ["Library"]
    assert len(f.exits) == 1 and f.exits[0].label == "Main walk"
    assert abs(geo.centroid(f.exits[0].polygon)[0] - 50) < 1.0  # where the path crosses the edge
    assert imp.venue.total_people() == 3000 and imp.venue.location is not None


def test_building_uses_mapped_entrance_and_notes_upper_floors() -> None:
    imp = venue_from_osm(
        FEATURES, FEATURES[0]["coords"], mode="indoor", name="Library", selected_id="w1"
    )
    f = imp.venue.floors[0]
    assert _errors(imp.venue) == []
    assert [(e.label, e.width_m) for e in f.exits] == [("Main entrance", 3.0)]
    assert any("3 floors" in n for n in imp.notes)
    assert imp.venue.total_people() > 0  # assumed from floor area, and said so
    assert any("Assumed" in n for n in imp.notes)


def test_building_without_entrances_gets_two_assumed_exits() -> None:
    imp = venue_from_osm([], _ring(0, 0, 30, 12), mode="indoor", name="Hall", people=200)
    exits = imp.venue.floors[0].exits
    assert len(exits) == 2 and all("assumed" in (e.label or "") for e in exits)
    assert _errors(imp.venue) == []


def test_large_park_gets_a_plausible_automatic_headcount() -> None:
    # a 600 x 500 m park at 1.5 per m2 would be ~450,000 people, beyond the zone limit
    imp = venue_from_osm([], _ring(0, 0, 600, 500), mode="outdoor", name="Park")
    assert imp.venue.total_people() == 10_000
    assert any("Set your real headcount" in n for n in imp.notes)


def test_too_large_area_is_refused_with_a_hint() -> None:
    with pytest.raises(ValueError, match="Draw a smaller box"):
        venue_from_osm([], _ring(0, 0, 900, 900), mode="outdoor", name="City", people=10)


def test_water_is_not_walkable() -> None:
    lake = {"id": "w9", "kind": "water", "name": "Lake", "tags": {"natural": "water"},
            "coords": _ring(20, 20, 50, 40), "closed": True}  # fmt: skip
    imp = venue_from_osm([lake], _ring(0, 0, 100, 80), mode="outdoor", name="Park", people=500)
    f = imp.venue.floors[0]
    assert [o.label for o in f.obstacles] == ["Lake"]
    # zones are single rings; the simulator and the checks subtract obstacles from them
    usable = geo.to_polygon(f.zones[0].polygon).intersection(geo.free_space(f))
    assert usable.intersection(geo.to_polygon(f.obstacles[0].polygon)).area < 0.01
    assert _errors(imp.venue) == []


# --- event layout on a real site and the Copilot ------------------------------------------


def _open_site() -> Any:
    feats = [{"id": "w5", "kind": "path", "name": "Gate road", "tags": {"highway": "residential"},
              "coords": [_ll(-10, 40), _ll(10, 40)], "closed": False}]  # fmt: skip
    return venue_from_osm(feats, _ring(0, 0, 160, 110), mode="outdoor", name="Park", people=4000)


def test_furnish_places_stage_away_from_the_gate_and_splits_the_crowd() -> None:
    from api.core.site_layout import furnish

    site = _open_site().venue
    res = furnish(site, attendees=4000, stage=True, toilets=30, alcohol=True)
    f = res.venue.floors[0]
    kinds = {o.kind for o in f.obstacles}
    assert {"stage", "barrier", "booth", "bar"} <= kinds and _errors(res.venue) == []
    stage = next(o for o in f.obstacles if o.kind == "stage")
    gate = f.exits[0]
    assert geo.centroid(stage.polygon)[0] > 80  # the gate is on the west edge
    assert geo.distance_to(gate.polygon, *geo.centroid(stage.polygon)) > 60
    assert [z.label for z in f.zones] == ["Front of stage", "Middle", "Back"]
    assert sum(z.people for z in f.zones) == 4000
    assert res.venue.stage is not None  # open-air stage gets wind-check parameters


async def test_copilot_plans_a_designed_venue_end_to_end(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.state import build_state
    from api.core.settings import Settings, get_settings
    from api.db import session as dbs
    from api.orchestrator.copilot import plan_event

    db = tmp_path / "copilot.sqlite"  # never the app's own database
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    get_settings.cache_clear()
    dbs.get_engine.cache_clear()
    settings = Settings(_env_file=None, db_url=f"sqlite:///{db}", runs_dir=tmp_path / "runs",
                        cache_dir=tmp_path / "cache", llm_provider="fake",
                        sandbox_provider="fake", offline=True)  # fmt: skip
    monkeypatch.setattr("api.core.settings.get_settings", lambda: settings)
    monkeypatch.setattr("api.db.session.get_settings", lambda: settings)
    monkeypatch.setattr("api.orchestrator.demos.DEMO_DIR", tmp_path / "no-demos")
    brief = {"title": "Gym night", "kind": "concert", "place": None, "setting": "indoor",
             "attendees": 400, "start": None, "duration_h": 3, "alcohol": False,
             "audience": "standing", "stage": True, "layout": "A gym 30 by 20 m"}  # fmt: skip
    spec = {"name": "Gym", "mode": "indoor", "width_m": 30, "depth_m": 20,
            "stage": {"wall": "north", "width_m": 10, "depth_m": 4},
            "exits": [{"wall": "south", "width_m": 2, "position": 0.3},
                      {"wall": "south", "width_m": 2, "position": 0.7}],
            "zones": [{"label": "Crowd", "people": 400, "region": "whole"}]}  # fmt: skip
    llm = FakeLLM({"brief": brief, "designer": spec}, settings)
    st = build_state(settings, llm=llm, runner=FakeRunner(settings.runs_dir))
    try:
        steps = [s async for s in plan_event(st, "a concert in a gym for 400 people")]
        keys = [s["step"] for s in steps]
        assert keys[0] == "brief" and "estimates" in keys and keys[-1] == "finished"
        venue = st.projects.venue(steps[-1]["project_id"])
        assert venue.total_people() == 400 and venue.extensions["event"]["duration_h"] == 3
        assert any(s["step"] == "simulate" and s["status"] == "done" for s in steps)
        assert any(s["step"] == "sweep" and s["status"] == "done" for s in steps)
        review = next(s for s in steps if s["step"] == "review" and s["status"] == "done")
        assert "summary" in review["review"]  # rule-based when the model has no script
        nodes = [s.get("node") for s in steps if s.get("node")]
        assert nodes[:2] == ["understand", "understand"]
        assert "design" in nodes and "locate" not in nodes
    finally:
        get_settings.cache_clear()
        dbs.get_engine.cache_clear()


def test_area_of_a_lat_lon_ring_is_in_square_metres() -> None:
    from api.orchestrator.copilot import _area_m2

    assert abs(_area_m2(_ring(0, 0, 100, 50)) - 5000) < 50
