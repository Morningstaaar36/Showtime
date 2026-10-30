"""A real case, end to end through the running app, as an organizer would do it.

Writes the case (as the "Add a real case" form does), opens it so the designer builds the venue
in rounds and the red team tests it, then presses "Let the AI fix it" and waits until the plan
holds or the loop ends. Prints each step and writes the record to <case>.run.json: the design
rounds, the site the map found, every test, the fixes the simulator proved and applied, and the
model calls it took. Nothing in here knows the case: it reads it from the file.

Usage: make live-case CASE=docs/examples/bailey-road-case.json   (needs the AI: real model calls)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = os.environ.get("SHOWTIME_API", "http://127.0.0.1:8000") + "/api/v1"
POLL_S = 5.0
T0 = time.monotonic()


def call(method: str, path: str, body: object | None = None, timeout: float = 900) -> Any:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Showtime": "1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return json.loads(data or b"null")


def say(msg: str) -> None:
    print(f"[{time.monotonic() - T0:6.0f} s] {msg}", flush=True)


def wait_session(sid: str, limit_s: float = 3600) -> dict[str, Any]:
    end = time.monotonic() + limit_s
    while time.monotonic() < end:
        s = call("GET", f"/sessions/{sid}")
        if s["status"] not in ("running", "queued"):
            return dict(s)
        time.sleep(POLL_S)
    raise TimeoutError(f"test {sid} still running after {limit_s:.0f} s")


def headline(s: dict[str, Any]) -> dict[str, Any]:
    sm = s.get("summary") or {}
    ev = sm.get("evaluation") or {}
    return {
        "session": s["id"],
        "status": s["status"],
        "scoreboard": sm.get("scoreboard"),
        "before": sm.get("before"),
        "after": sm.get("after"),
        "kept_fixes": sm.get("accepted_fixes"),
        "attacks": [a.get("title") for a in sm.get("attacks") or []],
        "fixes": {f.get("fix_id"): f.get("title") for f in sm.get("fixes") or []},
        "evaluation": ev.get("status"),
        "evaluation_reasons": ev.get("reasons"),
        "calls": (sm.get("cost") or {}).get("calls"),
    }


def main(path: str) -> None:
    case = json.loads(Path(path).read_text())
    out: dict[str, Any] = {"case": case["title"], "started": time.strftime("%Y-%m-%d %H:%M")}
    row = next((c for c in call("GET", "/real_cases") if c["title"] == case["title"]), None)
    if row is not None and os.environ.get("FRESH") == "1":
        if row.get("project_id"):
            call("DELETE", f"/projects/{row['project_id']}")
        call("DELETE", f"/real_cases/{row['id']}")
        row = None
    if row is None:
        row = call("POST", "/real_cases", case)
        say(f"case written: {row['id']}")
    say("opening it: the designer builds the venue, then the red team tests it")
    opened = call("POST", f"/real_cases/{row['id']}/open", timeout=1800)
    pid, sid = opened["project_id"], opened.get("session_id")
    project = call("GET", f"/projects/{pid}")
    venue = project["version"]["venue"]
    gen = venue.get("extensions", {}).get("generated", {})
    out["project"] = pid
    out["design_rounds"] = gen.get("design_rounds")
    out["site"] = gen.get("site")
    out["venue"] = {
        "floors": len(venue["floors"]),
        "stair_flights": len(venue["stairs"]),
        "exits": sum(len(f["exits"]) for f in venue["floors"]),
        "people": sum(z["people"] for f in venue["floors"] for z in f["zones"]),
    }
    for r in out["design_rounds"] or []:
        say(
            f"design round {r['round']}{' (kept)' if r.get('kept') else ''}: {r['summary']}; "
            f"{len(r['fixes'])} to fix, critic {r['critic']}, estimate {r.get('evac_s')} s"
        )
    if not sid:
        say(f"no test started ({opened.get('status')}): {opened.get('problems')}")
        out["status"] = opened.get("status")
        return save(path, out)
    say(f"testing: session {sid}")
    first = wait_session(sid)
    out["first_test"] = headline(first)
    say(f"first test {first['status']}: {out['first_test']['scoreboard']}")
    say("Let the AI fix it")
    loop = call("POST", f"/sessions/{sid}/improve", {})
    while loop["status"] == "running":
        time.sleep(POLL_S)
        loop = call("GET", f"/sessions/{sid}/improve")
    out["improve"] = loop
    for it in loop["iterations"]:
        say(
            f"test on version {it['version']}: {it['breaks']} of {it['attacks']} attacks broke "
            f"it; kept {it['fix_titles'] or 'no fix'}"
        )
    say(f"loop {loop['status']}: {loop['detail']}")
    last = loop["iterations"][-1]["session_id"] if loop["iterations"] else sid
    out["final_test"] = headline(call("GET", f"/sessions/{last}"))
    save(path, out)


def save(path: str, out: dict[str, Any]) -> None:
    dest = Path(path).with_suffix(".run.json")
    dest.write_text(json.dumps(out, indent=1, default=str))
    say(f"wrote {dest}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1])
    except urllib.error.HTTPError as exc:
        sys.exit(f"{exc.code} {exc.read().decode()[:400]}")
