"""Run service evidence records (P2-03, N16): reused runs are tagged as cache hits and results
stored before `basis` existed get it on read. Fake runners only."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from api.db.models import Run
from api.db.session import db_session
from api.models import RunResult
from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)
    yield lambda **kw: app_state(settings, **kw)
    reset_engine()


def _job(st: Any, project_id: str, tier: int = 2) -> Any:
    return st.runs.build_job(st.projects.venue(project_id), tier=tier, seed=7)


async def test_reused_runs_are_tagged_as_cache_hits(make_state: Callable[..., Any]) -> None:
    st = make_state()
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    first = await st.runs.run(_job(st, p.id), project_id=p.id)
    again = await st.runs.run(_job(st, p.id), project_id=p.id)
    assert first.run_id == again.run_id
    assert "cache_hit" not in first.extensions
    assert again.extensions["cache_hit"] is True
    assert first.basis == again.basis == "completed_simulation"
    # the tag lives on the copy handed out, never on the stored result
    assert "cache_hit" not in st.runs.get(first.run_id).result["extensions"]
    # a fresh service (another process) reuses the stored run the same way
    st2 = make_state()
    reused = await st2.runs.run(_job(st2, p.id), project_id=p.id)
    assert reused.extensions["cache_hit"] is True
    assert st2.runs.runner.calls == []


async def test_failed_runs_are_not_reused(make_state: Callable[..., Any]) -> None:
    st = make_state(outcome=lambda job: "timeout")
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    first = await st.runs.run(_job(st, p.id), project_id=p.id)
    again = await st.runs.run(_job(st, p.id), project_id=p.id)
    assert first.status == again.status == "timeout"
    assert "cache_hit" not in again.extensions  # retried, not reused
    assert len(st.runs.runner.calls) == 2


def test_old_stored_runs_get_their_basis_on_read(make_state: Callable[..., Any]) -> None:
    st = make_state()
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    old = {"run_id": "r_old", "tier": 3, "status": "partial", "engine": "jupedsim"}
    with db_session() as db:
        db.add(Run(id="r_old", project_id=p.id, tier=3, status="partial", result=old))
        db.commit()
    assert RunResult.model_validate(old).basis == "partial_simulation"
    assert st.runs.get("r_old").result["basis"] == "partial_simulation"
    assert {r.id: r.result["basis"] for r in st.runs.list(p.id)} == {"r_old": "partial_simulation"}
    # nothing is written back: the stored row keeps exactly what was saved
    with db_session() as db:
        stored = db.get(Run, "r_old")
        assert stored is not None and "basis" not in (stored.result or {})
