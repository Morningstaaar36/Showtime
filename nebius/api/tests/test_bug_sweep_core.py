"""Regression tests for core, hazard and edit-op bugs found in the October 2026 bug sweep."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from api.adapters.weather import OpenMeteoWeather, WeatherUnavailable
from api.core.building_gen import build_storeys
from api.core.countdown import choose_hazard, compute_countdown
from api.core.estimates import capacity
from api.core.extensions import HazardResult, Registry
from api.core.settings import Settings
from api.core.tier1 import run_tier1
from api.core.venue_ops import apply_patch
from api.models import Exit, Floor, Location, Venue, VenuePatch
from plugins.hazard_wind import first_crossing

S = Settings(_env_file=None)


def _ground() -> Venue:
    def door(x0: float, x1: float, i: int) -> Exit:
        return Exit(id=f"door_{i}", polygon=[(x0, 9), (x1, 9), (x1, 11), (x0, 11)], width_m=2.0)

    return Venue(
        venue_id="draft",
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


def patch(registry: Registry, venue: Venue, *ops: dict[str, Any]) -> Any:
    return apply_patch(venue, VenuePatch.model_validate({"ops": list(ops)}), registry)


# --- instant estimate and capacity in buildings of three or more storeys ---------------


@pytest.mark.parametrize("levels", [3, 4])
def test_tier1_routes_every_storey_down_a_chain_of_stairs(registry: Registry, levels: int) -> None:
    venue, _ = build_storeys(_ground(), levels=levels, use="office", interior="open", people=600)
    res = run_tier1(venue, [], registry, S)
    assert res.status == "ok", res.notes
    assert res.metrics.agents_not_evacuated == 0
    assert res.metrics.evac_time_p95_s is not None


def test_tier1_lower_stair_carries_everyone_above_it(registry: Registry) -> None:
    venue, _ = build_storeys(_ground(), levels=3, use="office", interior="open", people=600)
    plan = run_tier1(venue, [], registry, S).extensions["plan"]["stairs"]
    into_ground = {s.id for s in venue.stairs if s.to_floor == "F0"}
    assert sum(sum(plan.get(sid, {}).values()) for sid in into_ground) == 400


def test_capacity_counts_stacked_stairwells_once(registry: Registry) -> None:
    two, _ = build_storeys(_ground(), levels=2, use="office", interior="open", people=600)
    four, _ = build_storeys(_ground(), levels=4, use="office", interior="open", people=600)
    # the ground-floor flights carry everyone above; extra storeys must not add width
    assert capacity(four, registry, S).limited_by == "stairs"
    assert capacity(four, registry, S).safe_people < capacity(two, registry, S).safe_people


# --- countdown ---------------------------------------------------------------------------


def test_alarm_relative_hazard_gets_no_clock_time() -> None:
    hazard = HazardResult(source="hazard_timer", t_hazard_s=1800, explanation="manual")
    cd = compute_countdown(hazard, 300, 120, 1.5)
    assert cd.t_latest_s == 1800 - (120 + 300 * 1.5)
    assert cd.t_latest_iso is None


def test_hazards_are_compared_within_one_reference_frame() -> None:
    weather = HazardResult(
        source="hazard_wind", t_hazard_s=30, t_hazard_iso="2026-11-20T18:00:30", explanation="w"
    )
    scenario = HazardResult(source="hazard_timer", t_hazard_s=600, explanation="s")
    assert choose_hazard([weather, scenario]) is scenario
    assert choose_hazard([weather]) is weather
    untimed = HazardResult(source="hazard_wind", explanation="none")
    assert choose_hazard([untimed]) is untimed
    assert choose_hazard([]) is None


# --- wind hazard -------------------------------------------------------------------------


def test_gusts_already_over_the_limit_when_the_window_opens() -> None:
    times = ["2026-11-20T17:00", "2026-11-20T18:00", "2026-11-20T19:00"]
    start = datetime(2026, 11, 20, 18, 30)
    hit = first_crossing(times, [10, 25, 25], start, start + timedelta(hours=4), 20.0)
    assert hit == start


@pytest.mark.asyncio
async def test_no_hazard_message_quotes_the_peak_inside_the_window(
    registry: Registry, field: Venue
) -> None:
    from api.core.extensions import HazardContext

    venue = field.model_copy(deep=True)
    assert venue.location is not None
    venue.location = venue.location.model_copy(update={"event_start": "2026-11-20T18:00:00"})
    times = [f"2026-11-{d}T{h:02d}:00" for d in (20, 21) for h in range(24)]
    gusts = [5.0] * len(times)
    gusts[times.index("2026-11-21T12:00")] = 60.0  # far outside the event window
    venue.extensions = {**venue.extensions, "weather_snapshot": {"times": times, "gust_ms": gusts}}
    wind = next(h for h in registry.all("HazardSource") if h.id == "hazard_wind")
    res = await wind.evaluate(HazardContext(venue=venue, attack=None, get_forecast=None))
    assert res is not None and res.t_hazard_s is None
    assert "peak at 5.0 m/s" in res.explanation


# --- undo of edit operations ---------------------------------------------------------------


def test_undo_remove_zone_restores_its_people_mix(registry: Registry, hall: Venue) -> None:
    zone = hall.floors[0].zones[0]
    profiled = patch(
        registry,
        hall,
        {
            "op": "set_zone_profile",
            "zone_id": zone.id,
            "groups": [{"kind": "wheelchair", "share": 0.1}],
            "pre_movement_s": 300,
        },
    ).venue
    removed = patch(registry, profiled, {"op": "remove_zone", "zone_id": zone.id})
    undone = apply_patch(removed.venue, removed.inverse, registry).venue
    back = next(z for f in undone.floors for z in f.zones if z.id == zone.id)
    before = next(z for f in profiled.floors for z in f.zones if z.id == zone.id)
    assert back == before


def test_undo_set_event_start_clears_a_start_that_was_not_set(
    registry: Registry, field: Venue
) -> None:
    venue = field.model_copy(deep=True)
    venue.location = Location(lat=23.7, lon=90.4, timezone="Asia/Dhaka", event_start=None)
    res = patch(registry, venue, {"op": "set_event", "start": "2026-11-20T18:00"})
    assert res.venue.location.event_start == "2026-11-20T18:00"
    undone = apply_patch(res.venue, res.inverse, registry).venue
    assert undone.location is not None and undone.location.event_start is None


# --- weather cache -----------------------------------------------------------------------


class _Resp:
    status_code = 200

    def __init__(self, gust: float) -> None:
        self.gust = gust

    def json(self) -> dict[str, Any]:
        return {"hourly": {"time": ["2026-11-20T18:00"], "wind_gusts_10m": [self.gust]}}


@pytest.mark.asyncio
async def test_a_stale_forecast_is_refreshed_and_kept_when_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    gusts = iter([10.0, 30.0])
    fail = {"on": False}

    async def fake_get(self: Any, url: str, params: Any = None) -> _Resp:
        if fail["on"]:
            raise httpx.ConnectError("down")
        return _Resp(next(gusts))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    wx = OpenMeteoWeather("https://forecast.test", "https://archive.test", tmp_path)
    day = datetime.now().date()
    first = await wx.hourly_gusts(23.7, 90.4, "Asia/Dhaka", day)
    assert first["gust_ms"] == [10.0]
    assert (await wx.hourly_gusts(23.7, 90.4, "Asia/Dhaka", day))["cached"] is True

    # age the cached forecast past its time to live: the next call fetches again
    for path in tmp_path.rglob("*.json"):
        path.write_text(
            path.read_text().replace(
                first["fetched_at"], (datetime.now() - timedelta(hours=4)).isoformat()
            )
        )
    assert (await wx.hourly_gusts(23.7, 90.4, "Asia/Dhaka", day))["gust_ms"] == [30.0]

    fail["on"] = True
    for path in tmp_path.rglob("*.json"):
        text = path.read_text()
        fetched = text.split('"fetched_at": "')[1].split('"')[0]
        path.write_text(text.replace(fetched, (datetime.now() - timedelta(hours=4)).isoformat()))
    stale = await wx.hourly_gusts(23.7, 90.4, "Asia/Dhaka", day)
    assert stale["gust_ms"] == [30.0] and stale["cached"] is True

    with pytest.raises(WeatherUnavailable):
        await wx.hourly_gusts(23.7, 90.4, "Asia/Dhaka", day + timedelta(days=1))


def test_a_new_door_never_straddles_an_interior_wall(registry: Registry) -> None:
    from shapely.geometry import Polygon as P

    from api.models import Obstacle

    venue = _ground()
    # a room wall meets the east wall at y = 5 (room to the south, corridor to the north)
    wall = [(40.0, 4.9), (60.0, 4.9), (60.0, 5.1), (40.0, 5.1)]
    venue.floors[0].obstacles.append(Obstacle(id="room_wall", kind="wall", polygon=wall))
    res = patch(
        registry,
        venue,
        {
            "op": "add_exit",
            "floor_id": "F0",
            "id": "door_new",
            "wall": "east",
            "center": 5.0,
            "width_m": 2.0,
        },
    )
    door = P(next(e.polygon for e in res.venue.floors[0].exits if e.id == "door_new"))
    assert not door.intersects(P(wall).buffer(0.05))
    assert abs((door.bounds[1] + door.bounds[3]) / 2 - 5.0) < 2.0  # slid only as far as needed


def test_titles_name_objects_by_their_labels(registry: Registry) -> None:
    from api.agents.context import readable

    venue, _ = build_storeys(_ground(), levels=3, use="hospital", interior="rooms", people=120)
    zone = venue.floors[1].zones[0]
    stair = venue.stairs[0]
    text = readable(f"Add an exit for {zone.id} near {stair.id} and door_2", venue)
    assert zone.id not in text and (zone.label or "") in text
    assert stair.id not in text and "Stair" in text
    assert "door_2" not in text and "door 2" in text.lower()
    assert readable("Power cut slows everyone down", venue) == "Power cut slows everyone down"


def test_widen_stair_is_a_conformant_op_for_the_whole_stairwell(registry: Registry) -> None:
    from api.tests.conformance.suites import check_patch_op

    venue, _ = build_storeys(_ground(), levels=3, use="office", interior="open", people=600)
    first = venue.stairs[0]
    check_patch_op(registry, venue, {"op": "widen_stair", "stair_id": first.id, "width_m": 2.2})
    wider = patch(registry, venue, {"op": "widen_stair", "stair_id": first.id, "width_m": 2.2})
    changed = [s for s in wider.venue.stairs if s.width_m == 2.2]
    assert len(changed) == 2  # both flights of that stairwell in a 3-storey building
    before = run_tier1(venue, [], registry, S).metrics.evac_time_p95_s
    after = run_tier1(wider.venue, [], registry, S).metrics.evac_time_p95_s
    assert before is not None and after is not None and after < before


def test_building_fixes_widen_stairs_and_phase_the_evacuation(registry: Registry) -> None:
    from api.models import Attack
    from api.orchestrator.fallbacks import rule_fixes

    venue, _ = build_storeys(_ground(), levels=3, use="office", interior="open", people=600)
    attack = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Smoke on the 1st floor",
            "events": [{"type": "slowdown", "factor": 0.6, "at_s": 0, "floor_id": "F1"}],
            "inspired_by": {
                "incident": "x",
                "year": 2000,
                "source_url": "https://doi.org/10.5281/zenodo.19483010",
                "evidence": "x",
            },
            "rationale": "x",
        }
    )
    result = run_tier1(venue, [], registry, S)
    titles = [f.title for f in rule_fixes(registry, venue, attack, result, 4, "F1_R")]
    assert any(t.startswith("Widen") for t in titles), titles
    assert any(t.startswith("Phased evacuation") for t in titles), titles
