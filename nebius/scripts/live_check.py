"""Live end-to-end check against the running API (make up): one sentence → venue → simulation
→ red team, printing what a person would see. Uses the real model and the real simulator.

    python scripts/live_check.py "Hospital with 4 floors, 60 x 25 m, wards ..." [--rounds 2]
    python scripts/live_check.py --project p_123 --rounds 2      # red team an existing project
    python scripts/live_check.py --case love_parade_2010         # rebuild and test a real case

Prints the design (floors, people, stairs), the stress test and, with --rounds, the red-team
session: rounds, breaks, failure-map coverage and every cell's strongest attack.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

API = "http://127.0.0.1:8000/api/v1"


def call(method: str, path: str, body: Any = None, timeout: float = 600) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, method=method, data=data, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        return {"_error": exc.code, "_body": exc.read().decode()[:400]}


def wait_run(run_id: str) -> dict[str, Any]:
    while True:
        run = call("GET", f"/runs/{run_id}")
        if run.get("status") not in ("queued", "running"):
            return run
        time.sleep(5)


def design(text: str) -> str | None:
    t0 = time.time()
    out = call("POST", "/venues/design", {"text": text})
    venue = out.get("venue")
    if not venue:
        print("design failed:", out)
        return None
    floors = [(f["floor_id"], sum(z["people"] for z in f["zones"])) for f in venue["floors"]]
    print(f"design {out['status']} in {time.time() - t0:.0f} s · floors {floors}")
    print(f"  stairs {len(venue.get('stairs', []))} · problems {out.get('problems') or 'none'}")
    project = call("POST", "/projects", {"name": f"Live check · {venue['name']}", "venue": venue})
    if "_error" in project:
        print("project failed:", project)
        return None
    run = wait_run(call("POST", "/runs", {"project_id": project["id"], "tier": 3})["id"])
    res = run.get("result") or {}
    m = res.get("metrics") or {}
    ex = m.get("extra") or {}
    mix = {k[7:]: int(v) for k, v in ex.items() if k.startswith("people_")}
    print(
        f"stress test {run.get('status')}: {m.get('agents_evacuated')}/{m.get('agents_total')} out"
        f" · 95% in {m.get('evac_time_p95_s')} s · peak {m.get('peak_density_ppm2')} per m²"
        f" · turbulent {ex.get('time_turbulent_s')} s · people mix {mix or 'none'}"
    )
    print("project", project["id"])
    return str(project["id"])


def describe_venue(project_id: str) -> None:
    v = call("GET", f"/projects/{project_id}")["version"]["venue"]
    for f in v["floors"]:
        xs = [p[0] for p in f["walkable"]]
        ys = [p[1] for p in f["walkable"]]
        print(
            f"  {f['floor_id']} {max(xs) - min(xs):.0f}×{max(ys) - min(ys):.0f} m · "
            f"exits {[(e.get('label') or e['id'], e['width_m']) for e in f['exits']]} · "
            f"people {sum(z['people'] for z in f['zones'])} · "
            f"obstacles {sorted({o.get('label') or o['kind'] for o in f['obstacles']})[:6]}"
        )


def follow(sid: str) -> dict[str, Any]:
    t0, last = time.time(), ""
    while True:
        time.sleep(10)
        session = call("GET", f"/sessions/{sid}")
        arch = call("GET", f"/sessions/{sid}/archive")
        line = f"coverage {arch.get('coverage')} · QD-score {arch.get('qd_score')}"
        if line != last:
            print(f"[{time.time() - t0:4.0f} s] {line}", flush=True)
            last = line
        if session.get("status") not in ("running", "queued"):
            return {"session": session, "archive": arch}


def summarize(sid: str, session: dict[str, Any], arch: dict[str, Any]) -> None:
    summary = session.get("summary") or {}
    print("session", sid, session.get("status"), "· stopped:", summary.get("stopped_reason"))
    for row in summary.get("scoreboard") or []:
        print("  round", row.get("round"), "· breaks", row.get("breaks"), "of", row.get("attacks"))
    fixes = {f["fix_id"]: f["title"] for f in summary.get("fixes") or []}
    print("  kept fixes:", [fixes.get(i, i) for i in summary.get("accepted_fixes") or []])
    before = summary.get("before") or {}
    print(
        "  before fixes: peak",
        before.get("peak_density_ppm2"),
        "per m² · above danger",
        before.get("time_above_danger_s"),
        "s · still inside",
        before.get("agents_not_evacuated"),
    )
    for cell in arch.get("cells") or []:
        for e in cell.get("elites", [])[:1]:
            print(
                f"  {cell['kind']:<14} {cell['where']:<18} sev {e['severity']:.2f}"
                f" {'BREAK' if e['is_break'] else 'holds'} · {e.get('generated_by')}: {e['title']}"
            )
    if summary.get("judge_text"):
        print("  judge:", str(summary["judge_text"])[:300])


def real_case(case_id: str) -> None:
    t0 = time.time()
    out = call("POST", f"/real_cases/{case_id}/open")
    if "_error" in out:
        print("open failed:", out)
        return
    print(
        f"case {case_id}: {out.get('status')} in {time.time() - t0:.0f} s · project {out['project_id']}"
    )
    describe_venue(out["project_id"])
    if out.get("session_id"):
        res = follow(out["session_id"])
        summarize(out["session_id"], res["session"], res["archive"])


def red_team(project_id: str, rounds: int) -> None:
    started = call(
        "POST",
        "/sessions",
        {"project_id": project_id, "config": {"max_rounds": rounds, "attacks_per_round": 3}},
    )
    sid = started.get("id")
    if not sid:
        print("session failed:", started)
        return
    t0, last = time.time(), ""
    while True:
        time.sleep(10)
        session = call("GET", f"/sessions/{sid}")
        arch = call("GET", f"/sessions/{sid}/archive")
        line = f"coverage {arch.get('coverage')} · QD-score {arch.get('qd_score')}"
        if line != last:
            print(f"[{time.time() - t0:4.0f} s] {line}", flush=True)
            last = line
        if session.get("status") not in ("running", "queued"):
            break
    summary = session.get("summary") or {}
    print("session", sid, session.get("status"), "· stopped:", summary.get("stopped_reason"))
    for row in summary.get("scoreboard") or []:
        print("  round", row.get("round"), "· breaks", row.get("breaks"), "of", row.get("attacks"))
    fixes = {f["fix_id"]: f["title"] for f in summary.get("fixes") or []}
    print("  kept fixes:", [fixes.get(i, i) for i in summary.get("accepted_fixes") or []])
    for cell in arch.get("cells") or []:
        for e in cell.get("elites", [])[:1]:
            print(
                f"  {cell['kind']:<14} {cell['where']:<18} sev {e['severity']:.2f}"
                f" {'BREAK' if e['is_break'] else 'holds'} · {e.get('generated_by')}: {e['title']}"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("text", nargs="?", help="one sentence describing the venue")
    ap.add_argument("--project", help="an existing project to red team instead")
    ap.add_argument("--rounds", type=int, default=0, help="red-team rounds (0 = none)")
    ap.add_argument("--case", help="a real case id to rebuild and test (GET /real_cases)")
    args = ap.parse_args()
    if args.case:
        real_case(args.case)
        return
    project = args.project or (design(args.text) if args.text else None)
    if project is None:
        sys.exit("Give a description or --project.")
    if args.rounds:
        red_team(project, args.rounds)


if __name__ == "__main__":
    main()
