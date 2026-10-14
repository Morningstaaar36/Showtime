"""HTTP tests for the explainer route (/ask) and the one box "Ask or change anything" (N15).

FakeLLM scripts play the models; with no script an agent behaves like an unreachable model.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.tests.test_api import client as client


def _new(client: TestClient, template: str = "conference_hall_2f") -> str:
    r = client.post("/api/v1/projects", json={"template_id": template, "name": "Hall"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _script(client: TestClient) -> dict[str, Any]:
    llm = client.app.state.showtime.llm  # type: ignore[attr-defined]
    assert isinstance(llm, FakeLLM)
    return llm.script


def _stress_test(client: TestClient, pid: str) -> str:
    r = client.post("/api/v1/runs", json={"project_id": pid, "tier": 3, "seed": 1})
    assert r.status_code == 202, r.text
    rid = str(r.json()["id"])
    for _ in range(100):
        if client.get(f"/api/v1/runs/{rid}").json()["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert client.get(f"/api/v1/runs/{rid}").json()["status"] in ("ok", "partial")
    return rid


def test_ask_needs_a_run(client: TestClient) -> None:
    pid = _new(client)
    r = client.post("/api/v1/ask", json={"project_id": pid, "question": "why is it red?"})
    assert r.status_code == 409 and r.json()["code"] == "no_run"


def test_ask_answers_about_a_hotspot_from_the_run(client: TestClient) -> None:
    pid = _new(client)
    rid = _stress_test(client, pid)
    _script(client)["explainer"] = {"answer": "People queue for the two south doors."}
    r = client.post(
        "/api/v1/ask", json={"project_id": pid, "run_id": rid, "question": "why is it red?"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["answer"] == "People queue for the two south doors."
    assert out["numbers_checked"] is True and out["sources"] == []
    assert set(out["camera_target"]) == {"floor_id", "x", "y"}
    ctx = out["context"]
    assert set(ctx) == {
        "hotspot",
        "nearby_exits",
        "run",
        "scenario_events",
        "thresholds_people_per_m2",
    }
    assert ctx["run"]["kind"] == "simulation" and ctx["run"]["people"] == 1200


def test_ask_reports_an_unavailable_model_as_503(client: TestClient) -> None:
    pid = _new(client)
    rid = _stress_test(client, pid)
    r = client.post(
        "/api/v1/ask", json={"project_id": pid, "run_id": rid, "question": "why is it red?"}
    )
    assert r.status_code == 503 and r.json()["code"] == "llm_unavailable"
