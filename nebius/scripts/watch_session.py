"""Follow a red-team session's SSE stream in the terminal: python scripts/watch_session.py <id>."""

import json
import sys
import urllib.request

sid = sys.argv[1]
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
with urllib.request.urlopen(f"{base}/api/v1/sessions/{sid}/events", timeout=1800) as resp:
    for raw in resp:
        line = raw.decode().strip()
        if not line.startswith("data:"):
            continue
        d = json.loads(line[5:])
        if not d:
            print("END", flush=True)
            break
        t, p = d["type"], d["payload"]
        if t == "status":
            print(f"[{p['phase']}] {p['message']}", flush=True)
        elif t == "agent_call":
            print(
                f"  agent {p['agent']}: ok={p['ok']} {p['tokens_in']}+{p['tokens_out']} tok "
                f"{p['ms']:.0f} ms :: {p['summary'][:150]}",
                flush=True,
            )
        elif t == "attack_card":
            a = p["attack"]
            print(
                f"  ATTACK {a['attack_id']}: {a['title']} <- {a['inspired_by']['incident']} "
                f"({a['inspired_by']['year']}) {[e['type'] for e in a['events']]}",
                flush=True,
            )
        elif t == "fix_card":
            f = p["fix"]
            print(
                f"  FIX {f['fix_id']}: {f['title']} ops={[o['op'] for o in f['patch']['ops']]} "
                f"measures={[e['type'] for e in f['operational']]}",
                flush=True,
            )
        elif t == "run_finished":
            m = p["metrics"]
            print(
                f"  run t{p['tier']} {p['status']} break={p['is_break']} kept={p.get('accepted')} "
                f"p95={m.get('evac_time_p95_s')} peak={m.get('peak_density_ppm2')} "
                f"danger_s={m.get('time_above_danger_s')} {p['break_reasons'][:2]}",
                flush=True,
            )
        elif t == "score":
            print(f"  SCORE {p['scoreboard']} fixes kept={p['fixes_accepted']}", flush=True)
        elif t == "log":
            print(f"  log {p['level']}: {p['message'][:160]}", flush=True)
        elif t == "countdown":
            c = p["countdown"]
            print(
                f"  COUNTDOWN {c['status']} hazard={c.get('t_hazard_s')} latest={c.get('t_latest_s')}",
                flush=True,
            )
