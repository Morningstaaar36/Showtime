"""Sandbox entry point: /work/{request,venue,events,plan}.json -> result.json + artifacts.

Usage: python /app/run_sim.py /work
Always writes result.json (status ok | partial | timeout | failed) and prints a one-line
JSON summary to stdout for the adapter.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

import metrics  # noqa: E402

REGISTRY = json.loads((APP / "plugins" / "registry.json").read_text())


def _load(work: Path, name: str, default: Any) -> Any:
    p = work / name
    return json.loads(p.read_text()) if p.exists() else default


def _result_base(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": request.get("run_id", "r_unknown"),
        "tier": request.get("tier", 3),
        "status": "failed",
        "engine": request.get("engine", "jupedsim"),
        "metrics": {},
        "hotspots": [],
        "artifacts": {},
        "runtime_s": 0.0,
        "provider": request.get("provider", "docker"),
        "parent_run_id": request.get("parent_run_id"),
        "venue_hash": request.get("venue_hash", ""),
        "seed": request.get("seed", 42),
        "attack_id": request.get("attack_id"),
        "fix_id": request.get("fix_id"),
        "sim_time_s": 0.0,
        "notes": [],
        "error": None,
        "extensions": {},
    }


def main(work: Path) -> int:
    t0 = time.monotonic()
    request = _load(work, "request.json", {})
    result = _result_base(request)
    try:
        venue = _load(work, "venue.json", None)
        if venue is None:
            raise ValueError("venue.json is missing")
        base_venue = _load(work, "base_venue.json", None)
        events = _load(work, "events.json", [])
        plan = _load(work, "plan.json", {})
        settings: dict[str, Any] = dict(request.get("settings", {}))
        engine_id = request.get("engine", "jupedsim")
        spec = REGISTRY["engines"].get(engine_id)
        if spec is None:
            raise ValueError(f"engine '{engine_id}' is not installed in this image")
        engine = importlib.import_module(spec["module"])

        people = sum(int(z["people"]) for f in venue["floors"] for z in f.get("zones", []))
        people += sum(int(e.get("extra_people", 0)) for e in events if e.get("type") == "surge")
        people += sum(int(e.get("people", 0)) for e in events if e.get("type") == "counterflow")
        max_people = int(request.get("max_people", 3000))
        if people > max_people:
            raise ValueError(
                f"This scenario has {people:,} people but the limit is {max_people:,}. "
                "Raise MAX_PEOPLE in Settings or lower a zone's headcount."
            )
        frame_hz = float(settings.get("frame_hz") or (2.0 if people > 2500 else 4.0))
        settings["frame_dt"] = 1.0 / frame_hz
        if "dt" not in settings:
            # Tier 3 small crowds: 0.025 s (within ~4 % of 0.01 s); otherwise 0.05 s (~8 %
            # conservative) so 6,000-person runs fit a laptop. See docs/ASSUMPTIONS.md.
            tier = int(request.get("tier", 3))
            settings["dt"] = 0.025 if tier == 3 and people <= 2500 else 0.05

        raw = engine.run(work, request, venue, events, plan, settings, base_venue)
        outputs = raw["outputs"]
        floors = [f["floor_id"] for f in venue["floors"]]
        floor_index = {fid: i for i, fid in enumerate(floors)}
        times, frames = metrics.merge_frames(outputs, floor_index)
        x0, y0, nx, ny = metrics.grid_for(venue)
        bounds = metrics.bounds_for(venue)
        metrics.write_trajectory(work, times, frames, x0, y0, floors, bounds)
        warn = float(settings.get("density_warn_ppm2", 3.5))
        danger = float(settings.get("density_danger_ppm2", 5.0))
        dens = metrics.density_and_hotspots(
            work, venue, times, frames, x0, y0, nx, ny, warn, danger
        )
        evac = metrics.evacuation_metrics(
            outputs, raw["people_total"], venue, float(request.get("max_sim_s", 900))
        )
        notes: list[str] = []
        for out in outputs:
            notes.extend(n for n in out.notes if n not in notes)
        extra = dict(evac["extra"])
        try:
            for eid, val in metrics.exit_area_density(venue, times, frames, frame_hz).items():
                extra[f"exit_density_peak:{eid}"] = val
        except Exception as exc:  # PedPy is a bonus metric; never fail the run for it
            notes.append(f"PedPy exit-area density skipped: {type(exc).__name__}")
        extra.update(
            {
                "trapped": float(sum(o.trapped for o in outputs)),
                "sim_dt_s": float(settings["dt"]),
                "frame_hz": frame_hz,
                "stair_transfers": float(sum(len(o.stair_arrivals) for o in outputs)),
                **raw.get("rewind", {}),
            }
        )
        statuses = {o.status for o in outputs}
        status = (
            "timeout"
            if "timeout" in statuses
            else "partial"
            if "partial" in statuses or evac["not_evacuated"]
            else "ok"
        )
        if status == "partial" and int(request.get("tier", 3)) == 2:
            notes.append(
                f"Stopped at {request.get('max_sim_s')} s of simulated time (Tier 2 ranking run)."
            )
        result.update(
            {
                "status": status,
                "metrics": {
                    "evac_time_p95_s": evac["p95"],
                    "evac_time_max_s": evac["max"],
                    "peak_density_ppm2": round(dens["peak"], 2),
                    "time_above_danger_s": round(dens["above_danger_s"], 1),
                    "time_above_warning_s": round(dens["above_warn_s"], 1),
                    "agents_total": raw["people_total"],
                    "agents_evacuated": evac["evacuated"],
                    "agents_not_evacuated": evac["not_evacuated"],
                    "per_exit": evac["per_exit"],
                    "extra": extra,
                },
                "hotspots": dens["hotspots"],
                "artifacts": {
                    "trajectory": "traj.bin",
                    "trajectory_index": "traj_index.json",
                    "density_grid": "density.bin",
                    "density_index": "density_index.json",
                },
                "sim_time_s": max((o.sim_time for o in outputs), default=0.0),
                "notes": notes,
                "extensions": {
                    "marshals": [m for o in outputs for m in o.marshals],
                    "event_log": [e for o in outputs for e in o.event_log],
                },
            }
        )
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{exc}"
        result["notes"] = [traceback.format_exc(limit=4)[-1500:]]
    result["runtime_s"] = round(time.monotonic() - t0, 2)
    (work / "result.json").write_text(json.dumps(result))
    m = result.get("metrics", {})
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "status": result["status"],
                "rset_p95": m.get("evac_time_p95_s"),
                "peak": m.get("peak_density_ppm2"),
                "runtime_s": result["runtime_s"],
                "error": result["error"],
            }
        )
    )
    return 0 if result["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "/work")))
