"""Stress test at scale: attacks × (plan + kept changes) × seeds as parallel quick
simulations, a live counter, and failures that stay listed. FakeRunner only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import LLMError
from api.adapters.sandbox import FakeRunner
from api.app.main import create_app
from api.orchestrator import stress
from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings


def _down(_: Any) -> Any:
    raise LLMError("connection refused")


@pytest.fixture
def st(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = app_state(settings, fake=True)
    state.runs.runner = FakeRunner(settings.runs_dir, delay_s=0.02, max_parallel=4)
    state.llm.script["red_team"] = _down
    yield state
    reset_engine()


async def test_stress_counts_every_run_and_lists_failures(st: Any) -> None:
    p = st.projects.create("School", template_id="school_wing")
    row = st.sessions.start(
        p.id, {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1}
    )
    await st.sessions.live[row.id].task
    summary = st.sessions.get(row.id).summary
    attacks, kept = len(summary["attacks"]), len(summary["accepted_fixes"])
    assert attacks >= 2
    rec = stress.start_stress(st, p.id, "session", seeds=2, include_fixes=True)
    total = attacks * (1 + kept) * 2
    assert rec["total"] == total and rec["status"] == "running"
    jobs = st.runs.runner
    fail_seed = rec["seeds"][1]  # every run of the second seed fails in the sandbox
    jobs.fail_ids = {r["run_id"] for r in rec["rows"] if r["seed"] == fail_seed}
    await stress._TASKS[rec["id"]]
    rec = stress.get_stress(st, rec["id"])
    assert rec["status"] == "done"
    assert rec["done"] == rec["total"] == total
    assert rec["failed"] == total // 2
    failed = [r for r in rec["rows"] if r["status"] == "failed"]
    assert len(failed) == total // 2 and all(r["error"] for r in failed)
    ok = [r for r in rec["rows"] if r["status"] == "ok"]
    assert all(r["metrics"] and r["basis"] == "preview" for r in ok)
    assert {r["variant"] for r in rec["rows"]} >= {"Plan as it is"}
    assert jobs.max_active > 1, "runs fanned out in parallel"
    assert stress.latest_stress(st, p.id)["id"] == rec["id"]


async def test_stress_with_rule_attacks_and_no_test_yet(st: Any) -> None:
    p = st.projects.create("Alley", template_id="t_alley")
    rec = stress.start_stress(st, p.id, "session", seeds=1, include_fixes=True)
    assert rec["notes"], "says why the standard attacks are used"
    await stress._TASKS[rec["id"]]
    rec = stress.get_stress(st, rec["id"])
    assert rec["done"] == rec["total"] >= 2 and rec["failed"] == 0
    assert {r["variant"] for r in rec["rows"]} == {"Plan as it is"}


def test_stress_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = app_state(settings, fake=True)
    with TestClient(create_app(state=state, settings=settings)) as c:
        pid = c.post("/api/v1/projects", json={"name": "A", "template_id": "t_alley"}).json()["id"]
        assert c.get(f"/api/v1/projects/{pid}/stress").json() is None
        assert c.post(f"/api/v1/projects/{pid}/stress", json={"seeds": 6}).status_code == 422
        r = c.post(f"/api/v1/projects/{pid}/stress", json={"attacks": "rules", "seeds": 1})
        assert r.status_code == 202
        sid = r.json()["id"]
        got = c.get(f"/api/v1/stress/{sid}").json()
        assert got["id"] == sid and got["total"] >= 2
        assert c.get("/api/v1/stress/st_missing").status_code == 404
    reset_engine()
