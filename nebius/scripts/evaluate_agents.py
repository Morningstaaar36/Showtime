"""S-01 / P3-07: rules-only vs model-only vs hybrid red/blue sessions on the same venues, with the
same constraints, seed and simulation budget. Runs against a running API (the provider set in its
.env: OpenRouter for this study, Nebius for N-01) and writes the raw numbers and a Markdown table.

  python scripts/evaluate_agents.py [--base http://127.0.0.1:8000] [--arms rules,model,hybrid]
                                    [--venues school_wing,conference_hall_2f:300,t_alley:400]
                                    [--out docs/evaluation]

A venue is `template[:people]`: people scales the headcount (the sim image is amd64; on an ARM
laptop it runs emulated, so the study uses a few hundred people per venue). Every number in the
table comes from the session's own event stream (agent calls, cards, branch nodes, run events).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARMS = ("rules", "model", "hybrid")
AGENTS = ("red_team", "blue_team")  # the proposals being compared; judge/analyst are the same
CONFIG = {
    "max_rounds": 1,
    "attacks_per_round": 3,
    "fixes_per_attack": 2,
    "fix_targets": 2,
    "seed": 42,
    "max_runs": 12,
}


def call(base: str, method: str, path: str, body: Any = None, timeout: float = 120) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base}/api/v1{path}",
        data=data,
        method=method,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def events(base: str, sid: str) -> list[dict[str, Any]]:
    """The stored stream of a finished session (SSE replay, then `end`)."""
    out: list[dict[str, Any]] = []
    with urllib.request.urlopen(f"{base}/api/v1/sessions/{sid}/events", timeout=600) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            d = json.loads(line[5:])
            if not d:
                break
            out.append(d)
    return out


def venue_project(base: str, spec: str) -> str:
    template, _, people = spec.partition(":")
    p = call(base, "POST", "/projects", {"template_id": template, "name": f"Evaluation · {spec}"})
    if people:
        venue = call(base, "GET", f"/projects/{p['id']}")["version"]["venue"]
        zones = [z for f in venue["floors"] for z in f["zones"]]
        total = sum(z["people"] for z in zones) or 1
        ops = [
            {
                "op": "set_people",
                "zone_id": z["id"],
                "people": max(1, round(z["people"] * int(people) / total)),
            }
            for z in zones
        ]
        call(
            base,
            "POST",
            f"/projects/{p['id']}/patch",
            {"patch": {"ops": ops}, "message": f"Evaluation headcount {people}"},
        )
    return str(p["id"])


def run_arm(base: str, project: str, arm: str, wait_s: float) -> dict[str, Any]:
    t0 = time.time()
    s = call(
        base, "POST", "/sessions", {"project_id": project, "config": {**CONFIG, "agents": arm}}
    )
    sid = s["id"]
    while time.time() - t0 < wait_s:
        s = call(base, "GET", f"/sessions/{sid}")
        if s["status"] not in ("queued", "running"):
            break
        time.sleep(5)
    else:
        call(base, "POST", f"/sessions/{sid}/stop")
        s = call(base, "GET", f"/sessions/{sid}")
    return {"session": s, "events": events(base, sid), "wall_s": round(time.time() - t0, 1)}


def measure(raw: dict[str, Any]) -> dict[str, Any]:
    """The comparison's numbers, from one session's events and summary."""
    ev, s = raw["events"], raw["session"]
    summary = s.get("summary") or {}
    calls = [e["payload"] for e in ev if e["type"] == "agent_call"]
    prop = [c for c in calls if c.get("agent") in AGENTS]
    logs = [str(e["payload"].get("message", "")) for e in ev if e["type"] == "log"]
    nodes: dict[str, dict[str, Any]] = {}
    for e in ev:
        if e["type"] == "branch_node":
            nodes[e["payload"]["node_id"]] = {
                **nodes.get(e["payload"]["node_id"], {}),
                **e["payload"],
            }
    attacks = [
        n for n in nodes.values() if n.get("kind") == "attack" and ":current:" not in n["node_id"]
    ]
    fixes = [n for n in nodes.values() if n.get("kind") == "fix"]
    runs = [e["payload"] for e in ev if e["type"] == "run_finished"]
    evaluation = summary.get("evaluation") or {}
    final = next((n for n in nodes.values() if n["node_id"] == "final:after"), None)
    before = next((n for n in nodes.values() if n["node_id"] == "final:before"), None)
    return {
        "status": s.get("status"),
        "attacks": len([e for e in ev if e["type"] == "attack_card"]),
        "attacks_breaking": sum(1 for n in attacks if n.get("status") == "break"),
        "rule_attacks_added": sum(
            1
            for m in logs
            if "Rule-based attacks were added" in m or "built-in example script" in m
        ),
        "agent_calls": len(prop),
        "invalid_outputs": sum(1 for c in prop if not c.get("ok")),
        "spatial_errors_first": sum(int(c.get("problems_first", 0)) for c in prop),
        "spatial_errors_left": sum(int(c.get("problems", 0)) for c in prop),
        "repairs": sum(1 for c in prop if c.get("repaired")),
        "escalations": sum(1 for c in prop if c.get("escalated")),
        "cached_calls": sum(1 for c in calls if c.get("cached")),
        "model_ms": round(sum(float(c.get("ms", 0)) for c in prop)),
        "tokens": sum(int(c.get("tokens_in", 0)) + int(c.get("tokens_out", 0)) for c in calls),
        "cost_usd": round(sum(float(c.get("cost_usd", 0)) for c in calls), 6),
        "fixes_feasible": len([e for e in ev if e["type"] == "fix_card"]),
        "fixes_infeasible": sum(1 for m in logs if m.startswith("Rejected complete fix bundle")),
        "fixes_kept": len(summary.get("accepted_fixes") or []),
        "regressions": sum(
            1 for n in fixes if isinstance(n.get("gain"), (int, float)) and n["gain"] < 0
        ),
        "simulations": len(runs),
        "evaluation": evaluation.get("status"),
        "before_p95_s": (before or {}).get("metrics", {}).get("evac_time_p95_s")
        if before
        else None,
        "after_p95_s": (final or {}).get("metrics", {}).get("evac_time_p95_s") if final else None,
        "wall_s": raw["wall_s"],
        "models": sorted({c.get("model", "") for c in prop if c.get("model")}),
    }


COLUMNS = [
    ("venue", "Venue"),
    ("arm", "Arm"),
    ("attacks", "Attacks"),
    ("attacks_breaking", "Broke the plan"),
    ("spatial_errors_first", "Spatial errors (first answer)"),
    ("spatial_errors_left", "Left after repair"),
    ("invalid_outputs", "Invalid outputs"),
    ("fixes_feasible", "Feasible fixes"),
    ("fixes_infeasible", "Infeasible"),
    ("fixes_kept", "Kept"),
    ("regressions", "Regressions"),
    ("repairs", "Repairs"),
    ("escalations", "Escalations"),
    ("cached_calls", "Cached calls"),
    ("model_ms", "Model time (ms)"),
    ("tokens", "Tokens"),
    ("cost_usd", "Cost (USD)"),
    ("simulations", "Simulations"),
    ("wall_s", "Wall (s)"),
    ("evaluation", "Evaluation"),
]


def table(rows: list[dict[str, Any]]) -> str:
    head = "| " + " | ".join(c[1] for c in COLUMNS) + " |"
    sep = (
        "|"
        + "|".join(
            " ---: " if c[0] not in ("venue", "arm", "evaluation") else " --- " for c in COLUMNS
        )
        + "|"
    )
    body = [
        "| " + " | ".join("–" if r.get(k) is None else str(r.get(k)) for k, _ in COLUMNS) + " |"
        for r in rows
    ]
    return "\n".join([head, sep, *body])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--venues", default="school_wing,conference_hall_2f:300,t_alley:400")
    ap.add_argument("--out", default="docs/evaluation")
    ap.add_argument(
        "--wait", type=float, default=1500, help="seconds per session before it is stopped"
    )
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    health = call(a.base, "GET", "/health")
    llm = health["providers"]["llm"]
    print(
        f"LLM: {llm.get('provider')} {llm.get('label')} {llm.get('models')}; sandbox: {health['providers']['sandbox']['provider']}",
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for spec in a.venues.split(","):
        project = venue_project(a.base, spec)
        for arm in a.arms.split(","):
            print(f"{spec} · {arm} …", flush=True)
            try:
                raw = run_arm(a.base, project, arm, a.wait)
            except urllib.error.URLError as exc:
                print(f"  failed: {exc}", flush=True)
                continue
            row = {"venue": spec, "arm": arm, **measure(raw)}
            rows.append(row)
            print("  " + json.dumps(row), flush=True)
            (out / f"{stamp}-{spec.replace(':', '_')}-{arm}.json").write_text(
                json.dumps({"row": row, **raw}, indent=1, default=str)
            )
    md = table(rows)
    (out / f"{stamp}-table.md").write_text(md + "\n")
    meta = {
        "stamp": stamp,
        "llm": llm,
        "sandbox": health["providers"]["sandbox"],
        "config": CONFIG,
        "rows": rows,
    }
    (out / f"{stamp}-summary.json").write_text(json.dumps(meta, indent=1, default=str))
    print(md)


if __name__ == "__main__":
    main()
