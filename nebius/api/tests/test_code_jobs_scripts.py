"""User scripts (bring your own model): save, list, update, delete and run in a sandbox."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.sandbox import CodeResult
from api.app import routes_scripts
from api.app.routes_runs import RunIn
from api.tests.test_analyst import _new, _simulated_run, _state
from api.tests.test_api import client as client

ANALYSIS = "import showtime_data as sd\noutput = {'people': len(sd.load_trajectories())}\n"
SCENARIO = "def on_step(view, act):\n    if view.t > 60:\n        act.close_exit('E_S1')\n"


def _url(pid: str, rest: str = "") -> str:
    return f"/api/v1/projects/{pid}/scripts{rest}"


def _create(client: TestClient, pid: str, **kw: Any) -> dict[str, Any]:
    body = {"name": "Queue length", "kind": "analysis", "code": ANALYSIS, **kw}
    r = client.post(_url(pid), json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_scripts_crud(client: TestClient) -> None:
    pid = _new(client)
    assert client.get(_url(pid)).json() == {"scripts": [], "scenario_supported": False}
    a = _create(client, pid)
    assert a["author"] == "you" and a["problems"] == [] and a["last_run"] is None
    b = _create(client, pid, name="Close a door", kind="scenario", code=SCENARIO, every_s=2)
    assert b["problems"] == [] and b["every_s"] == 2
    listed = client.get(_url(pid)).json()["scripts"]
    assert {s["id"] for s in listed} == {a["id"], b["id"]}

    r = client.put(_url(pid, f"/{a['id']}"), json={**a, "code": "import os\n"})
    assert r.status_code == 200 and "importing 'os'" in r.json()["problems"][0]
    assert client.delete(_url(pid, f"/{b['id']}")).status_code == 204
    assert [s["id"] for s in client.get(_url(pid)).json()["scripts"]] == [a["id"]]
    assert client.delete(_url(pid, f"/{b['id']}")).status_code == 404
    assert client.get(_url("nope")).status_code == 404
    # scripts belong to their project
    assert client.get(_url(_new(client))).json()["scripts"] == []


def test_scenario_scripts_need_on_step(client: TestClient) -> None:
    pid = _new(client)
    s = _create(client, pid, kind="scenario", code="x = 1\n")
    assert s["problems"] == ["A scenario script needs a function on_step(view, act)."]
    s = _create(client, pid, kind="scenario", code="def on_step(view, act)\n")
    assert s["problems"][0].startswith("Syntax error")


def test_an_invalid_script_does_not_run(client: TestClient) -> None:
    pid = _new(client)
    s = _create(client, pid, code="open('/etc/passwd')\n")
    r = client.post(_url(pid, f"/{s['id']}/run"), json={})
    assert r.status_code == 422 and r.json()["code"] == "script_invalid"
    assert _state(client).runner.code_jobs == []


def test_an_analysis_script_runs_as_a_code_job(client: TestClient) -> None:
    pid = _new(client)
    s = _create(client, pid)
    r = client.post(_url(pid, f"/{s['id']}/run"), json={})
    assert r.status_code == 409 and r.json()["code"] == "no_run"

    rid = _simulated_run(client, pid)
    runner = _state(client).runner
    runner.code_results = [CodeResult("ok", {"people": 400}, "note", "", 0.8)]
    r = client.post(_url(pid, f"/{s['id']}/run"), json={"run_id": rid})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "analysis" and out["status"] == "ok" and out["output"] == {"people": 400}
    assert out["run_id"] == rid and out["sandbox"] == "fake" and out["runtime_s"] == 0.8
    job = runner.code_jobs[-1]
    assert job.kind == "user_script" and job.script == ANALYSIS and "result.json" in job.inputs
    saved = client.get(_url(pid)).json()["scripts"][0]
    assert saved["last_run"]["status"] == "ok" and saved["last_run"]["output"] == {"people": 400}


def test_timeouts_and_errors_are_kept_with_the_script(client: TestClient) -> None:
    pid = _new(client)
    _simulated_run(client, pid)
    s = _create(client, pid)
    runner = _state(client).runner
    runner.code_results = [CodeResult("timeout", stderr_tail="stopped after 30 s")]
    out = client.post(_url(pid, f"/{s['id']}/run"), json={}).json()
    assert out["status"] == "timeout"
    assert client.get(_url(pid)).json()["scripts"][0]["last_run"]["status"] == "timeout"


def test_scenario_scripts_wait_for_the_script_event(client: TestClient) -> None:
    pid = _new(client)
    s = _create(client, pid, kind="scenario", code=SCENARIO)
    r = client.post(_url(pid, f"/{s['id']}/run"), json={})
    assert r.status_code == 422 and r.json()["code"] == "scenario_unsupported"


def test_a_scenario_script_runs_as_a_quick_simulation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _new(client)
    s = _create(client, pid, name="Close a door", kind="scenario", code=SCENARIO, every_s=2)
    seen: list[RunIn] = []

    async def fake_start(body: RunIn, st: Any) -> dict[str, Any]:
        seen.append(body)
        return {"id": "r_script", "status": "queued"}

    monkeypatch.setattr(routes_scripts, "scenario_supported", lambda st: True)
    monkeypatch.setattr(routes_scripts, "start_run", fake_start)
    r = client.post(_url(pid, f"/{s['id']}/run"), json={"seed": 7})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "scenario" and out["run_id"] == "r_script"
    assert out["status"] == "started"
    body = seen[0]
    assert (body.tier, body.seed, body.label) == (2, 7, "Script: Close a door")
    event = body.events[0].model_dump()
    assert event == {
        "type": "script",
        "at_s": 0.0,
        "title": "Close a door",
        "code": SCENARIO,
        "every_s": 2.0,
    }
    saved = client.get(_url(pid)).json()["scripts"][0]
    assert saved["last_run"]["run_id"] == "r_script"
