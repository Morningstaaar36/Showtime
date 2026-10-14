"""Scenario scripts and checkpoint/resume in the real sim image (needs Docker).

Run with: cd api && SIM_IMAGE=showtime-sim:agent-a uv run pytest -q ../sim/tests
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from test_sim import IMAGE, room, run, two_floor

pytestmark = pytest.mark.slow

CLOSE_EAST_AT_20 = """
state = {"done": False}

def on_step(view, act):
    if not state["done"] and view.t >= 20:
        act.close_exit("e_east")
        act.note(f"east door jammed with {view.exits['e_east']['people_near']} people near it")
        state["done"] = True
"""


def script(code: str, every_s: float = 1.0, at_s: float = 0.0) -> dict[str, Any]:
    return {
        "type": "script",
        "title": "Test script",
        "code": code,
        "every_s": every_s,
        "at_s": at_s,
    }


def acts(res: dict[str, Any], action: str) -> list[dict[str, Any]]:
    log = res["extensions"]["event_log"]
    return [e for e in log if e.get("type") == "script" and e.get("action") == action]


def test_script_closing_an_exit_slows_the_evacuation() -> None:
    plain, _ = run(room(120, exits=2))
    res, _ = run(room(120, exits=2), [script(CLOSE_EAST_AT_20)])
    m = res["metrics"]
    assert res["status"] == "ok", res
    assert m["agents_evacuated"] == m["agents_total"] == 120
    assert m["evac_time_p95_s"] > plain["metrics"]["evac_time_p95_s"]
    closed = acts(res, "close_exit")
    assert len(closed) == 1 and closed[0]["exit_id"] == "e_east"
    assert 20 <= closed[0]["t_s"] < 21.5
    assert any(n.startswith("Scenario script closed e_east") for n in res["notes"])
    assert any("east door jammed" in n for n in res["notes"])


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("def on_step(view, act):\n    while True:\n        pass\n", "one step"),
        ("def on_step(view, act):\n    return 1 / 0\n", "ZeroDivisionError on line 2"),
        ("def on_step(view, act):\n    act.close_exit(view.exits['nope'])\n", "KeyError"),
    ],
)
def test_broken_script_is_stopped_and_run_finishes(code: str, reason: str) -> None:
    res, _ = run(room(40, exits=2), [script(code, every_s=0.5)])
    m = res["metrics"]
    assert res["status"] == "ok", res
    assert m["agents_evacuated"] == 40
    stopped = [n for n in res["notes"] if n.startswith("scenario script stopped:")]
    assert stopped and reason in stopped[0], res["notes"]
    assert len(acts(res, "stopped")) == 1


def test_script_with_socket_or_open_is_refused_inside_the_sandbox_too() -> None:
    """The API pre-check rejects these; if one slipped through, the sim's own check does."""
    code = "import socket\n\ndef on_step(view, act):\n    open('/work/x', 'w')\n"
    res, work = run(room(30, exits=2), [script(code)])
    assert res["status"] == "ok"
    assert res["metrics"]["agents_evacuated"] == 30
    assert any("failed the safety check" in n for n in res["notes"]), res["notes"]
    assert not (work / "x").exists()


def test_sandbox_has_no_network() -> None:
    """Defence in depth: even code that got past both checks runs with --network=none."""
    probe = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
        "    print('connected')\n"
        "except OSError as exc:\n"
        "    print('blocked', type(exc).__name__)\n"
    )
    out = subprocess.run(
        ["docker", "run", "--rm", "--network=none", IMAGE, "python", "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert out.stdout.startswith("blocked"), out


def test_unknown_ids_become_notes() -> None:
    code = (
        "def on_step(view, act):\n"
        "    act.close_exit('ghost')\n"
        "    act.add_people('nowhere', 5)\n"
        "    act.redirect('e_south', 'ghost', 0.5)\n"
    )
    res, _ = run(room(20, exits=2), [script(code, every_s=60)])
    assert res["status"] == "ok"
    assert res["metrics"]["agents_total"] == 20
    assert any("no exit called 'ghost'" in n for n in res["notes"])
    assert any("no zone called 'nowhere'" in n for n in res["notes"])
    assert not [n for n in res["notes"] if n.startswith("scenario script stopped")]


ADD_ONCE = """
state = {"added": False}

def on_step(view, act):
    if not state["added"] and view.t >= 5:
        act.add_people("z", 20)
        state["added"] = True
"""


def test_checkpoint_then_resume_accounts_for_everyone() -> None:
    venue = room(120, exits=1)
    events = [script(ADD_ONCE)]
    plain, _ = run(venue, events, seed=4)
    first, work = run(venue, events, seed=4, request={"checkpoint_at_s": 30.0})
    # writing a checkpoint does not change the run
    assert first["metrics"]["evac_time_p95_s"] == plain["metrics"]["evac_time_p95_s"]
    assert first["metrics"]["agents_total"] == plain["metrics"]["agents_total"] == 140
    assert first["metrics"]["extra"]["checkpoint_t_s"] == pytest.approx(30.0, abs=0.06)
    cp = json.loads((work / "checkpoint.json").read_text())
    inside = len(cp["agents"])
    assert inside > 0 and len(cp["exit_times"]) + inside == cp["next_gid"] - 1
    assert cp["scripts"][0]["state"] == {"state": {"added": True}}

    resumed, rwork = run(
        venue, events, seed=4, request={"resume": True}, checkpoint=work / "checkpoint.json"
    )
    m = resumed["metrics"]
    assert resumed["status"] == "ok", resumed
    # nobody added twice (the script's memory came back), nobody lost
    assert m["agents_total"] == 140
    assert m["agents_evacuated"] == 140
    assert m["extra"]["resumed_from_s"] == pytest.approx(30.0, abs=0.06)
    first_frame = json.loads((rwork / "traj_index.json").read_text())["times"][0]
    assert first_frame == pytest.approx(30.0, abs=0.06)
    assert any(n.startswith("Rewound to 30") for n in resumed["notes"])
    resume_log = [e for e in resumed["extensions"]["event_log"] if e["type"] == "resume"]
    assert resume_log and resume_log[0]["people"] == inside
    assert not acts(resumed, "add_people")[1:], "the script must not add people again"


def test_rewind_needs_a_single_floor() -> None:
    res, work = run(two_floor(20, 10), request={"checkpoint_at_s": 5.0})
    assert res["status"] == "ok"
    assert "rewind needs a single-floor venue" in res["notes"]
    assert not (work / "checkpoint.json").exists()
