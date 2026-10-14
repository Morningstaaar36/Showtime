"""Parallel branches in a red-team session: the screened attacks of a round and the candidate
fixes of one attack run at once, are read back in order, and stop cancels what is pending.

FakeRunner only: no Docker, no live model.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest

from api.adapters.llm import LLMError
from api.adapters.sandbox import FakeRunner, SimJob
from api.db.models import Run
from api.db.session import db_session
from api.models import RunResult
from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings

CFG = {"max_rounds": 2, "attacks_per_round": 3, "fixes_per_attack": 3, "fix_targets": 2}


async def _session(
    tmp: Path, monkeypatch: pytest.MonkeyPatch, parallel: bool, delay_s: float = 0.02
) -> tuple[Any, Any, list[Any]]:
    settings = use_test_settings(tmp, monkeypatch)
    st = app_state(settings, fake=True)
    st.runs.runner = FakeRunner(settings.runs_dir, delay_s=delay_s, max_parallel=4)
    st.llm.script["red_team"] = _down  # rule-based attacks: three per round
    p = st.projects.create("School", template_id="school_wing")
    row = st.sessions.start(p.id, {**CFG, "parallel_branches": parallel})
    await st.sessions.live[row.id].task
    scores = [e.payload for e in st.sessions.stored_events(row.id) if e.type == "score"]
    return st, st.sessions.get(row.id), scores


def _down(_: Any) -> Any:
    raise LLMError("connection refused")


def _comparable(row: Any) -> str:
    """The summary without its cost record, with this project's ids masked.

    The cost record holds wall-clock time, and in parallel also the simulations of candidate
    fixes that were not needed because an earlier one was kept. Run ids hash the venue, whose
    id is the project's.
    """
    rest = {k: v for k, v in row.summary.items() if k != "cost"}
    text = json.dumps(rest, sort_keys=True).replace(row.project_id, "P")
    return re.sub(r"r_[0-9a-f]{12}", "r_*", text)


async def test_parallel_session_matches_sequential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seq_st, seq, seq_scores = await _session(tmp_path / "seq", monkeypatch, parallel=False)
    seq_max = seq_st.runs.runner.max_active
    par_st, par, par_scores = await _session(tmp_path / "par", monkeypatch, parallel=True)
    reset_engine()
    assert seq.status == par.status == "finished"
    assert seq.summary["attacks"] and seq.summary["scoreboard"]
    assert _comparable(par) == _comparable(seq)
    # the sequential session never had two sandboxes busy; the parallel one did
    assert seq_max == 1
    assert par_st.runs.runner.max_active > 1
    assert max(r["attacks"] for r in seq.summary["scoreboard"]) > 1
    # same scoring events, in the same order
    assert par_scores == seq_scores


class SlowAttacks(FakeRunner):
    """Baseline at once; every attack simulation takes far longer than the test waits."""

    async def _run(self, job: SimJob) -> RunResult:
        if job.request.attack_id:
            await asyncio.sleep(30)
        return await super()._run(job)


async def test_stop_cancels_pending_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = use_test_settings(tmp_path, monkeypatch)
    st = app_state(settings, fake=True)
    st.runs.runner = SlowAttacks(settings.runs_dir, max_parallel=1)
    st.llm.script["red_team"] = _down
    p = st.projects.create("School", template_id="school_wing")
    row = st.sessions.start(p.id, {**CFG, "max_rounds": 1})
    live = st.sessions.live[row.id]
    for _ in range(200):
        if sum(n.startswith("atk:") for n in live.inflight) >= 2:
            break
        await asyncio.sleep(0.02)
    assert sum(n.startswith("atk:") for n in live.inflight) >= 2
    assert st.sessions.stop(row.id)
    await asyncio.wait_for(live.task, timeout=5)
    done = st.sessions.get(row.id)
    assert done.status == "stopped"
    assert done.summary["stopped_reason"] == "stopped by user"
    with db_session() as s:
        runs = [r for r in s.query(Run).all() if r.session_id == row.id]  # type: ignore[attr-defined]
    statuses = {r.status for r in runs}
    assert "cancelled" in statuses
    assert not statuses & {"queued", "running"}, "no orphan runs"
    assert not any(not t.done() for t in st.runs.tasks.values())
    # every started attack node is closed in the tree
    nodes: dict[str, str] = {}
    for e in st.sessions.stored_events(row.id):
        if e.type == "branch_node":
            nodes[e.payload["node_id"]] = e.payload["status"]
    assert all(v != "running" for v in nodes.values())
    reset_engine()
