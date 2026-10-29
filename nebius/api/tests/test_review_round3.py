"""Code and security review (docs/REVIEW.md section 5): imports, the run cache, sessions, the
daily model budget, cross-site writes and clean-up. Fake LLM and fake sandbox: no Docker."""

from __future__ import annotations

import asyncio
import io
import json
import stat
import sys
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import DailyBudget, DailyLimitReached, LLMClient, LLMError
from api.adapters.sandbox import DockerRunner, FakeRunner, sim_version
from api.app.main import create_app
from api.app.routes_projects import delete_project
from api.core.settings import Settings
from api.core.templates import get_template
from api.db.models import Run, VenueVersion
from api.db.session import db_session
from api.models import RunResult, Usage
from api.orchestrator.projects import NotFound
from api.orchestrator.session import LiveSession, TooManySessions
from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings
from api.tests.http import api_client
from api.tests.test_api import client  # noqa: F401 - shared fixture
from api.tests.test_docker_runner_streams import _job, _runner, fake_docker  # noqa: F401
from api.tests.test_redteam import state  # noqa: F401 - shared fixture


async def _until(ok: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not ok():
        assert time.monotonic() < deadline, "the condition never held"
        await asyncio.sleep(0.01)


def _zip(files: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, (bytes, str)) else json.dumps(data))
    return buf.getvalue()


def _export(versions: list[dict[str, Any]], **project: Any) -> bytes:
    return _zip(
        {
            "manifest.json": {"format": "showtime-project-v1"},
            "project.json": {"name": "Broken", **project},
            "versions.json": versions,
        }
    )


@pytest.fixture
def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """A test client (and its app state) with settings changed for one test."""
    base = use_test_settings(tmp_path, monkeypatch)

    def make(**changes: Any) -> tuple[TestClient, Any]:
        s = base.model_copy(update=changes)
        st = app_state(s, fake=True)
        return api_client(create_app(state=st, settings=s)), st

    yield make
    reset_engine()


# --- H1: a malformed export is a 422, and one broken project never breaks the list ------------


def test_malformed_versions_are_refused_before_anything_is_written(state: Any) -> None:  # noqa: F811
    venue = get_template("school_wing").model_dump(mode="json")
    bad = [
        _export([{"version": 1, "venue": venue}], current_version=7),
        _export([{"version": 1, "venue": venue}, {"version": 1, "venue": venue}]),
        _export([{"version": "one", "venue": venue}]),
        _export([{"version": 1}]),
        _export([{"version": True, "venue": venue}]),
        _export([{"version": 1, "venue": venue, "base_version": "x"}]),
        _export({"version": 1}),  # type: ignore[arg-type]
        _export([{"version": 1, "venue": {"floors": "none"}}]),
        _export([]),
    ]
    before = len(state.projects.list_projects())
    for data in bad:
        with pytest.raises(ValueError):
            state.projects.import_zip(data)
    assert len(state.projects.list_projects()) == before


def test_a_bad_import_is_a_422_and_a_broken_row_is_left_out(client: TestClient) -> None:  # noqa: F811
    venue = get_template("school_wing").model_dump(mode="json")
    data = _export([{"version": 1, "venue": venue}], current_version=3)
    r = client.post("/api/v1/projects/import", files={"file": ("p.showtime.zip", data)})
    assert r.status_code == 422 and r.json()["code"] == "bad_import", r.text
    ok = client.post("/api/v1/projects", json={"template_id": "school_wing", "name": "Ok"})
    gone = client.post("/api/v1/projects", json={"template_id": "school_wing", "name": "Gone"})
    with db_session() as db:  # a row an older import (or a bad disk) left unreadable
        for row in db.query(VenueVersion).filter_by(project_id=gone.json()["id"]):
            row.venue = {"floors": "none"}
            db.add(row)
        db.commit()
    r = client.get("/api/v1/projects")
    assert r.status_code == 200
    assert {p["id"] for p in r.json()} == {ok.json()["id"]}


# --- H2: the unpacked size and the number of entries are checked before reading ----------------


def test_a_zip_bomb_is_refused_from_its_declared_sizes(
    state: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    venue = get_template("school_wing").model_dump(mode="json")
    padded = [{"version": 1, "venue": venue, "message": " " * 2_000_000}]
    data = _export(padded)
    assert len(data) < 100_000  # compresses to almost nothing
    read = zipfile.ZipFile.read

    def no_read(*_: Any, **__: Any) -> bytes:
        raise AssertionError("an entry was read before the sizes were checked")

    monkeypatch.setattr(zipfile.ZipFile, "read", no_read)
    with pytest.raises(ValueError, match="unpacks to more than 1 MB"):
        state.projects.import_zip(data, max_unpacked_bytes=1_000_000)
    many = _zip({f"junk/{i}": "" for i in range(20)})
    with pytest.raises(ValueError, match="more than 10 entries"):
        state.projects.import_zip(many, max_entries=10)
    monkeypatch.setattr(zipfile.ZipFile, "read", read)
    assert state.projects.import_zip(data).current_version == 1  # under the default limit


def test_the_import_route_uses_the_limit_settings(make_client: Any) -> None:
    c, _ = make_client(import_max_unpacked_bytes=1_000_000)
    venue = get_template("school_wing").model_dump(mode="json")
    data = _export([{"version": 1, "venue": venue, "message": " " * 2_000_000}])
    with c:
        r = c.post("/api/v1/projects/import", files={"file": ("p.showtime.zip", data)})
    assert r.status_code == 422 and "unpacks to more than" in r.json()["message"]


# --- H3: the stream drains live events after its replay ---------------------------------------


async def test_events_of_a_session_ending_during_the_replay_still_arrive(state: Any) -> None:  # noqa: F811
    mgr = state.sessions
    live = LiveSession(id="s_drain", project_id="p", venue_version=1, config={})
    mgr.live[live.id] = live
    mgr.emit(live, "status", {"status": "running"})
    mgr.emit(live, "score", {"round": 1})
    stream = mgr.stream(live.id)
    first = await stream.__anext__()  # the replay of what was stored is under way
    # meanwhile the session sends its last events and ends (and leaves memory)
    mgr.emit(live, "status", {"status": "finished"})
    live.finished = True
    mgr.live.pop(live.id)
    rest = [e async for e in stream]
    assert [e.seq for e in [first, *rest]] == [1, 2, 3]
    assert rest[-1].payload == {"status": "finished"}


# --- M1: runs are keyed by the simulator; imported runs never stand in for a request ----------


def test_the_run_id_follows_the_simulator_code(state: Any, tmp_path: Path) -> None:  # noqa: F811
    venue = get_template("school_wing")
    assert state.runs.sim_version  # read from sim/ at start
    before = state.runs.build_job(venue, tier=2).request.run_id
    state.runs.sim_version = "a-fixed-simulator"
    assert state.runs.build_job(venue, tier=2).request.run_id != before
    sim = tmp_path / "sim"
    sim.mkdir()
    (sim / "run_sim.py").write_text("print(1)\n")
    v1 = sim_version(sim)
    (sim / "run_sim.py").write_text("print(2)\n")
    assert sim_version(sim) != v1


async def test_imported_runs_get_ids_of_their_own(state: Any, tmp_path: Path) -> None:  # noqa: F811
    p = state.projects.create("Hall", template_id="school_wing")
    job = state.runs.build_job(state.projects.venue(p.id), tier=2)
    rid = job.request.run_id
    await state.runs.run(job, project_id=p.id)
    src = state.settings.runs_dir / rid
    src.mkdir(parents=True, exist_ok=True)
    (src / "density.bin").write_bytes(b"\0" * 8)
    (src / "result.json").write_text(json.dumps({"run_id": rid, "path": f"runs/{rid}/x"}))
    data = state.projects.export_zip(p.id, artifacts_from=state.settings.runs_dir)
    state.projects.delete(p.id)  # the run's id is free again: an import must not take it
    target = tmp_path / "imported_runs"
    copy = state.projects.import_zip(data, runs_dir=target)
    assert state.runs.cached(rid) is None and state.runs.get(rid) is None
    with db_session() as db:
        runs = list(db.query(Run).filter_by(project_id=copy.id))
    assert len(runs) == 1 and runs[0].id != rid
    new = runs[0].id
    assert runs[0].request["run_id"] == new and runs[0].result["run_id"] == new
    assert sorted(x.name for x in target.iterdir()) == [new]
    assert json.loads((target / new / "result.json").read_text()) == {
        "run_id": new,
        "path": f"runs/{new}/x",
    }


async def test_a_cache_hit_needs_every_artifact_it_serves(state: Any, tmp_path: Path) -> None:  # noqa: F811
    p = state.projects.create("Hall", template_id="school_wing")
    job = state.runs.build_job(state.projects.venue(p.id), tier=2)
    rid = job.request.run_id
    await state.runs.run(job, project_id=p.id)
    traj, grid = tmp_path / "traj.bin", tmp_path / "density.bin"
    traj.write_bytes(b"t")
    with db_session() as db:
        row = db.get(Run, rid)
        res = RunResult.model_validate(row.result)
        res.artifacts.trajectory, res.artifacts.density_grid = str(traj), str(grid)
        row.result = res.model_dump(mode="json")
        db.add(row)
        db.commit()
    assert state.runs.cached(rid) is None  # the density grid is gone
    grid.write_bytes(b"d")
    assert state.runs.cached(rid) is not None


# --- M2: containers left by an earlier process, and the runner's own at shutdown ---------------

PS_DOCKER = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[0] == "ps":
    print("showtime-sim-r_old\\nshowtime-code-j_old\\nsomeone-elses")
"""


async def test_leftover_containers_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "docker"
    exe.write_text(PS_DOCKER.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    runner = _runner(tmp_path, exe)
    assert await runner.remove_leftovers() == 2
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert f"label={runner.owner_label}" in calls[0]  # only this API's containers
    assert calls[1] == ["rm", "--force", "showtime-sim-r_old", "showtime-code-j_old"]
    runner._docker = str(tmp_path / "no-docker")
    assert await runner.remove_leftovers() == 0  # without Docker: nothing to do, no error


def test_the_api_removes_leftovers_at_startup(make_client: Any) -> None:
    c, st = make_client()
    calls: list[str] = []

    async def leftovers() -> int:
        calls.append("startup")
        return 0

    st.runner.remove_leftovers = leftovers
    with c:
        assert calls == ["startup"]


async def test_close_kills_the_runners_containers(
    tmp_path: Path,
    fake_docker: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "hang")
    runner: DockerRunner = _runner(tmp_path, fake_docker)
    task = asyncio.create_task(runner.run(_job("r_close")))
    await _until(lambda: "showtime-sim-r_close" in runner.running)
    await _until(lambda: Path(str(tmp_path / "docker.log") + ".pid").exists())
    await runner.close()
    res = await asyncio.wait_for(task, timeout=10)
    assert res.status == "failed"  # stopped, not left running on its own
    log = (tmp_path / "docker.log").read_text().splitlines()
    assert ["kill", "showtime-sim-r_close"] in [json.loads(x) for x in log]
    assert not runner.running


# --- M3: bounded settings, concurrent sessions, the daily model budget -------------------------


def test_settings_from_the_page_have_upper_bounds(client: TestClient) -> None:  # noqa: F811
    for key, value in {
        "session_max_tokens": 10**9,
        "max_people": 10**6,
        "max_rounds": 100,
        "attacks_per_round": 50,
        "fixes_per_attack": 50,
        "tavily_max_calls": 10**4,
    }.items():
        r = client.put("/api/v1/settings", json={"values": {key: value}})
        assert r.status_code == 422, (key, r.text)
    assert client.put("/api/v1/settings", json={"values": {"max_rounds": 4}}).status_code == 200


def test_one_session_too_many_is_a_429(make_client: Any) -> None:
    c, st = make_client(max_concurrent_sessions=1)
    with c:
        pid = c.post("/api/v1/projects", json={"template_id": "school_wing"}).json()["id"]
        st.sessions.live["s_busy"] = LiveSession(
            id="s_busy", project_id="p_other", venue_version=1, config={}
        )
        r = c.post("/api/v1/sessions", json={"project_id": pid})
        assert r.status_code == 429, r.text
        assert r.json()["code"] == "too_many_sessions" and r.json()["hint"]
        del st.sessions.live["s_busy"]
        assert c.post("/api/v1/sessions", json={"project_id": pid}).status_code == 201


def test_the_daily_budget_counts_per_day() -> None:
    day = DailyBudget(max_tokens=200, max_usd=1.0)
    day.add(Usage(role="fast", model="m", prompt_tokens=150, completion_tokens=0))
    day.add(Usage(role="fast", model="m", prompt_tokens=500, cached=True))  # free: not counted
    day.check()
    day.add(Usage(role="fast", model="m", prompt_tokens=60))
    with pytest.raises(DailyLimitReached, match="200 tokens"):
        day.check()
    day.day = "2000-01-01"  # a new day starts from zero
    day.check()
    day.add(Usage(role="main", model="m", cost_usd=1.5))
    with pytest.raises(DailyLimitReached, match=r"\$1.00"):
        day.check()
    DailyBudget().add(Usage(role="fast", model="m", prompt_tokens=10**9))  # 0 means no limit


async def test_the_llm_client_refuses_calls_once_the_day_is_used() -> None:
    llm = LLMClient(Settings(_env_file=None, llm_provider="fake", daily_max_tokens=1000))
    msgs = [{"role": "user", "content": "hi"}]
    with pytest.raises(LLMError):  # under the limit: on to the (fake) provider
        await llm.chat("fast", msgs)
    llm._account(Usage(role="fast", model="m", prompt_tokens=1000), None)
    with pytest.raises(DailyLimitReached):
        await llm.chat("fast", msgs)


async def test_a_session_stops_gracefully_at_the_daily_limit(state: Any) -> None:  # noqa: F811
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    state.llm.daily = DailyBudget(max_tokens=1)  # the first answer uses it up
    row = state.sessions.start(p.id, {"max_rounds": 2, "attacks_per_round": 3, "fix_targets": 1})
    await state.sessions.live[row.id].task
    done = state.sessions.get(row.id)
    assert done.status == "finished"
    assert done.summary["stopped_reason"] == "budget: daily model limit"
    with pytest.raises(TooManySessions, match="tokens is used"):
        state.sessions.start(p.id)


# --- M4: trusted hosts, and a header on every change -------------------------------------------


def test_a_change_without_the_header_is_refused(client: TestClient) -> None:  # noqa: F811
    body = {"template_id": "school_wing", "name": "X"}
    r = client.post("/api/v1/projects", json=body, headers={"x-showtime": ""})
    assert r.status_code == 403 and r.json()["code"] == "missing_header", r.text
    plain = TestClient(client.app, base_url="http://localhost")  # a page on another site
    assert plain.post("/api/v1/projects", json=body).status_code == 403
    assert plain.delete("/api/v1/projects/p_x").status_code == 403
    assert plain.get("/api/v1/projects").status_code == 200  # reads need no header
    assert client.post("/api/v1/projects", json=body).status_code == 201
    pre = plain.options(
        "/api/v1/projects",
        headers={
            "origin": "http://localhost:5173",
            "access-control-request-method": "POST",
            "access-control-request-headers": "x-showtime,content-type",
        },
    )
    assert pre.status_code == 200 and "x-showtime" in pre.headers["access-control-allow-headers"]


def test_only_trusted_host_names_are_answered(make_client: Any) -> None:
    c, _ = make_client(web_origin="https://showtime.example.org", site_address="1.2.3.4.sslip.io")
    with c:
        for host in ("localhost", "127.0.0.1:8000", "api:8000", "showtime.example.org"):
            assert c.get("/api/v1/health", headers={"host": host}).status_code == 200, host
        assert c.get("/api/v1/health", headers={"host": "1.2.3.4.sslip.io"}).status_code == 200
        assert c.get("/api/v1/health", headers={"host": "rebind.attacker.test"}).status_code == 400
    c, _ = make_client(allowed_hosts="*")
    with c:
        assert c.get("/api/v1/health", headers={"host": "any.test"}).status_code == 200


def test_trusted_hosts_from_the_settings() -> None:
    s = Settings(_env_file=None, llm_provider="fake", site_address=":80")
    assert s.trusted_hosts == ["localhost", "127.0.0.1", "api"]  # ":80" names no host
    s = Settings(_env_file=None, llm_provider="fake", allowed_hosts="a.test, b.test")
    assert s.trusted_hosts == ["a.test", "b.test"]


# --- M5: a finished session leaves memory; its replay comes from the database ----------------


async def test_a_finished_session_is_freed_and_still_replays(state: Any) -> None:  # noqa: F811
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(p.id, {"max_rounds": 1, "attacks_per_round": 2, "fix_targets": 1})
    live = state.sessions.live[row.id]
    await live.task
    assert row.id not in state.sessions.live and live.finished
    replay = [e async for e in state.sessions.stream(row.id)]
    assert replay and replay[-1].payload.get("status") == "finished"
    assert [e.seq for e in replay] == list(range(1, len(replay) + 1))


# --- M6: slow work of async routes runs off the event loop -------------------------------------


def _off_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return True
    return False


def test_import_and_case_listing_run_off_the_event_loop(
    make_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, st = make_client()
    seen: list[bool] = []
    imp = next(i for i in st.registry.all("VenueImporter") if ".json" in i.file_extensions)

    def parse(data: bytes, filename: str) -> Any:
        seen.append(_off_loop())
        return get_template("school_wing")

    monkeypatch.setattr(imp, "import_bytes", parse)
    from api.app import routes_cases

    real = routes_cases.case_projects

    def case_projects(st: Any) -> dict[str, str]:
        seen.append(_off_loop())
        return real(st)

    monkeypatch.setattr(routes_cases, "case_projects", case_projects)
    with c:
        r = c.post("/api/v1/projects/import", files={"file": ("v.json", b"{}")})
        assert r.status_code == 201, r.text
        assert c.get("/api/v1/real_cases").status_code == 200
    assert seen == [True, True]


# --- lows: the notifier task is held; deleting a project stops its test and removes its files --


async def test_the_notify_task_is_held_until_it_ran(state: Any) -> None:  # noqa: F811
    live = LiveSession(id="s_held", project_id="p", venue_version=1, config={})
    state.sessions.emit(live, "status", {"status": "running"})
    assert len(state.sessions._notifiers) == 1  # referenced: it can't be collected mid-flight
    await _until(lambda: not state.sessions._notifiers)


async def test_deleting_a_project_stops_its_test_and_removes_its_runs(state: Any) -> None:  # noqa: F811
    runs_dir = state.settings.runs_dir
    state.runs.runner = FakeRunner(runs_dir, delay_s=30)
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(p.id, {"max_rounds": 1, "attacks_per_round": 2})
    live = state.sessions.live[row.id]
    await _until(lambda: bool(live.inflight))  # the baseline is simulating
    rid = live.branch_runs["baseline"]
    (runs_dir / rid).mkdir(parents=True, exist_ok=True)
    (runs_dir / rid / "traj.bin").write_bytes(b"t")
    other = state.projects.create("Other", template_id="school_wing")
    with db_session() as db:
        db.add(Run(id="r_other_project", project_id=other.id, status="ok"))
        db.commit()
    (runs_dir / "r_other_project").mkdir(parents=True)
    await asyncio.wait_for(delete_project(p.id, st=state), timeout=10)
    assert live.task is not None and live.task.done() and row.id not in state.sessions.live
    with pytest.raises(NotFound):
        state.projects.get(p.id)
    assert not (runs_dir / rid).exists()
    assert (runs_dir / "r_other_project").is_dir()  # another project's run keeps its files
