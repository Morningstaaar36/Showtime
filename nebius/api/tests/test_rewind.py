"""Rewind the worst moment: one checkpoint run, then "do nothing" and every response resumed
from that checkpoint in parallel, each compared with "do nothing". FakeRunner only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import LLMError
from api.adapters.sandbox import FakeRunner, SimJob
from api.app.main import create_app
from api.db.models import Run
from api.db.session import db_session
from api.models import Hotspot, RunResult
from api.orchestrator import rewind
from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings


def _down(_: Any) -> Any:
    raise LLMError("connection refused")


class Recorder(FakeRunner):
    """Keeps every job, and gives the worst attack's runs a danger hotspot at 75 s."""

    def __init__(self, runs_dir: Path) -> None:
        super().__init__(runs_dir, delay_s=0.02, max_parallel=4)
        self.jobs: dict[str, SimJob] = {}

    async def _run(self, job: SimJob) -> RunResult:
        self.jobs[job.request.run_id] = job
        res = await super()._run(job)
        if job.request.attack_id and not job.resume_from:
            res.hotspots = [
                Hotspot(floor_id="F0", x=1, y=1, peak_density_ppm2=4.0, t_s=40, level="warning"),
                Hotspot(floor_id="F0", x=2, y=2, peak_density_ppm2=6.2, t_s=75, level="danger"),
            ]
        return res


@pytest.fixture
def st(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = app_state(settings, fake=True)
    state.runs.runner = Recorder(settings.runs_dir)
    state.llm.script["red_team"] = _down  # rule-based attacks
    yield state
    reset_engine()


async def _finished_session(st: Any, template: str = "school_wing") -> Any:
    p = st.projects.create("Venue", template_id=template)
    row = st.sessions.start(
        p.id, {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1}
    )
    await st.sessions.live[row.id].task
    return st.sessions.get(row.id)


async def test_rewind_branches_from_one_checkpoint(st: Any) -> None:
    row = await _finished_session(st)
    assert row.summary["worst_attack_id"], "the session must find a worst attack"
    rec = rewind.start_rewind(st, row.id)
    assert rec["status"] == "running"
    await rewind._TASKS[rec["id"]]
    rec = rewind.get_rewind(st, rec["id"])
    assert rec is not None and rec["status"] == "done", rec.get("message")
    # the moment of peak danger: the densest danger hotspot of the worst run
    assert rec["moment"]["at_s"] == 75.0 and "6.2" in rec["moment"]["why"]

    runner: Recorder = st.runs.runner
    ckpt_id = rec["checkpoint_run_id"]
    ckpt = runner.jobs[ckpt_id]
    assert ckpt.request.checkpoint_at_s == 75.0 and not ckpt.request.resume
    assert ckpt.request.attack_id == row.summary["worst_attack_id"]
    assert ckpt.request.seed == row.config["seed"]
    assert (st.settings.runs_dir / ckpt_id / "checkpoint.json").exists()

    branches = rec["branches"]
    keys = [b["key"] for b in branches]
    assert keys[0] == "nothing" and len(keys) >= 3
    ran = [b for b in branches if b.get("run_id")]
    assert len(ran) == rec["total"] == rec["done"] == len(branches)
    for b in ran:
        job = runner.jobs[b["run_id"]]
        assert job.resume_from == ckpt_id and job.request.resume
        assert job.request.parent_run_id == ckpt_id
        assert runner.resumed[b["run_id"]] == ckpt_id
        assert (st.settings.runs_dir / b["run_id"] / "checkpoint.json").exists()
        assert b["basis"] == "preview" and b["metrics"]
        # every response starts no earlier than the rewind moment
        assert all(e["at_s"] >= 75.0 for e in b["events"])
    assert len({b["run_id"] for b in ran}) == len(ran), "one run per branch"
    # each response is compared with "do nothing" on the same four numbers
    for b in ran[1:]:
        assert set(b["vs_nothing"]) == {
            "evac_time_95_s",
            "people_inside",
            "peak_density_ppm2",
            "time_above_danger_s",
        }
        assert b["comparable"] is True
    if rec["best"]:
        assert next(b for b in branches if b["key"] == rec["best"])["better"]
    assert runner.max_active > 1, "branches ran in parallel"
    # stored with the session, and every run is finished
    assert rewind.latest_rewind(st, row.id)["id"] == rec["id"]
    with db_session() as s:
        statuses = {s.get(Run, b["run_id"]).status for b in ran}
    assert statuses <= {"ok", "partial"}


async def test_rewind_at_a_chosen_second_with_custom_responses(st: Any) -> None:
    row = await _finished_session(st)
    zone = st.projects.venue(row.project_id).floors[0].zones[0].id
    rec = rewind.start_rewind(
        st,
        row.id,
        at_s=30,
        responses=[
            {
                "label": "Hold the zone",
                "events": [{"type": "staggered_release", "zone_id": zone, "delay_s": 30}],
            }
        ],
    )
    await rewind._TASKS[rec["id"]]
    rec = rewind.get_rewind(st, rec["id"])
    assert rec["moment"] == {**rec["moment"], "at_s": 30.0, "source": "user"}
    assert [b["key"] for b in rec["branches"]] == ["nothing", "custom:1"]
    assert rec["branches"][1]["events"][0]["at_s"] == 30.0


async def test_rewind_refuses_a_multi_floor_venue(st: Any) -> None:
    row = await _finished_session(st, "conference_hall_2f")
    if not row.summary.get("worst_attack_id"):
        pytest.skip("no worst attack on this venue")
    n = len(st.runs.runner.jobs)
    rec = rewind.start_rewind(st, row.id)
    assert rec["status"] == "unsupported"
    assert "single-floor" in rec["message"]
    assert rec["id"] not in rewind._TASKS
    assert len(st.runs.runner.jobs) == n, "no run was started"


def test_rewind_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = app_state(settings, fake=True)
    with TestClient(create_app(state=state, settings=settings)) as c:
        assert c.post("/api/v1/sessions/s_missing/rewind", json={}).status_code == 404
        assert c.get("/api/v1/rewind/rw_missing").status_code == 404
        assert c.get("/api/v1/sessions/s_missing/rewind").json() is None
        assert c.post("/api/v1/sessions/x/rewind", json={"at_s": -1}).status_code == 422
    reset_engine()


async def test_without_a_break_it_rewinds_the_attack_that_came_out_worst(st: Any) -> None:
    st.base_settings = st.base_settings.model_copy(
        update={"target_evac_indoor_s": 100_000, "density_danger_ppm2": 99, "fix_min_gain": 9}
    )
    row = await _finished_session(st)
    assert row.summary["worst_attack_id"] is None
    rec = rewind.start_rewind(st, row.id)
    await rewind._TASKS[rec["id"]]
    rec = rewind.get_rewind(st, rec["id"])
    assert rec["status"] == "done" and rec["hardest_not_breaking"]
    assert rec["attack"]["attack_id"] in {a["attack_id"] for a in row.summary["attacks"]}
    assert "No attack broke the plan" in rec["notes"][0]
