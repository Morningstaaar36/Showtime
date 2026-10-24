"""Regression tests for the backend bug sweep (routes, sessions, runs, reports, copilot)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import LLMReplayMiss
from api.adapters.sandbox import FakeRunner
from api.agents.base import AgentUnavailable
from api.agents.red_team import is_script_attack, signature
from api.app.main import create_app
from api.db.models import RedTeamSession, Run
from api.db.session import db_session
from api.orchestrator.reports import build_bundle
from api.orchestrator.session import SessionConfigError, session_config
from api.tests.test_api import client  # noqa: F401 - shared fixture
from api.tests.test_redteam import state  # noqa: F401 - shared fixture


def _shape(body: dict[str, Any]) -> None:
    assert set(body) == {"code", "message", "hint", "details"}


def _project(c: TestClient, template: str = "conference_hall_2f") -> str:
    r = c.post("/api/v1/projects", json={"template_id": template, "name": "Test"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


# --- 1. the sweep route starts its runs on the event loop -------------------------------------


def test_sweep_route_starts_every_scenario(client: TestClient) -> None:  # noqa: F811
    pid = _project(client)
    r = client.post(f"/api/v1/projects/{pid}/sweep")
    assert r.status_code == 202, r.text
    items = r.json()["items"]
    assert items and all(i["run_id"] and not i.get("skipped") for i in items)
    for _ in range(200):
        statuses = {
            i["status"] for i in client.get(f"/api/v1/projects/{pid}/sweep").json()["items"]
        }
        if statuses <= {"ok", "partial"}:
            break
        time.sleep(0.05)
    assert statuses <= {"ok", "partial"}, statuses


# --- 2. an LLM error (e.g. a replay miss) never leaves a session running ----------------------


def _miss(_: Any) -> Any:
    raise LLMReplayMiss("no recorded response")


async def test_replay_miss_falls_back_and_the_session_finishes(state: Any) -> None:  # noqa: F811
    for agent in ("red_team", "blue_team", "judge"):
        state.llm.script[agent] = _miss
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(p.id, {"max_rounds": 1, "attacks_per_round": 3, "fix_targets": 1})
    live = state.sessions.live[row.id]
    await asyncio.wait_for(live.task, timeout=30)
    assert live.finished
    done = state.sessions.get(row.id)
    assert done.status == "finished"
    assert done.summary["attacks"], "rule-based attacks stand in for the model"
    assert not done.summary["stopped_reason"].startswith("error")
    assert done.summary["numbers_checked"] is False  # the judge fell back to the template


async def test_a_failing_finish_marks_the_session_failed(
    state: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("countdown exploded")

    monkeypatch.setattr(state.sessions, "_countdown", boom)
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(p.id, {"max_rounds": 1, "attacks_per_round": 2, "fix_targets": 1})
    live = state.sessions.live[row.id]
    await asyncio.wait_for(live.task, timeout=30)
    assert live.finished
    done = state.sessions.get(row.id)
    assert done.status == "failed" and "countdown exploded" in (done.error or "")
    assert done.finished_at is not None
    # a listener that joins now gets the stored events and the stream ends
    events = await asyncio.wait_for(_collect(state, row.id), timeout=5)
    assert events[-1].payload["status"] == "failed"


async def _collect(st: Any, sid: str) -> list[Any]:
    return [e async for e in st.sessions.stream(sid)]


# --- 3. attack ids stay unique across rounds --------------------------------------------------


async def test_attack_ids_are_unique_and_the_example_script_is_not_repeated(
    state: Any,  # noqa: F811
) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(
        p.id, {"max_rounds": 3, "attacks_per_round": 3, "fix_targets": 1, "agents": "hybrid"}
    )
    await asyncio.wait_for(state.sessions.live[row.id].task, timeout=60)
    attacks = state.sessions.get(row.id).summary["attacks"]
    ids = [a["attack_id"] for a in attacks]
    assert len(ids) == len(set(ids)), ids
    assert sorted(ids, key=lambda i: int(i[1:])) == [f"A{n}" for n in range(1, len(ids) + 1)]
    from api.models import Attack

    sigs = [signature([e.model_dump() for e in Attack.model_validate(a).events]) for a in attacks]
    assert len(sigs) == len(set(sigs)), "an attack was tested twice"
    assert sum(is_script_attack(Attack.model_validate(a)) for a in attacks) >= 1


# --- 4. session settings are validated and budgets capped -------------------------------------


def test_session_config_coerces_caps_and_ignores_unknown_keys(state: Any) -> None:  # noqa: F811
    s = state.settings
    cfg = session_config(
        s,
        {
            "max_rounds": "2",
            "max_runs": 10**6,
            "max_wall_s": 10**9,
            "max_tokens": s.session_max_tokens * 10,
            "density_danger_ppm2": 99,  # not a session setting
            "agents": "nonsense",
        },
    )
    assert cfg["max_rounds"] == 2
    assert cfg["max_runs"] == s.session_max_runs
    assert cfg["max_wall_s"] == s.session_max_wall_s
    assert cfg["max_tokens"] == s.session_max_tokens
    assert "density_danger_ppm2" not in cfg
    assert cfg["agents"] == "model"
    assert session_config(s, {"max_tokens": 10})["max_tokens"] == 10  # lowering is fine
    for bad in ({"max_tokens": "lots"}, {"max_rounds": 0}, {"seed": -1}, {"max_runs": 2.5}):
        with pytest.raises(SessionConfigError):
            session_config(s, bad)


def test_bad_session_config_is_a_422(client: TestClient) -> None:  # noqa: F811
    pid = _project(client)
    r = client.post("/api/v1/sessions", json={"project_id": pid, "config": {"max_tokens": "lots"}})
    assert r.status_code == 422, r.text
    _shape(r.json())
    assert r.json()["code"] == "invalid_config"
    assert "max_tokens" in r.json()["message"]
    assert client.get(f"/api/v1/projects/{pid}/sessions").json() == []


# --- 5. reports of imported projects find the shared runs -------------------------------------


async def test_report_of_an_imported_project_has_baseline_and_final(
    state: Any,  # noqa: F811
) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(p.id, {"max_rounds": 1, "attacks_per_round": 3, "fix_targets": 1})
    await asyncio.wait_for(state.sessions.live[row.id].task, timeout=60)
    original = build_bundle(state, p.id, row.id)
    assert original.baseline is not None
    copy = state.projects.import_zip(state.projects.export_zip(p.id))
    sid = state.sessions.list_sessions(copy.id)[0].id
    imported = build_bundle(state, copy.id, sid)
    assert imported.baseline is not None
    assert imported.baseline.run_id == original.baseline.run_id
    assert (imported.final is None) == (original.final is None)


# --- 6/10. work left behind by a restart ------------------------------------------------------


def test_startup_fails_stale_runs_and_stops_stale_sessions(state: Any) -> None:  # noqa: F811
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    with db_session() as db:
        db.add(Run(id="r_stale_queue", project_id=p.id, status="queued"))
        db.add(Run(id="r_stale_run", project_id=p.id, status="running"))
        db.add(Run(id="r_done", project_id=p.id, status="ok"))
        db.add(RedTeamSession(id="s_stale", project_id=p.id, status="running"))
        db.commit()
    app = create_app(state=state, settings=state.base_settings)
    with TestClient(app) as c:
        for rid in ("r_stale_queue", "r_stale_run"):
            run = c.get(f"/api/v1/runs/{rid}").json()
            assert run["status"] == "failed" and "restarted" in run["error"]
            assert run["finished_at"]
        assert c.get("/api/v1/runs/r_done").json()["status"] == "ok"
        assert c.get("/api/v1/sessions/s_stale").json()["status"] == "stopped"
        listed = c.get(f"/api/v1/projects/{p.id}/sessions").json()
        assert [s["status"] for s in listed] == ["stopped"]
        # a row still marked running that this server is not running: same answer everywhere
        with db_session() as db:
            db.add(RedTeamSession(id="s_orphan", project_id=p.id, status="running"))
            db.commit()
        listed = {s["id"]: s["status"] for s in c.get(f"/api/v1/projects/{p.id}/sessions").json()}
        assert listed["s_orphan"] == "stopped"
        assert c.get("/api/v1/sessions/s_orphan").json()["status"] == "stopped"


# --- 7. one caller's cancel keeps a run others still wait for ---------------------------------


def _slow_job(st: Any) -> Any:
    st.runs.runner = FakeRunner(st.settings.runs_dir, delay_s=0.3)
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    return st.runs.build_job(st.projects.venue(p.id), tier=2)


async def _started(st: Any, rid: str) -> None:
    for _ in range(100):
        if rid in st.runs.tasks and st.runs.waiters.get(rid, 0) + (rid in st.runs.detached):
            return
        await asyncio.sleep(0.01)


async def test_cancelled_waiter_keeps_a_shared_run(state: Any) -> None:  # noqa: F811
    job = _slow_job(state)
    rid = job.request.run_id
    a = asyncio.create_task(state.runs.run(job))
    b = asyncio.create_task(state.runs.run(job))
    await _started(state, rid)
    await asyncio.sleep(0.05)
    assert state.runs.waiters[rid] == 2
    a.cancel()
    res = await asyncio.wait_for(b, timeout=5)
    assert a.cancelled()
    assert res.status in ("ok", "partial")
    assert state.runs.get(rid).status in ("ok", "partial")
    # finished runs leave the in-flight maps; the result stays readable from the database
    await asyncio.sleep(0)
    assert rid not in state.runs.tasks and rid not in state.runs.waiters


async def test_last_waiter_cancelled_stops_the_run(state: Any) -> None:  # noqa: F811
    job = _slow_job(state)
    rid = job.request.run_id
    a = asyncio.create_task(state.runs.run(job))
    await _started(state, rid)
    await asyncio.sleep(0.05)
    a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await a
    assert state.runs.get(rid).status == "cancelled"  # stored before the wait ended
    assert rid not in state.runs.waiters


async def test_cancelled_waiter_keeps_a_run_followed_over_the_api(
    state: Any,  # noqa: F811
) -> None:
    job = _slow_job(state)
    rid = job.request.run_id
    state.runs.submit(job)  # e.g. POST /runs: the UI polls it
    a = asyncio.create_task(state.runs.run(job))
    await _started(state, rid)
    await asyncio.sleep(0.05)
    a.cancel()
    await asyncio.gather(a, return_exceptions=True)
    task = state.runs.tasks[rid]
    assert not task.done()
    assert (await task).status in ("ok", "partial")
    # the organizer's Cancel still stops a run for everyone
    job2 = state.runs.build_job(job.venue, tier=2, seed=7)
    rid2 = state.runs.submit(job2)
    waiter = asyncio.create_task(state.runs.run(job2))
    await _started(state, rid2)
    await asyncio.sleep(0.05)
    assert await state.runs.cancel(rid2)
    assert (await asyncio.wait_for(waiter, timeout=5)).status == "cancelled"


# --- 8. weather with a bad date is a 422 ------------------------------------------------------


def test_weather_with_a_bad_day_or_event_start_is_a_422(client: TestClient) -> None:  # noqa: F811
    pid = _project(client)
    r = client.get("/api/v1/weather", params={"project_id": pid, "day": "tomorrow"})
    assert r.status_code == 422, r.text
    _shape(r.json())
    assert r.json()["code"] == "invalid_day"
    st = client.app.state.showtime  # type: ignore[attr-defined]
    venue = st.projects.venue(pid)
    assert venue.location is not None
    bad = venue.model_copy(
        update={"location": venue.location.model_copy(update={"event_start": "soon"})}
    )
    st.projects.replace_venue(pid, bad, "bad event start")
    r = client.get("/api/v1/weather", params={"project_id": pid})
    assert r.status_code == 422, r.text
    _shape(r.json())
    assert r.json()["code"] == "invalid_event_start"


# --- 9. the copilot leaves no checkpoint thread behind ----------------------------------------


async def test_copilot_plan_drops_its_checkpoint_thread(state: Any) -> None:  # noqa: F811
    from api.orchestrator.copilot import plan_event
    from api.orchestrator.copilot_graph import GRAPH

    def threads() -> set[str]:
        return {k for k in GRAPH.checkpointer.storage if str(k).startswith("copilot-")}  # type: ignore[union-attr]

    before = threads()
    # no model script for the brief: the graph fails, and its thread is still dropped
    with pytest.raises(AgentUnavailable):
        _ = [s async for s in plan_event(state, "a concert in a gym for 400 people")]
    assert threads() == before
