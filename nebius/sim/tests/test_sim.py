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
