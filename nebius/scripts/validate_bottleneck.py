"""Validate the simulator against the Jülich 2006 bottleneck experiment (DOI 10.34735/ped.2006.2).

For every width of the b-series (b090 ... b250): measure the flow through the bottleneck entrance
from the real trajectories with PedPy, simulate the same geometry and headcount in JuPedSim
(Tier 3, app defaults, one run per seed) and measure the simulated trajectories with the same
PedPy code (`sim/bottleneck_flow.py`, run in the sim image as a code job). Writes
api/data/validation.json. Needs `scripts/get_data.sh` (data/validation/bottleneck2006).

Usage: uv run --project api python scripts/validate_bottleneck.py [--runs b090 b120]
       [--seeds 1 2 3] [--people N] [--out PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Scratch database: never share the app's SQLite file (same reason as calibrate_tier1.py).
os.environ.setdefault("DB_URL", f"sqlite:///{ROOT / 'cache/tmp/validate.sqlite'}")

import shapely  # noqa: E402

from api.adapters.sandbox import CodeJob, DockerRunner  # noqa: E402
from api.core.plugins import load_plugins  # noqa: E402
from api.core.settings import ROOT_DIR, get_settings  # noqa: E402
from api.core.validation import (  # noqa: E402
    HOLDING_DENSITY_PPM2,
    VALIDATION_PATH,
    bottleneck_venue,
    error_pct,
    holding_depth,
    summarize,
)
from api.db.session import migrate  # noqa: E402
from api.models.validation import SimulatorValidation  # noqa: E402
from api.orchestrator.runs import RunService  # noqa: E402

DATA = ROOT_DIR / "data" / "validation" / "bottleneck2006"
SERIES = re.compile(
    r"^b\d{3}$"
)  # the width series (l = 4 m); l0/l2/l4 and n/d/bfl runs vary others
DEFAULT_SEEDS = [1, 2, 3]

MEASURE = """
import bottleneck_flow as bf
{load}
output = bf.line_flow(df, fr, (({x0}, 0.0), ({x1}, 0.0)), {b})
"""
LOAD_REAL = "df, fr = bf.load_juelich_txt('{name}')"
LOAD_SIM = "import showtime_data as sd\ndf, fr = bf.from_showtime(sd.load_trajectories(), {hz})"


def experiment_runs(names: list[str]) -> list[dict[str, Any]]:
    """Runs of the width series from the archive metadata, with the geometry checked."""
    meta = json.loads((DATA / "metadata.json").read_text())
    out = []
    for p in meta["experiment"]["parameters"]:
        name = p["run_name"]
        if not SERIES.match(name) or (names and name not in names):
            continue
        par = p["parameters"]
        b, length = float(par["bottleneck_width"]), float(par["bottleneck_length"])
        # the WKT has the walls as holes; the bottleneck walls' inner faces must be at +-b/2
        geom = shapely.from_wkt(p["wkt_geometry"])
        faces = sorted(min(abs(x) for x, _y in h.coords) for h in geom.interiors)
        if not all(abs(f - b / 2) < 1e-6 for f in faces):
            raise SystemExit(f"{name}: WKT walls {faces} do not match b = {b}")
        out.append(
            {
                "run_name": name,
                "b": b,
                "l": length,
                "n": int(p["number_participants"]),
                "corridor_w": float(par["floor_width"]),
                "distance": float(par["bottleneck_distance"]),
            }
        )
    return out


async def measure(runner: DockerRunner, job_id: str, inputs: dict[str, bytes], code: str) -> Any:
    res = await runner.run_code(
        CodeJob(
            job_id=job_id,
            kind="analysis",
            script=code,
            inputs=inputs,
            timeout_s=180,
            mem="1g",
        )
    )
    if res.status != "ok" or not isinstance(res.output, dict):
        raise SystemExit(f"{job_id}: measurement failed: {res.stderr_tail}")
    return res.output


async def main(args: argparse.Namespace) -> None:
    st = get_settings()
    migrate()
    host = load_plugins(ROOT_DIR)
    runner = DockerRunner(
        st.runs_dir, st.sim_image, st.sim_mem_limit, st.sim_cpus, sim_code_dir=ROOT_DIR / "sim"
    )
    svc = RunService(st, host.registry, runner)
    runs = experiment_runs(args.runs)
    if not runs:
        raise SystemExit("no matching runs in the metadata (run scripts/get_data.sh first?)")
    widths: list[dict[str, Any]] = []
    pedpy_version, frame_hz, dt = "", 0.0, 0.0
    repeat = ""
    for r in runs:
        name, b = r["run_name"], r["b"]
        line = {"x0": -b / 2, "x1": b / 2, "b": b}
        txt = (DATA / "txt" / f"{name}.txt").read_bytes()
        real = await measure(
            runner,
            f"val-real-{name}",
            {f"{name}.txt": txt},
            MEASURE.format(load=LOAD_REAL.format(name=f"/work/val-real-{name}/{name}.txt"), **line),
        )
        pedpy_version = real["pedpy"]
        n_sim = args.people or r["n"]
        venue = bottleneck_venue(name, b, r["l"], n_sim, r["corridor_w"], r["distance"])
        seed_runs = []
        for seed in args.seeds:
            t0 = time.monotonic()
            res = await svc.run(svc.build_job(venue, tier=3, seed=seed), label=f"validate {name}")
            if res.status not in ("ok", "partial") or not res.artifacts.trajectory:
                raise SystemExit(f"{name} seed {seed}: simulation {res.status}: {res.error}")
            frame_hz = float(res.metrics.extra.get("frame_hz", 4.0))
            dt = float(res.metrics.extra.get("sim_dt_s", 0.0))
            work = st.runs_dir / res.run_id
            sim = await measure(
                runner,
                f"val-sim-{res.run_id}",
                {
                    "traj.bin": (work / "traj.bin").read_bytes(),
                    "traj_index.json": (work / "traj_index.json").read_bytes(),
                },
                MEASURE.format(load=LOAD_SIM.format(hz=frame_hz), **line),
            )
            if sim["flow_ps"] is None:
                raise SystemExit(f"{name} seed {seed}: too few crossings ({sim['crossings']})")
            seed_runs.append(
                {
                    "seed": seed,
                    "run_id": res.run_id,
                    "flow_ps": sim["flow_ps"],
                    "crossings": sim["crossings"],
                    "window_s": sim["window_s"],
                }
            )
            print(
                f"{name} b={b:g} seed={seed} sim {sim['flow_ps']:.2f}/s "
                f"(people {res.metrics.agents_total}, crossings {sim['crossings']}, "
                f"wall {time.monotonic() - t0:.0f}s)",
                flush=True,
            )
        flows = [s["flow_ps"] for s in seed_runs]
        med = round(statistics.median(flows), 4)
        widths.append(
            {
                "run_name": name,
                "b_m": b,
                "l_m": r["l"],
                "n_people": n_sim,
                "measured_flow_ps": real["flow_ps"],
                "measured_specific_flow": real["specific_flow"],
                "measured_window_s": real["window_s"],
                "simulated_flow_ps": {
                    "median": med,
                    "min": min(flows),
                    "max": max(flows),
                    "runs": seed_runs,
                },
                "simulated_specific_flow": round(med / b, 4),
                "error_pct": error_pct(med, real["flow_ps"]),
            }
        )
        w = widths[-1]
        print(
            f"== {name}: measured {w['measured_flow_ps']:.2f}/s, simulated {med:.2f}/s "
            f"[{min(flows):.2f}-{max(flows):.2f}], error {w['error_pct']:+.1f}%",
            flush=True,
        )
    if not args.runs or "b120" in args.runs:
        # the l-series run l4 repeats b120's setup: a measure of experimental scatter
        l4 = DATA / "txt" / "l4.txt"
        if l4.exists():
            rep = await measure(
                runner,
                "val-real-l4",
                {"l4.txt": l4.read_bytes()},
                MEASURE.format(
                    load=LOAD_REAL.format(name="/work/val-real-l4/l4.txt"), x0=-0.6, x1=0.6, b=1.2
                ),
            )
            repeat = (
                f"Run l4 repeats the b120 setup (b = 1.2 m, l = 4 m, 178 people): "
                f"{rep['flow_ps']:.2f} /s measured with the same method"
            )
    errors = [w["error_pct"] for w in widths]
    med_abs, mean_err = summarize(errors)
    depth = holding_depth(runs[0]["n"], runs[0]["corridor_w"])
    report = {
        "schema_version": 1,
        "meta": {
            "dataset": "Jülich pedestrian dynamics archive: Bottleneck, Caserne (Düsseldorf, 2006)",
            "dataset_doi": "10.34735/ped.2006.2",
            "dataset_licence": "CC BY 4.0",
            "funding": "DFG projects KL 1873/1-1 and SE 1789/1-1",
            "papers": [
                {
                    "label": "Seyfried, Rupprecht, Passon, Steffen, Klingsch, Boltes: New insights "
                    "into pedestrian flow through bottlenecks. Transportation Science 43 (2009) "
                    "395-406",
                    "url": "https://doi.org/10.1287/trsc.1090.0263",
                },
                {
                    "label": "Seyfried et al.: Enhanced empirical data for the fundamental diagram "
                    "and the flow through bottlenecks. PED 2008 (Springer 2010)",
                    "url": "https://arxiv.org/abs/0810.1945",
                },
                {
                    "label": "Liddle et al.: An experimental study of pedestrian congestions: "
                    "influence of bottleneck width and length (arXiv 2009)",
                    "url": "https://arxiv.org/abs/0911.4350",
                },
            ],
            "method": "PedPy compute_n_t on a measurement line; flow = (k1 - k0) / (t_k1 - t_k0) "
            "over the crossings ranked k0..k1 (1 / mean time gap); specific flow = flow / b. "
            "Same code (sim/bottleneck_flow.py) for the experiment and the simulation.",
            "measurement_line": "bottleneck entrance, y = 0, from x = -b/2 to x = b/2",
            "steady_window": "crossings 10 to 150: skips the first 9 people (start-up) and "
            "ends at the 150th person like Liddle et al. (2009)",
            "engine": "JuPedSim 1.4.2 via the Showtime sim image (Tier 3)",
            "model": "collision-free speed model (app default), with the app's squeeze and "
            "unstick rules active",
            "pedpy_version": pedpy_version,
            "sim_image": st.sim_image,
            "agent_radius_m": st.agent_radius,
            "walk_speed": f"normal({st.walk_speed_mean}, {st.walk_speed_sd}) m/s clipped to "
            f"0.6-2.0; {st.slow_walker_fraction:.0%} slow walkers at 0.7 m/s",
            "sim_dt_s": dt,
            "frame_hz": frame_hz,
            "seeds": list(args.seeds),
            "app_defaults": True,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "assumptions": [
                "Geometry from the archive metadata (wkt_geometry and parameters): corridor "
                f"{runs[0]['corridor_w']:g} m wide in front of the bottleneck, bottleneck b x l, "
                "walls 5 cm thick; coordinates in the archive's frame (entrance on y = 0).",
                "The holding area is not specified in the metadata or papers: it spans the "
                f"corridor width and ends {runs[0]['distance']:g} m before the entrance "
                "('bottleneck_distance'); its depth gives an initial density of "
                f"{HOLDING_DENSITY_PPM2} persons/m2 (the value of the group's 2005 series, "
                f"Seyfried et al. 2009), e.g. {depth:g} m for {runs[0]['n']} people.",
                "Behind the bottleneck: an open area 8 m wide and 1 m deep (the metadata's "
                "bounding box), whose far edge is the exit, so the exit never limits the flow.",
                "Everyone starts walking at t = 0 (no reaction-time spread); the participants "
                "were soldiers told to walk normally, the simulation uses the app's adult "
                "walking speeds.",
                "Real trajectories are head positions at 25 fps; simulated positions are body "
                f"centres at {frame_hz:g} fps (app default output rate).",
            ],
            "experimental_repeat": repeat,
        },
        "widths": widths,
        "median_abs_error_pct": med_abs,
        "mean_error_pct": mean_err,
    }
    SimulatorValidation.model_validate(report)  # never write a file the API cannot serve
    out = Path(args.out) if args.out else VALIDATION_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"median |error| {med_abs}%, mean error {mean_err:+}% -> {out}")


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", nargs="*", default=[], help="run names, e.g. b090 b120")
    ap.add_argument("--seeds", nargs="*", type=int, default=DEFAULT_SEEDS)
    ap.add_argument("--people", type=int, default=0, help="override the headcount (tests)")
    ap.add_argument("--out", default="", help="output path (default api/data/validation.json)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    asyncio.run(main(parse(sys.argv[1:])))
