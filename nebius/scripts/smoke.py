"""End-to-end smoke test against a running Showtime API (section 14.5).

Usage: make smoke      (API at http://127.0.0.1:8000 or SHOWTIME_API=...)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("SHOWTIME_API", "http://127.0.0.1:8000") + "/api/v1"
T0 = time.monotonic()


def call(method: str, path: str, body: object | None = None, raw: bool = False) -> object:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Showtime": "1"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        data = r.read()
    return data if raw else json.loads(data or b"null")


def step(msg: str) -> None:
    print(f"[{time.monotonic() - T0:6.1f}s] {msg}", flush=True)


def mem_mb() -> int:
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) // 1024
    return -1


def main() -> int:
    lowest = mem_mb()
    h = call("GET", "/health")
    prov = h["providers"]
    step("health: " + ", ".join(f"{k}={'ok' if v['ok'] else 'NOT OK'}" for k, v in prov.items()))
    if not (prov["llm"]["ok"] and prov["sandbox"]["ok"]):
        print("LLM and sandbox must be up (make llm-up; make build-sim)")
        return 1
    p = call("POST", "/projects", {"template_id": "school_wing", "name": "Smoke test"})
    pid = p["id"]
    step(f"project {pid}")
    e = call("POST", f"/projects/{pid}/edit", {"text": "add a 2 m exit on the east side"})
    step(f"text edit: {e['status']} — {e['explanation']}")
    assert e["status"] in ("applied", "questions"), e
    v = call("POST", f"/venues/{pid}/validate")
    assert v["ok"], v
    t1 = call("POST", f"/venues/{pid}/tier1", {})
    step(
        f"instant estimate: 95% out in {t1['metrics']['evac_time_p95_s']} s "
        f"({t1['runtime_s'] * 1000:.0f} ms)"
    )
    run = call("POST", "/runs", {"project_id": pid, "tier": 3, "seed": 42})
    while run["status"] in ("queued", "running"):
        time.sleep(2)
        lowest = min(lowest, mem_mb())
        run = call("GET", f"/runs/{run['id']}")
    m = run["result"]["metrics"]
    step(
        f"tier 3: {run['status']} · 95% out in {m['evac_time_p95_s']} s · peak {m['peak_density_ppm2']}"
    )
    assert run["status"] in ("ok", "partial"), run
    s = call(
        "POST",
        "/sessions",
        {
            "project_id": pid,
            "config": {
                "max_rounds": 1,
                "attacks_per_round": 2,
                "fixes_per_attack": 1,
                "fix_targets": 1,
            },
        },
    )
    step(f"red team session {s['id']}")
    with urllib.request.urlopen(f"{BASE}/sessions/{s['id']}/events", timeout=1800) as r:
        for raw in r:
            line = raw.decode().strip()
            if line.startswith("data:") and line[5:].strip() not in ("", "{}"):
                ev = json.loads(line[5:])
                if ev["type"] == "status":
                    step(f"  {ev['payload']['phase']}: {ev['payload']['message']}")
            if line.startswith("event: end"):
                break
            lowest = min(lowest, mem_mb())
    s = call("GET", f"/sessions/{s['id']}")
    step(f"session {s['status']} · scoreboard {s['summary']['scoreboard']} · tokens {s['tokens']}")
    report = call("GET", f"/sessions/{s['id']}/report", raw=True)
    svg = call("GET", f"/sessions/{s['id']}/map.svg", raw=True)
    assert b"Planning aid, not a safety certification" in report
    assert b"Planning aid, not a safety certification" in svg
    step(f"report {len(report) / 1024:.0f} KB, map {len(svg) / 1024:.0f} KB (disclaimer present)")
    call("DELETE", f"/projects/{pid}", raw=True)
    step(f"SMOKE OK · lowest free RAM during test {lowest} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
