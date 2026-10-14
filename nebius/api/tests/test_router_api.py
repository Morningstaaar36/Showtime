"""HTTP tests for the explainer route (/ask) and the one box "Ask or change anything" (N15).

FakeLLM scripts play the models; with no script an agent behaves like an unreachable model.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.app.routes_ask import question_run
from api.core.extensions import Registry
from api.models import Venue
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


# --- ask-anything ----------------------------------------------------------------------------

RESIZE = {
    "intent": "resize door_s1 to 3 m",
    "ops": [{"op": "resize", "target": "door_s1", "width_m": 3}],
    "questions": [],
}


def _ask(client: TestClient, pid: str, text: str, **extra: Any) -> Any:
    return client.post(f"/api/v1/projects/{pid}/ask-anything", json={"text": text, **extra})


def test_a_what_if_works_with_the_model_down(client: TestClient) -> None:
    pid = _new(client)
    r = _ask(client, pid, "what if it rains and twice as many people come?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["intent"], body["routed_by"]) == ("what_if", "keywords")
    res = body["result"]
    assert res["params"] == {
        "crowd_scale": 2.0,
        "crowd_scale_asked": 2.0,
        "capped": False,
        "weather": "rain",
        "speed_factor": 0.85,
        "closed_exits": [],
        "changed": True,
    }
    assert (res["people"], res["before"]["people"]) == (2400, 1200)
    assert res["basis"] == res["before"]["basis"] == "Instant estimate (formula)"
    assert res["metrics"]["evac_time_p95_s"] > res["before"]["metrics"]["evac_time_p95_s"]
    # the numbers are the what-if route's own (computed in code, never by a model)
    direct = client.post(
        f"/api/v1/projects/{pid}/whatif", json={"people_scale": 2, "speed_factor": 0.85}
    ).json()

    def measured(m: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in m.items() if k != "extra"}  # extra holds the solver's timing

    assert measured(res["metrics"]) == measured(direct["metrics"])
    assert res["score"]["score"] == direct["score"]["score"]


def test_the_crowd_scale_is_clamped(client: TestClient) -> None:
    pid = _new(client)
    _script(client)["router"] = [
        {"intent": "what_if", "crowd_scale": 10},
        {"intent": "what_if", "crowd_scale": 0.1},
    ]
    big = _ask(client, pid, "what if ten times as many people come?").json()["result"]
    assert big["params"]["crowd_scale"] == 3.0 and big["params"]["capped"] is True
    assert big["params"]["crowd_scale_asked"] == 10 and big["people"] == 3600
    small = _ask(client, pid, "what if hardly anyone comes?").json()["result"]
    assert small["params"]["crowd_scale"] == 0.25 and small["people"] == 300


def test_unknown_exit_names_are_rejected_with_the_valid_names(client: TestClient) -> None:
    pid = _new(client)
    _script(client)["router"] = {
        "intent": "what_if",
        "closed_exits": ["South door 1", "the VIP gate"],
    }
    r = _ask(client, pid, "what if South door 1 and the VIP gate are closed?")
    assert r.status_code == 422, r.text
    err = r.json()
    assert err["code"] == "unknown_exit" and "“the VIP gate”" in err["message"]
    assert err["hint"] == "Exits here: South door 1, South door 2."
    assert err["details"] == {
        "unknown": ["the VIP gate"],
        "valid": ["South door 1", "South door 2"],
        "intent": "what_if",
        "routed_by": "model",
    }
    del _script(client)["router"]  # the keyword fallback checks names the same way
    kw = _ask(client, pid, "close the VIP gate").json()
    assert kw["code"] == "unknown_exit" and kw["details"]["unknown"] == ["VIP gate"]
    assert kw["details"]["routed_by"] == "keywords"


def test_named_exits_are_closed_in_the_what_if(client: TestClient) -> None:
    pid = _new(client)
    _script(client)["router"] = {"intent": "what_if", "closed_exits": ["door 1"]}
    res = _ask(client, pid, "what if door 1 is closed?").json()["result"]
    assert res["params"]["closed_exits"] == [{"id": "door_s1", "name": "South door 1"}]
    assert res["capacity"]["by_egress"] < res["before"]["capacity"]["by_egress"]
    assert res["metrics"]["evac_time_p95_s"] > res["before"]["metrics"]["evac_time_p95_s"]


def test_an_edit_is_only_proposed_until_the_organizer_applies_it(client: TestClient) -> None:
    # T-N15-3: the venue agent runs with apply=false; only the confirm call saves a version
    pid = _new(client)
    before = client.get(f"/api/v1/projects/{pid}").json()
    _script(client).update(router={"intent": "edit"}, venue=RESIZE)
    r = _ask(client, pid, "make South door 1 3 m wide")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["intent"], body["routed_by"]) == ("edit", "model")
    out = body["result"]
    assert out["status"] == "proposed" and out["version"] is None
    assert out["patch"]["ops"][0]["target"] == "door_s1"
    after = client.get(f"/api/v1/projects/{pid}").json()
    assert after["current_version"] == before["current_version"] == 1
    assert after["version"]["venue"] == before["version"]["venue"]
    assert len(client.get(f"/api/v1/projects/{pid}/versions").json()) == 1
    ok = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={"patch": out["patch"], "message": "AI change", "expected_version": 1},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["version"]["version"] == 2


def test_an_edit_needs_the_model_and_says_how_it_was_understood(client: TestClient) -> None:
    pid = _new(client)
    r = _ask(client, pid, "make South door 1 3 m wide")
    assert r.status_code == 503
    err = r.json()
    assert err["code"] == "llm_unavailable"
    assert err["details"] == {"intent": "edit", "routed_by": "keywords"}


def test_navigation_and_help(client: TestClient) -> None:
    from api.agents.router import keyword_intent

    pid = _new(client)
    nav = _ask(client, pid, "download the report").json()
    assert nav == {"intent": "navigate", "routed_by": "keywords", "result": {"target": "report"}}
    _script(client)["router"] = {"intent": "navigate", "target": "expert view"}
    assert _ask(client, pid, "studio please").json()["result"] == {"target": "expert"}
    _script(client)["router"] = {"intent": "other"}
    out = _ask(client, pid, "hello", context="plan").json()
    assert (out["intent"], out["routed_by"]) == ("other", "model")
    examples = out["result"]["examples"]
    assert examples == [
        "why is it crowded near the stage?",
        "what if South door 2 is closed and it rains?",
        "make South door 1 3 m wide",
    ]
    # each example still lands where it should when the model is down
    assert [keyword_intent(e) for e in examples] == ["question", "what_if", "edit"]


def test_a_question_before_any_test_uses_the_instant_estimate(client: TestClient) -> None:
    pid = _new(client)
    answer = {"answer": "Most people leave by the two south doors."}
    _script(client).update(router={"intent": "question"}, explainer=answer)
    res = _ask(client, pid, "which exit is the busiest?").json()["result"]
    assert res["answer"] == answer["answer"] and res["numbers_checked"] is True
    assert res["run_id"] is None and res["basis"] == "Instant estimate (formula)"
    assert res["context"]["run"]["kind"] == "instant estimate"
    assert [e["exit"] for e in res["context"]["exits"]] == ["South door 1", "South door 2"]


def test_question_answers_quote_only_computed_numbers(client: TestClient) -> None:
    pid = _new(client)
    made_up = {"answer": "Everyone is out after 9999 seconds."}
    _script(client).update(router={"intent": "question"}, explainer=[made_up, made_up])
    res = _ask(client, pid, "how long does it take?").json()["result"]
    assert res["numbers_checked"] is False and "9999" not in res["answer"]


def test_a_question_uses_the_latest_test_of_this_venue(client: TestClient) -> None:
    pid = _new(client)
    rid = _stress_test(client, pid)
    answer = {"answer": "The south doors carry everyone."}
    _script(client).update(router={"intent": "question"}, explainer=answer)
    res = _ask(client, pid, "which exit is the busiest?").json()["result"]
    assert res["run_id"] == rid and res["basis"] == "Preview only (no simulation)"
    assert res["context"]["run"]["kind"] == "simulation"
    # after an edit that test describes an older venue: back to the instant estimate
    edit = {"ops": [{"op": "resize", "target": "door_s1", "width_m": 3}]}
    assert client.post(f"/api/v1/projects/{pid}/patch", json={"patch": edit}).status_code == 200
    assert _ask(client, pid, "which exit is the busiest?").json()["result"]["run_id"] is None


def test_bad_requests_are_designed_errors(client: TestClient) -> None:
    pid = _new(client)
    assert _ask(client, pid, "x").status_code == 422
    assert _ask(client, pid, "what if it rains?", context="home").status_code == 422
    assert _ask(client, "p_missing", "what if it rains?").status_code == 404


def _run(rid: str, **kw: Any) -> SimpleNamespace:
    base = {
        "id": rid,
        "result": {"run_id": rid},
        "status": "ok",
        "attack_id": None,
        "fix_id": None,
        "request": {},
        "venue_version": 1,
    }
    return SimpleNamespace(**(base | kw))


def test_questions_about_a_tested_plan_use_its_session_runs(
    hall: Venue, registry: Registry
) -> None:
    runs = {
        r.id: r
        for r in [
            _run("final"),
            _run("base"),
            _run("broken", status="failed"),
            _run("plain"),
            _run("attack", attack_id="a1"),
        ]
    }
    sessions = {
        "s1": SimpleNamespace(project_id="p1", summary={"final_run_id": "final"}),
        "s2": SimpleNamespace(
            project_id="p1", summary={"final_run_id": "broken", "baseline_run_id": "base"}
        ),
        "elsewhere": SimpleNamespace(project_id="p2", summary={"final_run_id": "final"}),
    }
    st: Any = SimpleNamespace(
        sessions=SimpleNamespace(get=sessions.get),
        runs=SimpleNamespace(
            get=runs.get, list=lambda pid, limit=50: [runs["attack"], runs["plain"]]
        ),
        registry=registry,
    )

    def pick(session_id: str | None, version: int = 1) -> str | None:
        row = question_run(st, "p1", session_id, hall, version)
        return row.id if row is not None else None

    assert pick("s1") == "final"
    assert pick("s2") == "base"  # the final run failed
    assert pick("elsewhere") == "plain"  # another project's session is ignored
    assert pick(None) == "plain"  # an attack run is not a plain test of the venue
    assert pick(None, version=2) is None  # nothing tested at the current version
