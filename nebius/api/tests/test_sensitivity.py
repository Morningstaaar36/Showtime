"""Sensitivity (P2-04): Your plan's key run with fewer or more people, slower or faster walking.

Each variant changes one assumption (headcount × 0.8 / × 1.2, walking speed × 0.85 / × 1.15) and
keeps the seed, venue, events and tier. The range covers the runs that finished, the plan as
tested included; every run says whether it breaks the plan. Fake runners only: no Docker, no
live model calls.
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
from api.models import RunResult
from api.orchestrator.sensitivity import (
    VARIANTS,
    SensitivityError,
    sensitivity_status,
    start_sensitivity,
)
from api.orchestrator.session import SessionManager
from api.orchestrator.together import start_together_check
from api.tests.evidence_fakes import SimLikeRunner, reset_engine, use_test_settings
from api.tests.test_api import client as client
from api.tests.test_seeds import _baseline_session
from api.tests.test_together import kept_three_session

BASE_SPEED = 1.34


class AssumptionRunner(SimLikeRunner):
    """Simulator-like results that follow the assumptions, well inside every break rule:
    evacuation time (95%) is 60 s × (people / 1,200) × (1.34 / walking speed), peak density
    2 people per m², and `jam_above` people or more leave 50 people inside."""

    def __init__(self, runs_dir: Path, outcome: Any = None, jam_above: int | None = None) -> None:
        super().__init__(runs_dir, outcome)
        self.jam_above = jam_above
        self.speeds: dict[str, float] = {}

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        res = await super().run(job, on_progress)
        speed = float(job.sim_settings["walk_speed_mean"])
        self.speeds[job.request.run_id] = speed
        if res.status in ("ok", "partial"):
            m = res.metrics
            m.evac_time_p95_s = round(60 * m.agents_total / 1200 * BASE_SPEED / speed, 1)
            m.peak_density_ppm2 = 2.0
            m.time_above_danger_s = 0.0
            m.extra.pop("trapped", None)
            jam = self.jam_above is not None and m.agents_total >= self.jam_above
            m.agents_not_evacuated = 50 if jam else 0
        return res


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)

    def make(fail_variant_speed: float | None = None, jam_above: int | None = None) -> Any:
        def outcome(job: SimJob) -> str | None:
            speed = float(job.sim_settings["walk_speed_mean"])
            hit = fail_variant_speed is not None and abs(speed - fail_variant_speed) < 1e-6
            return "failed" if hit else None

        runner = AssumptionRunner(settings.runs_dir, outcome, jam_above)
        st = build_state(settings, llm=FakeLLM({}, settings), runner=runner)
        st.sessions = SessionManager(st)
        return st

    yield make
    reset_engine()


async def _settle(st: Any, sid: str) -> dict[str, Any]:
    await asyncio.gather(*[t for t in st.runs.tasks.values() if not t.done()])
    return sensitivity_status(st, st.sessions.get(sid))


def _by(out: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["variant"]: i for i in out["items"]}


async def test_each_assumption_changes_one_input_of_the_after_run(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    row = await kept_three_session(st)
    after_id = row.summary["final_run_id"]
    before = sensitivity_status(st, row)
    assert before["status"] == "none" and before["available"]
    assert before["key"]["side"] == "after" and before["key"]["run_id"] == after_id
    assert [v["variant"] for v in before["variants"]] == [v.key for v in VARIANTS]

    out = await _settle(st, start_sensitivity(st, row)["session_id"])
    items = _by(out)
    assert list(items) == [v.key for v in VARIANTS]
    # the plan as tested is rebuilt exactly, so its run is reused
    assert items["as_tested"]["run_id"] == after_id and items["as_tested"]["original"]
    assert len({i["run_id"] for i in out["items"]}) == 5

    original = st.runs.get(after_id)
    total = original.result["metrics"]["agents_total"]
    for key, people in (("people_minus_20", 0.8), ("people_plus_20", 1.2)):
        run = st.runs.get(items[key]["run_id"])
        assert items[key]["metrics"]["agents_total"] == round(total * people)
        assert st.runner.speeds[run.id] == BASE_SPEED  # speed unchanged
    for key, speed in (("speed_minus_15", 0.85), ("speed_plus_15", 1.15)):
        run = st.runs.get(items[key]["run_id"])
        assert st.runner.speeds[run.id] == pytest.approx(BASE_SPEED * speed)
        assert items[key]["metrics"]["agents_total"] == total  # headcount unchanged
        assert run.venue_hash == original.venue_hash
    events = []
    for item in out["items"]:
        run = st.runs.get(item["run_id"])
        # same seed, tier, attack and events in every run
        assert run.request["seed"] == 42 and run.tier == 3
        assert run.attack_id == original.attack_id == "A1"
        if not item["original"]:
            events.append([e["type"] for e in run.request["extensions"]["events"]])
        assert item["included"] and item["breaks"] == []
    assert len(events) == 4 and all(e == events[0] for e in events)
    assert "block_exit" in events[0] and "marshal_redirect" in events[0]

    evac = {k: i["metrics"]["evac_time_p95_s"] for k, i in items.items()}
    assert evac["speed_minus_15"] > evac["as_tested"] > evac["speed_plus_15"]
    rng = out["range"]["evac_time_p95_s"]
    assert rng["n"] == 5
    assert rng["min"] == min(evac.values()) and rng["max"] == max(evac.values())
    assert out["range"]["agents_not_evacuated"] == {"min": 0.0, "max": 0.0, "median": 0.0, "n": 5}
    assert out["status"] == "done" and out["done"] == out["total"] == 5
    assert out["holds_in_all"] is True and out["breaks_in"] == [] and out["notes"] == []

    # repeating the check reuses every run
    calls = len(st.runner.calls)
    again = await _settle(st, start_sensitivity(st, row)["session_id"])
    assert [i["run_id"] for i in again["items"]] == [i["run_id"] for i in out["items"]]
    assert len(st.runner.calls) == calls


async def test_a_variant_that_breaks_the_plan_is_named(make_state: Callable[..., Any]) -> None:
    st = make_state(jam_above=1400)  # the hall holds 1,200: only 20% more jams
    row = await kept_three_session(st)
    out = await _settle(st, start_sensitivity(st, row)["session_id"])
    items = _by(out)
    assert items["people_plus_20"]["breaks"] == ["50 people still inside at the end"]
    assert all(not i["breaks"] for k, i in items.items() if k != "people_plus_20")
    assert out["holds_in_all"] is False and out["breaks_in"] == ["20% more people"]
    assert out["range"]["agents_not_evacuated"]["max"] == 50


async def test_a_failed_variant_is_listed_and_left_out(make_state: Callable[..., Any]) -> None:
    st = make_state(fail_variant_speed=BASE_SPEED * 1.15)
    row = await kept_three_session(st)
    out = await _settle(st, start_sensitivity(st, row)["session_id"])
    fast = _by(out)["speed_plus_15"]
    assert fast["status"] == "failed" and not fast["included"] and fast["basis"] == "unknown"
    assert out["range"]["evac_time_p95_s"]["n"] == 4
    assert out["notes"] == ["1 run did not finish and is left out of the range."]
    # not every assumption was simulated, so the plan is not said to hold across all of them
    assert out["holds_in_all"] is None


async def test_the_range_follows_the_chosen_changes(make_state: Callable[..., Any]) -> None:
    st = make_state()
    row = await kept_three_session(st)
    st.sessions.apply_final(row.id, ["F1_R1", "F2"])
    start_together_check(st, st.sessions.get(row.id))
    await asyncio.gather(*[t for t in st.runs.tasks.values() if not t.done()])
    await asyncio.sleep(0)
    row = st.sessions.get(row.id)
    subset_run = row.summary["applied"][-1]["together"]["run_id"]
    out = await _settle(st, start_sensitivity(st, row)["session_id"])
    assert out["key"]["side"] == "together" and out["key"]["run_id"] == subset_run
    assert _by(out)["as_tested"]["run_id"] == subset_run


async def test_baseline_when_nothing_was_kept_and_rerun_after_a_setting_change(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    venue = st.projects.venue(p.id)
    base = await st.runs.run(st.runs.build_job(venue, tier=3, seed=42), project_id=p.id)
    row = _baseline_session(st, base.run_id, p.id)
    out = await _settle(st, start_sensitivity(st, row)["session_id"])
    assert out["key"]["side"] == "baseline"
    assert _by(out)["as_tested"]["run_id"] == base.run_id
    assert all(st.runs.get(i["run_id"]).attack_id is None for i in out["items"])

    st.runs.settings = st.settings.model_copy(update={"walk_speed_mean": 1.2})
    changed = await _settle(st, start_sensitivity(st, row)["session_id"])
    first = _by(changed)["as_tested"]
    assert not first["original"] and first["run_id"] != base.run_id
    assert any("simulated again" in n for n in changed["notes"])


def test_speed_factor_changes_the_run_identity_only_when_used(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    p = st.projects.create("Hall", template_id="school_wing")
    venue = st.projects.venue(p.id)
    plain = st.runs.build_job(venue, tier=3, seed=42)
    assert st.runs.build_job(venue, tier=3, seed=42, speed_factor=1.0).request.run_id == (
        plain.request.run_id
    )
    fast = st.runs.build_job(venue, tier=3, seed=42, speed_factor=1.15)
    assert fast.request.run_id != plain.request.run_id
    for k in ("walk_speed_mean", "walk_speed_sd", "stair_speed"):
        assert fast.sim_settings[k] == pytest.approx(plain.sim_settings[k] * 1.15, abs=1e-4)
    for k in ("specific_flow", "stair_flow", "slow_walker_fraction"):
        assert fast.sim_settings[k] == plain.sim_settings[k]


# --- routes ----------------------------------------------------------------------------------


def _wait(client: TestClient, path: str, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while True:
        body = client.get(path).json()
        if done(body) or time.monotonic() > deadline:
            return body
        time.sleep(0.05)


def test_sensitivity_routes(client: TestClient) -> None:
    st = client.app.state.showtime  # type: ignore[attr-defined]
    pid = client.post("/api/v1/projects", json={"template_id": "school_wing"}).json()["id"]
    run = client.post("/api/v1/runs", json={"project_id": pid, "tier": 3}).json()
    _wait(client, f"/api/v1/runs/{run['id']}", lambda r: r["status"] in ("ok", "partial"))
    _baseline_session(st, run["id"], pid)

    status = client.get("/api/v1/sessions/s_base/sensitivity").json()
    assert status["status"] == "none" and status["available"]
    assert client.get("/api/v1/sessions/missing/sensitivity").status_code == 404
    assert client.post("/api/v1/sessions/missing/sensitivity").status_code == 404

    r = client.post("/api/v1/sessions/s_base/sensitivity")
    assert r.status_code == 202, r.text
    assert r.json()["total"] == 5
    out = _wait(client, "/api/v1/sessions/s_base/sensitivity", lambda b: b["status"] == "done")
    assert out["status"] == "done" and out["done"] == 5
    assert [i["label"] for i in out["items"]] == [v.label for v in VARIANTS]

    from api.db.models import RedTeamSession
    from api.db.session import db_session

    with db_session(st.projects.db_url) as db:
        db.add(RedTeamSession(id="s_live", project_id=pid, venue_version=1, status="running"))
        db.commit()
    busy = client.post("/api/v1/sessions/s_live/sensitivity")
    assert busy.status_code == 409 and busy.json()["code"] == "sensitivity_unavailable"
    with pytest.raises(SensitivityError):
        start_sensitivity(st, st.sessions.get("s_live"))
