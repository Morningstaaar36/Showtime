"""Autopilot (N13): a sentence or a project taken to a tested plan, never applied on its own.

FakeLLM (scripted agents) and FakeRunner (scaled instant estimates): no GPU, no Docker.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from api.adapters.llm import FakeLLM, LLMError
from api.adapters.sandbox import FakeRunner
from api.app.main import create_app
from api.app.state import build_state
from api.core.session_modes import session_modes
from api.core.settings import Settings, get_settings
from api.db import session as dbs
from api.db.models import Run
from api.db.session import db_session
from api.models.autopilot import STEP_ORDER, AutopilotRequest, AutopilotRun
from api.orchestrator import autopilot as ap
from api.orchestrator import sweep
from api.orchestrator.copilot_graph import OUTAGE_NOTE
from api.orchestrator.reports import build_bundle
from api.orchestrator.session import SessionManager
from api.tests.http import api_client
from api.tests.test_redteam import BLUE, red_reply

SENTENCE = "A concert in a 30 by 20 m gym for 400 people, 3 hours, stage on the north wall"
BRIEF = {"title": "Gym night", "kind": "concert", "place": None, "setting": "indoor",
         "attendees": 400, "start": None, "duration_h": 3, "alcohol": False,
         "audience": "standing", "stage": True, "layout": "A gym 30 by 20 m"}  # fmt: skip
SPEC = {"name": "Gym", "mode": "indoor", "width_m": 30, "depth_m": 20,
        "stage": {"wall": "north", "width_m": 10, "depth_m": 4},
        "exits": [{"wall": "south", "width_m": 2, "position": 0.3},
                  {"wall": "south", "width_m": 2, "position": 0.7}],
        "zones": [{"label": "Crowd", "people": 400, "region": "whole"}]}  # fmt: skip


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite:///{tmp_path / 'autopilot.sqlite'}",
        runs_dir=tmp_path / "runs",
        cache_dir=tmp_path / "cache",
        llm_provider="fake",
        sandbox_provider="fake",
        offline=True,
        target_evac_indoor_s=120,
    )


def _script() -> dict[str, Any]:
    return {
        "brief": BRIEF,
        "designer": SPEC,
        "red_team": red_reply,
        "blue_team": BLUE,
        "judge": {"summary": "The plan was tested.", "recommendations": []},
    }


def _isolate(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_URL", f"sqlite:///{tmp_path / 'autopilot.sqlite'}")
    get_settings.cache_clear()
    monkeypatch.setattr("api.core.settings.get_settings", lambda: settings)
    monkeypatch.setattr("api.db.session.get_settings", lambda: settings)
    monkeypatch.setattr("api.orchestrator.demos.DEMO_DIR", tmp_path / "no-demos")
    dbs.get_engine.cache_clear()


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    settings = _settings(tmp_path)
    _isolate(settings, tmp_path, monkeypatch)
    st = build_state(
        settings, llm=FakeLLM(_script(), settings), runner=FakeRunner(settings.runs_dir)
    )
    st.sessions = SessionManager(st)
    yield st
    get_settings.cache_clear()
    dbs.get_engine.cache_clear()


async def _plan(st: Any, **request: Any) -> AutopilotRun:
    mgr = ap.manager_for(st)
    run = mgr.start(AutopilotRequest(**request))
    task = mgr.live[run.id].task
    assert task is not None
    await task
    out = mgr.get(run.id)
    assert out is not None
    return out


def _steps(run: AutopilotRun) -> dict[str, Any]:
    return {s.key: s for s in run.steps}


async def test_quick_autopilot_from_a_sentence_delivers_a_tested_plan(state: Any) -> None:
    run = await _plan(state, text=SENTENCE)
    assert run.status == "finished", (run.error, run.steps)
    assert run.project_id and run.session_id and run.project_name == "Gym night"
    assert [s.key for s in run.steps] == list(STEP_ORDER)
    steps = _steps(run)
    for key in ("understand", "venue", "capacity", "simulate", "attack", "deliver"):
        assert steps[key].status == "done", key
        assert steps[key].started_at and steps[key].finished_at
    assert all(s.status in ("done", "skipped") for s in run.steps)
    assert "Safe capacity" in (steps["capacity"].detail or "")

    session = state.sessions.get(run.session_id)
    assert session.status == "finished"
    quick = session_modes().autopilot["quick"]
    assert {k: session.config[k] for k in quick} == quick  # the quick preset
    summary = session.summary
    assert summary["judge_text"] and summary["attacks"]
    baseline = summary["baseline_run_id"]
    assert any(r.id == baseline and r.tier == 3 for r in state.runs.list(run.project_id))

    assert run.report_url == f"/api/v1/sessions/{run.session_id}/report"
    bundle = build_bundle(state, run.project_id, run.session_id)
    html = state.registry.get("Exporter", "export_html_report").render(bundle).decode()
    assert "Planning aid, not a safety certification" in html
    # nothing applied: the project keeps the one version Autopilot created
    assert [v.version for v in state.projects.versions(run.project_id)] == [1]
    assert run.headline and run.headline.startswith("Tested ")
    assert not run.ai_outage and run.partial_reason is None

    cost = run.cost
    assert cost is not None
    assert cost.intake_tokens == 300  # brief + designer, 150 tokens each on FakeLLM
    assert cost.red_team_tokens == session.tokens > 0
    assert cost.tokens_total == cost.intake_tokens + cost.red_team_tokens
    assert cost.llm_calls >= 3 and cost.simulations >= 2


async def test_project_input_skips_reading_and_building(state: Any) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    run = await _plan(state, project_id=p.id)
    assert run.status == "finished", (run.error, run.steps)
    steps = _steps(run)
    for key in ("understand", "venue", "capacity"):
        assert steps[key].status == "skipped" and steps[key].detail == ap.OWN_VENUE
        assert steps[key].started_at is None
    assert steps["simulate"].status == "done" and steps["attack"].status == "done"
    assert run.project_id == p.id and run.project_name == "Hall"
    assert [x.id for x in state.projects.list_projects()] == [p.id]  # no new project
    assert not {a for a, _ in state.llm.calls} & {"brief", "designer"}
    assert [v.version for v in state.projects.versions(p.id)] == [1]
    assert ap.manager_for(state).latest_for_project(p.id).id == run.id  # type: ignore[union-attr]


async def test_llm_outage_still_delivers_and_says_so(state: Any) -> None:
    def down(_: Any) -> Any:
        raise LLMError("connection refused")

    for agent in ("red_team", "blue_team", "judge"):
        state.llm.script[agent] = down
    p = state.projects.create("School", template_id="school_wing")
    run = await _plan(state, project_id=p.id)
    assert run.status == "finished", (run.error, run.steps)
    assert run.ai_outage and OUTAGE_NOTE in run.notes
    assert run.report_url and run.session_id
    attacks = state.sessions.get(run.session_id).summary["attacks"]
    assert attacks and all(a["extensions"].get("generated_by") == "rules" for a in attacks)


async def test_request_without_the_ai_fails_with_a_way_forward(state: Any) -> None:
    state.llm.script.clear()  # every agent unreachable: nobody can read the sentence
    run = await _plan(state, text=SENTENCE)
    assert run.status == "failed" and run.error == ap.LLM_DOWN
    steps = _steps(run)
    assert steps["understand"].status == "failed"
    assert all(steps[k].status == "skipped" for k in STEP_ORDER[1:])
    assert run.project_id is None and run.session_id is None


async def test_budget_ends_with_a_partial_plan(state: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    modes = session_modes()
    monkeypatch.setitem(modes.autopilot, "quick", {**modes.autopilot["quick"], "max_tokens": 10})
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    run = await _plan(state, project_id=p.id)
    assert run.status == "finished" and run.partial_reason == "budget"
    assert run.report_url and any("budget" in n for n in run.notes)


async def test_stop_during_the_red_team_leaves_no_simulation_running(state: Any) -> None:
    state.runs.runner.delay_s = 0.2
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    mgr = ap.manager_for(state)
    run = mgr.start(AutopilotRequest(project_id=p.id))
    live = mgr.live[run.id]
    task = live.task
    assert task is not None
    for _ in range(300):
        if live.session_id:
            break
        await asyncio.sleep(0.01)
    assert live.session_id and mgr.stop(run.id)
    await task
    done = mgr.get(run.id)
    assert done is not None
    assert done.status == "stopped" and done.partial_reason == "stopped"
    assert state.sessions.get(done.session_id).status == "stopped"
    assert all(t.done() for t in state.runs.tasks.values())
    with db_session() as db:
        statuses = {r.status for r in db.exec(select(Run).where(Run.project_id == p.id))}
    assert not statuses & {"queued", "running"}
    assert [v.version for v in state.projects.versions(p.id)] == [1]
    assert not mgr.stop(run.id)  # nothing left to stop


async def test_stop_while_reading_the_request_cancels_the_work(state: Any) -> None:
    gate, chat = asyncio.Event(), state.llm.chat

    async def slow(role: str, messages: Any, schema: Any = None, **kw: Any) -> Any:
        if kw.get("agent") == "brief":
            await gate.wait()
        return await chat(role, messages, schema, **kw)

    state.llm.chat = slow
    mgr = ap.manager_for(state)
    run = mgr.start(AutopilotRequest(text=SENTENCE))
    live = mgr.live[run.id]
    task = live.task
    assert task is not None
    for _ in range(300):
        if live.step("understand").status == "running":
            break
        await asyncio.sleep(0.01)
    assert mgr.stop(run.id)
    await task
    done = mgr.get(run.id)
    assert done is not None and done.status == "stopped"
    assert done.project_id is None and done.session_id is None
    assert all(s.status == "skipped" for s in done.steps)
    assert _steps(done)["understand"].detail == ap.STOPPED_DURING


async def test_events_replay_after_a_sequence_number(state: Any) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    mgr = ap.manager_for(state)
    run = mgr.start(AutopilotRequest(project_id=p.id))
    live_events = [e async for e in mgr.stream(run.id)]  # follows the run to its end
    assert [e.seq for e in live_events] == list(range(1, len(live_events) + 1))
    assert live_events[-1].type == "done" and live_events[-1].payload["status"] == "finished"
    assert {"step", "session", "cost", "done"} <= {e.type for e in live_events}
    stored = [e async for e in mgr.stream(run.id)]
    assert [e.model_dump() for e in stored] == [e.model_dump() for e in live_events]
    later = [e async for e in mgr.stream(run.id, after=5)]
    assert [e.seq for e in later] == [e.seq for e in live_events[5:]]


async def test_thorough_adds_the_sweep_and_a_larger_red_team(state: Any) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    run = await _plan(state, project_id=p.id, depth="thorough")
    assert run.status == "finished", (run.error, run.steps)
    config = state.sessions.get(run.session_id).config
    thorough = session_modes().autopilot["thorough"]
    assert {k: config[k] for k in thorough} == thorough
    assert sweep.sweep_status(state, p.id) is not None
    q = state.projects.create("Hall again", template_id="conference_hall_2f")
    await _plan(state, project_id=q.id)
    assert sweep.sweep_status(state, q.id) is None  # quick never runs the sweep


# --- HTTP ------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = _settings(tmp_path)
    _isolate(settings, tmp_path, monkeypatch)
    st = build_state(
        settings, llm=FakeLLM(_script(), settings), runner=FakeRunner(settings.runs_dir)
    )
    with api_client(create_app(state=st, settings=settings)) as c:
        yield c
    get_settings.cache_clear()
    dbs.get_engine.cache_clear()


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    for _ in range(600):
        body: dict[str, Any] = client.get(f"/api/v1/autopilot/{run_id}").json()
        if body["status"] not in ("queued", "running"):
            return body
        time.sleep(0.05)
    raise AssertionError("Autopilot did not finish")


def test_autopilot_over_http(client: TestClient) -> None:
    r = client.post("/api/v1/autopilot", json={"text": SENTENCE, "depth": "quick"})
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["id"].startswith("ap_") and len(run["steps"]) == 8
    done = _wait(client, run["id"])
    assert done["status"] == "finished", done
    report = client.get(done["report_url"])
    assert report.status_code == 200 and "Planning aid" in report.text
    latest = client.get(f"/api/v1/projects/{done['project_id']}/autopilot")
    assert latest.status_code == 200 and latest.json()["id"] == run["id"]
    versions = client.get(f"/api/v1/projects/{done['project_id']}/versions").json()
    assert len(versions) == 1  # tested, not applied
    with client.stream("GET", f"/api/v1/autopilot/{run['id']}/events?after=3") as s:
        text = "".join(s.iter_text())
    ids = [int(x) for x in re.findall(r"^id: (\d+)", text, re.M)]
    assert ids and ids[0] == 4 and ids == sorted(set(ids))
    assert text.rstrip().endswith("data: {}") and "event: end" in text
    stopped = client.post(f"/api/v1/autopilot/{run['id']}/stop")
    assert stopped.status_code == 200 and stopped.json()["status"] == "finished"


def test_autopilot_http_errors(client: TestClient) -> None:
    assert client.post("/api/v1/autopilot", json={}).status_code == 422
    both = {"text": SENTENCE, "project_id": "p_x"}
    assert client.post("/api/v1/autopilot", json=both).status_code == 422
    assert client.post("/api/v1/autopilot", json={"project_id": "p_none"}).status_code == 404
    assert client.get("/api/v1/autopilot/ap_none").status_code == 404
    assert client.get("/api/v1/autopilot/ap_none/events").status_code == 404
    assert client.post("/api/v1/autopilot/ap_none/stop").status_code == 404
    assert client.get("/api/v1/projects/p_none/autopilot").status_code == 404
    pid = client.post("/api/v1/projects", json={"template_id": "school_wing", "name": "S"}).json()
    r = client.get(f"/api/v1/projects/{pid['id']}/autopilot")
    assert r.status_code == 200 and r.json() is None


def test_copilot_graph_shows_the_autopilot_flow(client: TestClient) -> None:
    g = client.get("/api/v1/copilot/graph").json()
    assert {"red_team", "deliver"} <= set(g["nodes"])
    edges = {(e["source"], e["target"]) for e in g["edges"]}
    assert {
        ("__start__", "understand"),
        ("__start__", "simulate"),
        ("simulate", "sweep"),
        ("simulate", "red_team"),
        ("sweep", "red_team"),
        ("sweep", "review"),
        ("red_team", "deliver"),
        ("deliver", "__end__"),
    } <= edges
    assert [s["key"] for s in g["steps"]] == list(STEP_ORDER)
    assert [s["label"] for s in g["steps"]][:2] == [
        "Understanding your event",
        "Building the venue",
    ]
    assert next(s for s in g["steps"] if s["key"] == "attack")["phases"] == [
        "red_team",
        "screening",
        "simulating",
    ]
