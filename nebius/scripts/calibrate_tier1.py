"""Compare Tier 1 (instant estimate) with Tier 3 (simulation) on every template.

Writes api/data/calibration.json (the Tier1/Tier3 ratio per template, shown in reports).
Usage: uv run --project api python scripts/calibrate_tier1.py [template ...]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Scratch database: never share the app's SQLite file with the API container (WAL over the
# Docker Desktop file share is not coherent).
os.environ.setdefault(
    "DB_URL", f"sqlite:///{Path(__file__).resolve().parents[1] / 'cache/tmp/calibrate.sqlite'}"
)

from api.adapters.sandbox import DockerRunner
from api.core.plugins import load_plugins
from api.core.settings import ROOT_DIR, get_settings
from api.core.templates import get_template, list_templates
from api.db.session import migrate
from api.orchestrator.runs import RunService

OUT = ROOT_DIR / "api" / "data" / "calibration.json"


async def main(ids: list[str]) -> None:
    st = get_settings()
    migrate()
    host = load_plugins(ROOT_DIR)
    runner = DockerRunner(
        st.runs_dir, st.sim_image, st.sim_mem_limit, st.sim_cpus, sim_code_dir=ROOT_DIR / "sim"
    )
    svc = RunService(st, host.registry, runner)
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    for tid in ids or [t.venue_id for t in list_templates()]:
        v = get_template(tid)
        t1 = svc.estimate(v)
        t0 = time.monotonic()
        res = await svc.run(svc.build_job(v, tier=3, seed=st.default_seed), label=f"calib {tid}")
        m1, m3 = t1.metrics, res.metrics
        ratio = (
            m1.evac_time_p95_s / m3.evac_time_p95_s
            if m1.evac_time_p95_s and m3.evac_time_p95_s
            else None
        )
        print(
            f"{tid:20s} T1 p95={m1.evac_time_p95_s} peak={m1.peak_density_ppm2} | "
            f"T3 {res.status} p95={m3.evac_time_p95_s} peak={m3.peak_density_ppm2} "
            f"not_evac={m3.agents_not_evacuated} wall={time.monotonic() - t0:.0f}s "
            f"ratio={ratio and round(ratio, 2)}",
            flush=True,
        )
        print(
            "   T1 exits",
            [(p.exit_id, p.people) for p in m1.per_exit],
            "| T3 exits",
            [(p.exit_id, p.people, p.mean_flow_pps) for p in m3.per_exit],
            flush=True,
        )
        data[tid] = {
            "tier1_p95_s": m1.evac_time_p95_s,
            "tier3_p95_s": m3.evac_time_p95_s,
            "tier1_peak": m1.peak_density_ppm2,
            "tier3_peak": m3.peak_density_ppm2,
            "ratio_p95": ratio and round(ratio, 3),
            "run_id": res.run_id,
            "specific_flow": st.specific_flow,
            "agent_radius": st.agent_radius,
        }
        OUT.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
