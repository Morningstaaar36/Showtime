"""Tier 1, countdown, stage wind check and hazard sources."""

from __future__ import annotations

import math
import time
from typing import Any

import pytest

from api.core.countdown import compute_countdown
from api.core.extensions import HazardContext, HazardResult, Registry
from api.core.settings import Settings
from api.core.templates import get_template
from api.core.tier1 import run_tier1
from api.models import Attack, ScenarioEventIn, StageParams, Venue
from api.tests.conformance.suites import check_hazard_source
from plugins.hazard_wind import first_crossing
from plugins.hazard_wind.stage_check import check_stage

S = Settings(_env_file=None)


def _room(width: float = 2.0, people: int = 100, exits: int = 1) -> Venue:
    ex = [
        {
            "id": "e1",
            "polygon": [[4, 0.02], [4 + width, 0.02], [4 + width, 0.42], [4, 0.42]],
            "width_m": width,
        }
    ]
    if exits == 2:
        ex.append(
            {
                "id": "e2",
                "polygon": [[19.58, 4], [19.98, 4], [19.98, 4 + width], [19.58, 4 + width]],
                "width_m": width,
            }
        )
    return Venue.model_validate(
        {
            "venue_id": "room",
            "name": "Room",
            "mode": "indoor",
            "floors": [
                {
                    "floor_id": "F0",
                    "walkable": [[0, 0], [20, 0], [20, 10], [0, 10]],
                    "exits": ex,
                    "zones": [
                        {
                            "id": "z",
                            "polygon": [[8, 8], [12, 8], [12, 9.5], [8, 9.5]],
                            "people": people,
                        }
                    ],
                }
            ],
        }
    )


def test_tier1_one_room_matches_hand_calculation(registry: Registry) -> None:
    # 100 people, 2 m door, capacity 1.3 × 2 = 2.6 p/s -> queue-limited ≈ walk + 100/2.6
    r = run_tier1(_room(2.0, 100), [], registry, S)
    m = r.metrics
    walk_first = 7.3 / S.walk_speed_mean  # nearest person ~7.3 m from the door
    expected_max = walk_first + 100 / 2.6
    assert m.evac_time_max_s is not None
    assert abs(m.evac_time_max_s - expected_max) < 6, (m.evac_time_max_s, expected_max)
    assert m.agents_not_evacuated == 0
    assert m.per_exit[0].people == 100


def test_tier1_wider_door_is_faster(registry: Registry) -> None:
    narrow = run_tier1(_room(1.0, 200), [], registry, S).metrics.evac_time_p95_s
    wide = run_tier1(_room(3.0, 200), [], registry, S).metrics.evac_time_p95_s
    assert narrow and wide and wide < narrow


def test_tier1_two_exits_split_by_capacity(registry: Registry) -> None:
    r = run_tier1(_room(2.0, 300, exits=2), [], registry, S)
    loads = {p.exit_id: p.people for p in r.metrics.per_exit}
    assert loads["e1"] + loads["e2"] == 300
    assert min(loads.values()) > 60  # both exits are used


def test_tier1_block_exit_reroutes_and_slows(registry: Registry) -> None:
    v = _room(2.0, 300, exits=2)
    base = run_tier1(v, [], registry, S).metrics
    blocked = run_tier1(
        v, [ScenarioEventIn(type="block_exit", exit_id="e2", at_s=0)], registry, S
    ).metrics
    assert {p.exit_id: p.people for p in blocked.per_exit}["e2"] == 0
    assert blocked.evac_time_p95_s and base.evac_time_p95_s
    assert blocked.evac_time_p95_s > base.evac_time_p95_s
    assert blocked.peak_density_ppm2 >= base.peak_density_ppm2


def test_tier1_staggered_release_and_surge(registry: Registry) -> None:
    v = _room(2.0, 100)
    base = run_tier1(v, [], registry, S).metrics.evac_time_max_s or 0
    held = run_tier1(
        v,
        [
            ScenarioEventIn.model_validate(
                {"type": "staggered_release", "zone_id": "z", "delay_s": 60}
            )
        ],
        registry,
        S,
    ).metrics
    surged = run_tier1(
        v,
        [
            ScenarioEventIn.model_validate(
                {"type": "surge", "zone_id": "z", "extra_people": 100, "at_s": 0}
            )
        ],
        registry,
        S,
    ).metrics
    assert (held.evac_time_max_s or 0) > base + 30
    assert surged.agents_total == 200


def test_tier1_all_templates_fast(registry: Registry) -> None:
    for tid in ("conference_hall_2f", "school_wing", "festival_field", "t_alley"):
        v = get_template(tid)
        run_tier1(v, [], registry, S)  # warm the distance-field cache
        t0 = time.perf_counter()
        r = run_tier1(v, [], registry, S)
        assert (time.perf_counter() - t0) < 0.05, tid
        assert r.metrics.agents_not_evacuated == 0, tid
        assert r.extensions["plan"]["groups"], tid


def test_tier1_multi_floor_routes_through_stair(registry: Registry, hall: Venue) -> None:
    r = run_tier1(hall, [], registry, S)
    plan = r.extensions["plan"]
    assert plan["groups"]["mezzanine"] == {"stair_ne": 300}
    assert sum(plan["stairs"]["stair_ne"].values()) == 300


def test_tier1_trapped_people_reported(registry: Registry) -> None:
    v = _room(2.0, 50)
    r = run_tier1(v, [ScenarioEventIn(type="block_exit", exit_id="e1", at_s=0)], registry, S)
    assert r.metrics.agents_not_evacuated == 50
    assert r.status == "partial"


# --- countdown -----------------------------------------------------------------------


def _hz(t: float | None, iso: str | None = None) -> HazardResult:
    return HazardResult(source="test", t_hazard_s=t, t_hazard_iso=iso, explanation="x")


def test_countdown_formula() -> None:
    c = compute_countdown(_hz(3600, "2026-11-20T19:00:00"), 400, 60, 1.5)
    assert c.status == "ok"
    assert c.t_latest_s == 3600 - (60 + 400 * 1.5)
    assert c.t_latest_iso == "2026-11-20T18:49"  # 18:00 start + 2,940 s


def test_countdown_no_hazard_and_too_late() -> None:
    assert compute_countdown(None, 400, 60, 1.5).status == "no_hazard"
    assert compute_countdown(_hz(None), 400, 60, 1.5).status == "no_hazard"
    late = compute_countdown(_hz(300), 400, 60, 1.5)
    assert late.status == "too_late" and late.t_latest_s is not None and late.t_latest_s < 0
    assert compute_countdown(_hz(300), None, 60, 1.5).status == "unknown"


# --- stage check ----------------------------------------------------------------------

STAGE = {
    "width_m": 20,
    "depth_m": 8,
    "roof_height_m": 12,
    "roof_area_m2": 160,
    "legs": 6,
    "ballast_kg_per_leg": 2000,
    "friction_coeff": 0.5,
    "force_coeff": 1.3,
    "banner_area_m2": 60,
}


def _stage(**kw: Any) -> StageParams:
    return StageParams.model_validate({**STAGE, **kw})


def test_stage_check_monotonic() -> None:
    base = check_stage(_stage()).v_limit_ms
    assert check_stage(_stage(ballast_kg_per_leg=4000)).v_limit_ms > base
    assert check_stage(_stage(ballast_kg_per_leg=1000)).v_limit_ms < base
    assert check_stage(_stage(roof_area_m2=320, banner_area_m2=120)).v_limit_ms < base
    r = check_stage(_stage())
    assert r.governing in ("uplift", "sliding", "overturning")
    assert r.label == "screening estimate" and len(r.assumptions) >= 4


def test_stage_check_scales_with_sqrt_ballast() -> None:
    # uplift limit: V² ∝ (W_b + dead share): quadrupling ballast roughly doubles V
    v1 = check_stage(_stage(ballast_kg_per_leg=1000)).limits_ms["uplift"]
    v4 = check_stage(_stage(ballast_kg_per_leg=4000)).limits_ms["uplift"]
    assert 1.5 < v4 / v1 < 2.1


# --- hazards -----------------------------------------------------------------------------


def test_first_crossing_interpolates() -> None:
    from datetime import datetime

    times = ["2026-11-20T18:00", "2026-11-20T19:00", "2026-11-20T20:00"]
    hit = first_crossing(
        times, [10, 20, 30], datetime(2026, 11, 20, 18), datetime(2026, 11, 20, 23), 25.0
    )
    assert hit == datetime(2026, 11, 20, 19, 30)
    assert (
        first_crossing(
            times, [1, 2, 3], datetime(2026, 11, 20, 18), datetime(2026, 11, 20, 23), 25.0
        )
        is None
    )


@pytest.mark.asyncio
async def test_wind_hazard_with_forecast(registry: Registry, field: Venue) -> None:
    async def forecast(lat: float, lon: float, day: str, tz: str) -> dict[str, Any]:
        return {
            "times": [f"{day}T{h:02d}:00" for h in range(24)],
            "gust_ms": [5.0] * 19 + [40.0] * 5,
            "source": "test",
        }

    src = registry.get("HazardSource", "hazard_wind")
    res = await check_hazard_source(src, HazardContext(venue=field, get_forecast=forecast))
    assert res is not None and res.t_hazard_s is not None
    limit = res.details["limit_ms"]
    assert 15 < limit < 45
    assert 0 < res.t_hazard_s < 3600  # between 18:00 and 19:00


@pytest.mark.asyncio
async def test_wind_hazard_calm_and_manual(registry: Registry, field: Venue) -> None:
    async def calm(lat: float, lon: float, day: str, tz: str) -> dict[str, Any]:
        return {"times": [f"{day}T{h:02d}:00" for h in range(24)], "gust_ms": [4.0] * 24}

    src = registry.get("HazardSource", "hazard_wind")
    res = await src.evaluate(HazardContext(venue=field, get_forecast=calm))
    assert res is not None and res.t_hazard_s is None
    assert "No hazard in forecast window" in res.explanation
    res2 = await src.evaluate(HazardContext(venue=field, manual={"gust_ms": 99.0}))
    assert res2 is not None and res2.t_hazard_s == 0.0


@pytest.mark.asyncio
async def test_timer_hazard_from_attack(registry: Registry, hall: Venue) -> None:
    attack = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Door lost",
            "events": [{"type": "block_exit", "exit_id": "door_s1", "at_s": 90}],
            "inspired_by": {"incident": "x", "source_url": "https://example.org"},
        }
    )
    src = registry.get("HazardSource", "hazard_timer")
    res = await check_hazard_source(src, HazardContext(venue=hall, attack=attack))
    assert res is not None and res.t_hazard_s == 90
    assert await src.evaluate(HazardContext(venue=hall)) is None
    manual = await src.evaluate(HazardContext(venue=hall, manual={"hazard_time_s": 300}))
    assert manual is not None and manual.t_hazard_s == 300
    assert math.isclose(manual.t_hazard_s, 300)


# --- organizer estimates (planning ratios + capacity) ------------------------------------


def _est(registry: Registry, venue: Venue) -> Any:
    from api.core.estimates import compute_estimates
    from api.core.settings import Settings

    return compute_estimates(venue, registry, Settings())


def test_toilets_follow_the_purple_guide_rows(registry: Registry) -> None:
    from api.core.templates import get_template
    from api.core.venue_ops import apply_patch
    from api.models import VenuePatch

    v = get_template("school_wing")  # 400 people
    lines = {ln.key: ln for ln in _est(registry, v).lines}
    assert lines["toilets"].value == 2 + 1  # 200/100 women, 200/500 men (rounded up)
    ops = [{"op": "set_event", "duration_h": 8, "alcohol": True}]
    v2 = apply_patch(v, VenuePatch.model_validate({"ops": ops}), registry).venue
    lines2 = {ln.key: ln for ln in _est(registry, v2).lines}
    assert lines2["toilets"].value == 3 + 1  # 200/75 women, 200/400 men
    assert lines2["stewards"].value == 4  # 1 per 100 with alcohol
    assert "alcohol" in lines2["toilets"].detail


def test_more_exit_width_never_lowers_capacity(registry: Registry) -> None:
    from api.core.estimates import capacity
    from api.core.settings import Settings
    from api.core.templates import get_template
    from api.core.venue_ops import apply_patch
    from api.models import VenuePatch

    v = get_template("festival_field")
    base = capacity(v, registry, Settings())
    ops = [{"op": "add_exit", "floor_id": "F0", "id": "gate_e1", "wall": "east", "width_m": 8}]
    wider = apply_patch(v, VenuePatch.model_validate({"ops": ops}), registry).venue
    more = capacity(wider, registry, Settings())
    assert base.by_egress is not None and more.by_egress is not None
    assert more.by_egress >= base.by_egress
    assert base.safe_people <= base.by_space


def test_planning_score_parts_and_caps() -> None:
    from api.core.score import planning_score
    from api.models import RunMetrics

    good = RunMetrics(evac_time_p95_s=120, evac_time_max_s=150, peak_density_ppm2=2.0,
                      time_above_danger_s=0, agents_not_evacuated=0, agents_total=500)  # fmt: skip
    kw = {"target_evac_s": 300, "warn_ppm2": 3.5, "danger_ppm2": 5.0, "people": 500,
          "safe_people": 900, "exit_width_have": 6, "exit_width_need": 2.6, "errors": 0,
          "warnings": 0}  # fmt: skip
    s = planning_score(good, **kw)
    assert s.grade == "A" and s.score == 100
    trapped = good.model_copy(update={"agents_not_evacuated": 30})
    assert planning_score(trapped, **kw).grade == "F"
    few_left = good.model_copy(update={"agents_not_evacuated": 2})
    assert planning_score(few_left, **kw).grade == "D"
    crowded = good.model_copy(update={"peak_density_ppm2": 6.0, "evac_time_p95_s": 360})
    assert planning_score(crowded, **kw).score < 60
