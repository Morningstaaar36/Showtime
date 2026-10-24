"""Simulation tests (section 14.2). They run the real sim image on small crowds.

Run with: make test-sim   (needs Docker and showtime-sim:latest, or the image in SIM_IMAGE)
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from api.tests.docker_check import docker_unavailable

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs" / "_simtests"
pytestmark = pytest.mark.slow  # registered in api/pyproject.toml
IMAGE = os.environ.get("SIM_IMAGE", "showtime-sim:latest")

SETTINGS = {
    "walk_speed_mean": 1.34,
    "walk_speed_sd": 0.26,
    "slow_walker_fraction": 0.05,
    "agent_radius": 0.22,
    "specific_flow": 1.3,
    "density_warn_ppm2": 3.5,
    "density_danger_ppm2": 5.0,
    "stair_speed": 0.6,
    "stair_flow": 1.0,
}


_REASON = docker_unavailable(IMAGE)
if _REASON:
    pytest.skip(_REASON, allow_module_level=True)


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def room(people: int = 50, exits: int = 1) -> dict[str, Any]:
    ex = [{"id": "e_south", "polygon": rect(4, 0.02, 6, 0.42), "width_m": 2.0}]
    if exits > 1:
        ex.append({"id": "e_east", "polygon": rect(11.58, 6, 11.98, 8), "width_m": 2.0})
    return {
        "venue_id": "room",
        "name": "Room",
        "mode": "indoor",
        "floors": [
            {
                "floor_id": "F0",
                "elevation_m": 0,
                "walkable": rect(0, 0, 12, 10),
                "obstacles": [],
                "exits": ex,
                "zones": [{"id": "z", "polygon": rect(1, 5, 9, 9), "people": people}],
            }
        ],
        "stairs": [],
    }


def two_floor(people_top: int = 40, people_ground: int = 20) -> dict[str, Any]:
    v = room(people_ground)
    v["floors"].append(
        {
            "floor_id": "F1",
            "elevation_m": 4,
            "walkable": rect(0, 5, 12, 10),
            "obstacles": [],
            "exits": [],
            "zones": [{"id": "up", "polygon": rect(1, 6, 7, 9), "people": people_top}],
        }
    )
    v["stairs"] = [
        {
            "id": "st",
            "from_floor": "F1",
            "to_floor": "F0",
            "top_polygon": rect(9, 6, 11, 9),
            "bottom_polygon": rect(9, 1, 11, 4),
            "width_m": 1.2,
            "length_m": 6,
        }
    ]
    return v


def run(
    venue: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
    seed: int = 1,
    dt: float = 0.05,
    intervention: float | None = None,
    base: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    checkpoint: Path | None = None,
    max_sim_s: float = 300,
) -> tuple[dict[str, Any], Path]:
    work = RUNS / f"t_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True)
    if checkpoint is not None:
        shutil.copy(checkpoint, work / "checkpoint.json")
    req = {
        "run_id": work.name,
        "venue_id": venue["venue_id"],
        "tier": 3,
        "seed": seed,
        "max_people": 2000,
        "max_sim_s": max_sim_s,
        "max_wall_s": 120,
        "engine": "jupedsim",
        "intervention_at_s": intervention,
        "settings": {**SETTINGS, "dt": dt},
        **(request or {}),
    }
    (work / "request.json").write_text(json.dumps(req))
    (work / "venue.json").write_text(json.dumps(venue))
    (work / "events.json").write_text(json.dumps(events or []))
    if base is not None:
        (work / "base_venue.json").write_text(json.dumps(base))
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--memory=1g",
            "--cpus=2",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--label",
            "com.showtime.project=true",
            "-e",
            "MPLCONFIGDIR=/tmp",
            "-v",
            f"{ROOT / 'sim'}:/app:ro",
            "-v",
            f"{work}:/work",
            IMAGE,
            "python",
            "/app/run_sim.py",
            "/work",
        ],
        check=False,
        capture_output=True,
        timeout=240,
    )
    return json.loads((work / "result.json").read_text()), work


def frames(work: Path) -> list[tuple[float, bytes]]:
    idx = json.loads((work / "traj_index.json").read_text())
    data = (work / "traj.bin").read_bytes()
    out = []
    for t, off in zip(idx["times"], idx["offsets"], strict=True):
        (n,) = struct.unpack_from("<I", data, off)
        out.append((t, data[off : off + 4 + 7 * n]))
    return out


def test_one_room_everyone_leaves() -> None:
    res, work = run(room(50))
    m = res["metrics"]
    assert res["status"] == "ok", res
    assert m["agents_total"] == 50
    assert m["agents_evacuated"] == 50
    assert m["evac_time_p95_s"] > 0
    assert (work / "traj.bin").stat().st_size > 0
    assert (work / "density.bin").stat().st_size > 0


def test_blocking_exit_increases_rset() -> None:
    open_res, _ = run(room(80, exits=2))
    blocked, _ = run(room(80, exits=2), [{"type": "block_exit", "exit_id": "e_east", "at_s": 0}])
    assert blocked["metrics"]["agents_evacuated"] == 80
    assert blocked["metrics"]["evac_time_p95_s"] > open_res["metrics"]["evac_time_p95_s"]


def test_people_mix_is_simulated_and_listed() -> None:
    plain, _ = run(room(60))
    venue = room(60)
    venue["floors"][0]["zones"][0]["groups"] = [
        {"kind": "wheelchair", "share": 0.25},
        {"kind": "elderly", "share": 0.25},
    ]
    mixed, work = run(venue)
    assert mixed["metrics"]["agents_evacuated"] == 60
    assert mixed["metrics"]["evac_time_p95_s"] > plain["metrics"]["evac_time_p95_s"]
    kinds = json.loads((work / "agents.json").read_text())["kinds"]
    assert sorted(kinds.values()).count("wheelchair") == 15
    assert sorted(kinds.values()).count("elderly") == 15
    assert mixed["metrics"]["extra"]["people_wheelchair"] == 15
    assert mixed["artifacts"]["agents"] == "agents.json"
    assert "agents" not in plain["artifacts"]


def test_people_mix_stays_slow_down_the_stairs() -> None:
    plain, _ = run(two_floor(24, 0))
    venue = two_floor(24, 0)
    venue["floors"][1]["zones"][0]["groups"] = [{"kind": "bed", "share": 0.125}]
    beds, work = run(venue)
    assert beds["metrics"]["agents_evacuated"] == 24
    assert beds["metrics"]["evac_time_p95_s"] > plain["metrics"]["evac_time_p95_s"]
    assert list(json.loads((work / "agents.json").read_text())["kinds"].values()).count("bed") == 3


def test_every_exit_blocked_counts_people_as_not_evacuated() -> None:
    venue = room(40)
    venue["floors"][0]["exits"][0]["blocked"] = True
    res, _ = run(venue)
    m = res["metrics"]
    assert res["status"] == "partial", res
    assert m["agents_total"] == 40
    assert m["agents_evacuated"] == 0
    assert m["agents_not_evacuated"] == 40
    assert m["extra"]["trapped"] == 40


def test_same_seed_same_result_different_seed_small_variation() -> None:
    a, _ = run(room(60), seed=7)
    b, _ = run(room(60), seed=7)
    c, _ = run(room(60), seed=8)
    assert a["metrics"] == b["metrics"]
    ra, rc = a["metrics"]["evac_time_p95_s"], c["metrics"]["evac_time_p95_s"]
    assert ra != rc or a["metrics"]["peak_density_ppm2"] != c["metrics"]["peak_density_ppm2"]
    assert abs(ra - rc) / ra < 0.25


def test_intervention_identical_before_t() -> None:
    base = room(80, exits=1)
    fixed = room(80, exits=2)
    parent, wp = run(base, seed=3)
    child, wc = run(fixed, seed=3, intervention=10.0, base=base)
    assert child["status"] in ("ok", "partial")
    fp, fc = frames(wp), frames(wc)
    before = [(t, b) for t, b in fp if t < 10.0]
    assert before and before == [(t, b) for t, b in fc if t < 10.0]
    assert child["metrics"]["evac_time_p95_s"] < parent["metrics"]["evac_time_p95_s"]


def test_multi_floor_conserves_people() -> None:
    res, _ = run(two_floor(40, 20))
    m = res["metrics"]
    assert m["agents_total"] == 60
    assert m["agents_evacuated"] == 60
    assert m["extra"]["stair_transfers"] == 40


def test_surge_and_slowdown_events() -> None:
    res, _ = run(
        room(30),
        [
            {"type": "surge", "zone_id": "z", "extra_people": 20, "at_s": 5},
            {"type": "slowdown", "factor": 0.5, "at_s": 0},
        ],
    )
    assert res["metrics"]["agents_total"] == 50
    assert res["metrics"]["agents_evacuated"] == 50
    normal, _ = run(room(30))
    assert res["metrics"]["evac_time_p95_s"] > normal["metrics"]["evac_time_p95_s"]


def test_one_way_stops_counterflow() -> None:
    cf = [{"type": "counterflow", "exit_id": "e_south", "people": 30, "at_s": 0}]
    res, _ = run(room(40, exits=2), cf)
    held, _ = run(room(40, exits=2), [*cf, {"type": "one_way", "exit_id": "e_south", "at_s": 0}])
    assert res["metrics"]["agents_total"] > held["metrics"]["agents_total"] == 40


def test_time_step_calibration() -> None:
    """dt = 0.05 s (used for speed) is conservative: at most 15 % slower than dt = 0.01 s
    on a small room (about 8 % on the 1,200-person hall, see docs/ASSUMPTIONS.md)."""
    fine, _ = run(room(60), dt=0.01, seed=5)
    coarse, _ = run(room(60), dt=0.05, seed=5)
    rf, rc = fine["metrics"]["evac_time_p95_s"], coarse["metrics"]["evac_time_p95_s"]
    assert rc >= rf * 0.97, (rf, rc)
    assert (rc - rf) / rf < 0.15, (rf, rc)


def test_invalid_input_reports_readable_error() -> None:
    v = room(10)
    v["floors"][0]["walkable"] = [[0, 0], [1, 0]]
    res, _ = run(v)
    assert res["status"] == "failed"
    assert res["error"]


def _hall(exit_width: float, people: int = 150) -> dict[str, Any]:
    v = room(people)
    f = v["floors"][0]
    f["walkable"] = rect(0, 0, 16, 12)
    half = exit_width / 2
    f["exits"] = [
        {"id": "e", "polygon": rect(8 - half, 0.02, 8 + half, 0.42), "width_m": exit_width}
    ]
    f["zones"][0]["polygon"] = rect(1, 4, 15, 11)
    return v


def test_crowd_pressure_layer_and_level_of_service() -> None:
    """pressure.bin uses the density layout; a bottleneck shows more crowd pressure than an
    open room (Helbing et al. 2007), and Fruin LoS shares cover every person-second."""
    narrow, wn = run(_hall(0.8))
    wide, ww = run(_hall(6.0))
    for res, work in ((narrow, wn), (wide, ww)):
        assert res["status"] == "ok", res
        assert res["artifacts"]["pressure_grid"] == "pressure.bin"
        idx = json.loads((work / "pressure_index.json").read_text())
        data = (work / "pressure.bin").read_bytes()
        assert idx["format"] == "showtime-pressure-v1" and idx["danger"] == 0.02
        assert len(data) == idx["shape"][0] * idx["shape"][1] * idx["nx"] * idx["ny"] > 0
        assert len(idx["times"]) == idx["shape"][0]
        e = res["metrics"]["extra"]
        assert e["peak_pressure"] >= 0 and e["time_turbulent_s"] >= 0
        assert abs(sum(e[f"los_share_{b}"] for b in "ABCDEF") - 1.0) < 1e-3
    en, ew = narrow["metrics"]["extra"], wide["metrics"]["extra"]
    assert en["peak_pressure"] > ew["peak_pressure"]
    assert en["time_turbulent_s"] > ew["time_turbulent_s"]
    assert en["los_share_F"] > ew["los_share_F"]
    hot = narrow["extensions"]["turbulence_hotspots"]
    assert hot and {"floor_id", "x", "y", "t_s", "peak_pressure_per_s2"} <= set(hot[0])


def two_stairs(people_top: int = 40) -> dict[str, Any]:
    v = two_floor(people_top, 10)
    v["floors"][1]["zones"][0]["polygon"] = rect(3.5, 5.5, 8.5, 9.5)
    v["stairs"].append(
        {
            "id": "st_w",
            "from_floor": "F1",
            "to_floor": "F0",
            "top_polygon": rect(0.5, 6, 2.5, 9),
            "bottom_polygon": rect(1, 1.5, 3, 4),
            "width_m": 1.2,
            "length_m": 6,
        }
    )
    return v


def test_stair_events_slow_floor_and_slower_walkers() -> None:
    """block_exit and counterflow take a stair id; slowdown takes a floor id; mobility_share
    slows a fixed share of people on the level and on the stairs."""
    base, _ = run(two_stairs())
    lost, _ = run(two_stairs(), [{"type": "block_exit", "exit_id": "st_w", "at_s": 0}])
    for res in (base, lost):
        assert res["metrics"]["agents_evacuated"] == 50, res
        assert res["metrics"]["extra"]["stair_transfers"] == 40
    t0 = base["metrics"]["evac_time_p95_s"]
    assert lost["metrics"]["evac_time_p95_s"] > t0
    assert any(e["type"] == "block_exit" for e in lost["extensions"]["event_log"])
    smoke, _ = run(two_stairs(), [{"type": "slowdown", "factor": 0.5, "floor_id": "F1"}])
    assert smoke["metrics"]["evac_time_p95_s"] > t0
    slow, _ = run(two_stairs(), [{"type": "mobility_share", "share": 0.3, "speed_mps": 0.5}])
    assert slow["metrics"]["agents_evacuated"] == 50
    assert slow["metrics"]["evac_time_p95_s"] > t0
    up = [{"type": "counterflow", "exit_id": "st", "people": 4, "target_zone_id": "up", "at_s": 0}]
    ff, _ = run(two_stairs(), up)
    assert ff["status"] in ("ok", "partial"), ff
    assert ff["metrics"]["agents_total"] == 54
