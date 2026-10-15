"""Ranges across seeds (N05): the plan's key run repeated with more seeds.

The after-fixes confirmation run (or the baseline when nothing was kept) runs again with
seeds + 1 … + n: same venue, events and tier, each a normal run with the seed in its identity.
The range covers the runs that finished; failed runs stay listed and are left out with a note.
Fake runners only: no Docker, no live model calls.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import ProgressFn, SimJob
from api.app.state import build_state
from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import RunResult
from api.orchestrator.seeds import SeedCheckError, seed_check_status, spread, start_seed_check
from api.orchestrator.session import SessionManager
from api.tests.evidence_fakes import SimLikeRunner, reset_engine, use_test_settings
from api.tests.test_api import client as client
from api.tests.test_redteam import BLUE, red_reply


class SeededRunner(SimLikeRunner):
    """Simulator-like results that change with the seed: every seed above 42 adds 5 s to the
    evacuation time (95%) and 0.1 people per m² to the peak density."""

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        res = await super().run(job, on_progress)
        if res.status in ("ok", "partial"):
            k = job.request.seed - 42
            m = res.metrics
            if m.evac_time_p95_s is not None:
                m.evac_time_p95_s = round(m.evac_time_p95_s + 5 * k, 1)
            m.peak_density_ppm2 = round(m.peak_density_ppm2 + 0.1 * k, 2)
        return res


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)

    def make(fail_seeds: set[int] | None = None) -> Any:
        bad = fail_seeds or set()
        runner = SeededRunner(
            settings.runs_dir, lambda job: "failed" if job.request.seed in bad else None
        )
        script: dict[str, Any] = {
            "red_team": red_reply,
            "blue_team": BLUE,
            "judge": {"summary": "The plan was tested.", "recommendations": []},
        }
        st = build_state(settings, llm=FakeLLM(script, settings), runner=runner)
        st.sessions = SessionManager(st)
        return st

    yield make
    reset_engine()


async def _session(st: Any) -> Any:
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    row = st.sessions.start(
        p.id, {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1}
    )
    await st.sessions.live[row.id].task
    return st.sessions.get(row.id)


async def _settle(st: Any, out: dict[str, Any]) -> dict[str, Any]:
    tasks = [st.runs.tasks[i["run_id"]] for i in out["items"] if i["run_id"] in st.runs.tasks]
    await asyncio.gather(*tasks)
    return seed_check_status(st, st.sessions.get(out["session_id"]))


def _baseline_session(st: Any, run_id: str, project_id: str, sid: str = "s_base") -> Any:
    """A finished test that kept nothing: its key run is the baseline."""
    with db_session(st.projects.db_url) as db:
        db.add(
            RedTeamSession(
                id=sid,
                project_id=project_id,
                venue_version=1,
                status="finished",
                config={"seed": 42},
                summary={
                    "baseline_run_id": run_id,
                    "accepted_fixes": [],
                    "evaluation": {"status": "unconfirmed", "after_run_id": None},
                },
            )
        )
        db.commit()
    return st.sessions.get(sid)


# --- range math ----------------------------------------------------------------------------


def test_range_is_min_max_and_median() -> None:
    assert spread([200.0, 180.0, 210.0, 190.0]) == {
        "min": 180.0,
        "max": 210.0,
        "median": 195.0,
        "n": 4,
    }
    assert spread([3.0, 1.0, 2.0]) == {"min": 1.0, "max": 3.0, "median": 2.0, "n": 3}
    assert spread([4.5]) == {"min": 4.5, "max": 4.5, "median": 4.5, "n": 1}
    assert spread([]) is None


# --- the after run with more seeds ----------------------------------------------------------


async def test_more_seeds_repeat_the_after_run_with_distinct_seeds(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    row = await _session(st)
    after_id = row.summary["evaluation"]["after_run_id"]
    assert row.summary["accepted_fixes"] and after_id
    before = seed_check_status(st, row)
    assert before["status"] == "none" and before["available"]
    assert before["key"]["side"] == "after" and before["key"]["run_id"] == after_id
    assert before["default_extra"] == 3 and before["max_extra"] == 5

    out = await _settle(st, start_seed_check(st, row))
    items = out["items"]
    # the original run is the first seed: rebuilt exactly, so it is reused, not re-run
    assert items[0] == {**items[0], "seed": 42, "run_id": after_id, "original": True}
    assert [i["seed"] for i in items] == [42, 43, 44, 45]
    ids = [i["run_id"] for i in items]
    assert len(set(ids)) == 4
    original = st.runs.get(after_id)
    for item in items[1:]:
        run = st.runs.get(item["run_id"])
        # same venue, events and tier; only the seed differs, and it is part of the identity
        assert run.request["seed"] == item["seed"]
        assert run.tier == original.tier == 3
        assert run.venue_hash == original.venue_hash
        assert run.attack_id == original.attack_id == row.summary["worst_attack_id"]
        assert run.request["extensions"]["events"] == original.request["extensions"]["events"]
        assert run.session_id == row.id and run.project_id == row.project_id
        assert f"seed {item['seed']}" in run.label
    assert out["status"] == "done" and out["done"] == out["total"] == 4

    p95 = [st.runs.get(i).result["metrics"]["evac_time_p95_s"] for i in ids]
    assert p95[1:] == [p95[0] + 5, p95[0] + 10, p95[0] + 15]
    rng = out["range"]
    assert rng["evac_time_p95_s"] == {
        "min": p95[0],
        "max": p95[0] + 15,
        "median": p95[0] + 7.5,
        "n": 4,
    }
    assert rng["peak_density_ppm2"]["n"] == 4
    assert rng["agents_not_evacuated"] == {"min": 0.0, "max": 0.0, "median": 0.0, "n": 4}
    assert out["bases"] == {"completed_simulation": 4} and out["notes"] == []
    assert all(i["included"] and i["basis"] == "completed_simulation" for i in items)

    # repeating the check reuses every run: no new simulations
    calls = len(st.runner.calls)
    again = await _settle(st, start_seed_check(st, row))
    assert [i["run_id"] for i in again["items"]] == ids
    assert len(st.runner.calls) == calls
    # more seeds later: the first ones are reused, at most five
    more = await _settle(st, start_seed_check(st, row, 9))
    assert [i["seed"] for i in more["items"]] == [42, 43, 44, 45, 46, 47]
    assert len(st.runner.calls) == calls + 2


async def test_failed_seeds_stay_listed_and_are_left_out_of_the_range(
    make_state: Callable[..., Any],
) -> None:
    st = make_state(fail_seeds={44})
    row = await _session(st)
    out = await _settle(st, start_seed_check(st, row, 3))
    failed = [i for i in out["items"] if i["seed"] == 44]
    assert len(failed) == 1 and failed[0]["status"] == "failed"
    assert failed[0]["basis"] == "unknown" and not failed[0]["included"]
    assert out["status"] == "done" and out["total"] == 4
    assert out["range"]["evac_time_p95_s"]["n"] == 3
    p95 = sorted(i["metrics"]["evac_time_p95_s"] for i in out["items"] if i["included"])
    assert out["range"]["evac_time_p95_s"]["min"] == p95[0]
    assert out["range"]["evac_time_p95_s"]["max"] == p95[-1]
    assert out["notes"] == ["1 run did not finish and is left out of the range."]


async def test_baseline_is_repeated_when_nothing_was_kept(make_state: Callable[..., Any]) -> None:
    st = make_state()
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    venue = st.projects.venue(p.id)
    base = await st.runs.run(st.runs.build_job(venue, tier=3, seed=42), project_id=p.id)
    row = _baseline_session(st, base.run_id, p.id)
    out = await _settle(st, start_seed_check(st, row, 2))
    assert out["key"]["side"] == "baseline" and out["key"]["run_id"] == base.run_id
    assert [(i["seed"], i["original"]) for i in out["items"]] == [
        (42, True),
        (43, False),
        (44, False),
    ]
    assert all(st.runs.get(i["run_id"]).attack_id is None for i in out["items"])
    assert out["range"]["evac_time_p95_s"]["n"] == 3

    # a setting changed since the test: the original seed runs again with the new settings
    st.runs.settings = st.settings.model_copy(update={"walk_speed_mean": 1.1})
    changed = await _settle(st, start_seed_check(st, row, 1))
    first = changed["items"][0]
    assert first["seed"] == 42 and not first["original"] and first["run_id"] != base.run_id
    assert any("seed 42 was simulated again" in n for n in changed["notes"])


async def test_unfinished_test_has_nothing_to_repeat(make_state: Callable[..., Any]) -> None:
    st = make_state()
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    with db_session(st.projects.db_url) as db:
        db.add(RedTeamSession(id="s_run", project_id=p.id, venue_version=1, status="running"))
        db.commit()
    row = st.sessions.get("s_run")
    status = seed_check_status(st, row)
    assert status["status"] == "none" and not status["available"]
    assert "hasn't finished" in status["reason"]
    with pytest.raises(SeedCheckError):
        start_seed_check(st, row)


# --- routes ----------------------------------------------------------------------------------


def _wait(client: TestClient, path: str, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while True:
        body = client.get(path).json()
        if done(body) or time.monotonic() > deadline:
            return body
        time.sleep(0.05)


def test_seed_check_routes(client: TestClient) -> None:
    st = client.app.state.showtime  # type: ignore[attr-defined]
    pid = client.post("/api/v1/projects", json={"template_id": "school_wing"}).json()["id"]
    run = client.post("/api/v1/runs", json={"project_id": pid, "tier": 3}).json()
    _wait(client, f"/api/v1/runs/{run['id']}", lambda r: r["status"] in ("ok", "partial"))
    _baseline_session(st, run["id"], pid)

    status = client.get("/api/v1/sessions/s_base/seeds").json()
    assert status["status"] == "none" and status["available"]
    assert status["key"]["side"] == "baseline" and status["key"]["seed"] == 42
    assert client.post("/api/v1/sessions/s_base/seeds", json={"n": 6}).status_code == 422
    assert client.get("/api/v1/sessions/missing/seeds").status_code == 404
    assert client.post("/api/v1/sessions/missing/seeds", json={}).status_code == 404

    r = client.post("/api/v1/sessions/s_base/seeds", json={"n": 2})
    assert r.status_code == 202, r.text
    assert [i["seed"] for i in r.json()["items"]] == [42, 43, 44]
    out = _wait(client, "/api/v1/sessions/s_base/seeds", lambda b: b["status"] == "done")
    assert out["status"] == "done" and out["total"] == 3
    # the fake sandbox scales the instant estimate: every seed gives the same preview
    assert out["bases"] == {"preview": 3}
    evac = out["range"]["evac_time_p95_s"]
    assert evac["n"] == 3 and evac["min"] == evac["max"] == evac["median"]

    with db_session(st.projects.db_url) as db:
        db.add(RedTeamSession(id="s_live", project_id=pid, venue_version=1, status="running"))
        db.commit()
    busy = client.post("/api/v1/sessions/s_live/seeds", json={})
    assert busy.status_code == 409 and busy.json()["code"] == "seed_check_unavailable"
