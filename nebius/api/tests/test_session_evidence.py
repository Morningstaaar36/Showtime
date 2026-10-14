"""Typed evidence in Red Team Night sessions (P2-03).

A failed or timed-out simulation stays on record with basis `unknown`; the instant estimate
shown in its place is a separate, linked run. FakeLLM and fake runners only: no Docker, no
live model calls.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from api.adapters.sandbox import SimJob
from api.models import RunResult, SessionEvent
from api.tests.evidence_fakes import (
    app_state,
    is_after,
    is_before,
    reset_engine,
    use_test_settings,
)


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)
    yield lambda **kw: app_state(settings, **kw)
    reset_engine()


async def _session(st: Any, project_id: str, **cfg: Any) -> Any:
    row = st.sessions.start(
        project_id,
        {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1, **cfg},
    )
    await st.sessions.live[row.id].task
    return st.sessions.get(row.id)


def _events(st: Any, sid: str, type_: str) -> list[SessionEvent]:
    return [e for e in st.sessions.stored_events(sid) if e.type == type_]


# --- failed simulations and their estimates ------------------------------------------------


FAILING = [(is_after, "timeout", "final:after"), (is_before, "failed", "final:before")]


@pytest.mark.parametrize(("which", "status", "node"), FAILING)
async def test_a_failed_simulation_keeps_its_record_next_to_a_linked_estimate(
    make_state: Callable[..., Any], which: Callable[[SimJob], bool], status: str, node: str
) -> None:
    st = make_state(outcome=lambda job: status if which(job) else None)
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    row = await _session(st, p.id)
    assert row.status == "finished"
    assert row.summary["accepted_fixes"]
    finished = {e.payload["run_id"]: e.payload for e in _events(st, row.id, "run_finished")}
    failed_id = next(r for r, f in finished.items() if f["node_id"] == node and f["tier"] == 3)
    fallback_id = finished[failed_id]["fallback_run_id"]
    assert fallback_id == f"{failed_id}-est" != failed_id

    # the failed run is stored as it ended, with basis unknown
    failed = st.runs.get(failed_id)
    assert failed.status == status and failed.result["basis"] == "unknown"
    assert RunResult.model_validate(failed.result).basis == "unknown"
    # the estimate shown in its place is a separate, linked record
    fb = st.runs.get(fallback_id)
    assert fb.tier == 1 and fb.status in ("ok", "partial")
    fb_result = RunResult.model_validate(fb.result)
    assert fb_result.basis == "instant_estimate"
    assert fb_result.extensions["fallback_for"] == failed_id
    assert fb_result.extensions["fallback_reason"] == status

    # both records are in the stream, each with its own basis; the node shows the estimate
    assert finished[failed_id]["status"] == status
    assert finished[failed_id]["basis"] == "unknown"
    assert finished[fallback_id]["basis"] == "instant_estimate"
    assert finished[fallback_id]["fallback_for"] == failed_id
    node_ev = [
        e.payload for e in _events(st, row.id, "branch_node") if e.payload["node_id"] == node
    ]
    assert node_ev[-1]["run_id"] == fallback_id and node_ev[-1]["fallback_for"] == failed_id
    if node == "final:after":
        assert row.summary["final_run_id"] == failed_id  # the attempt, never the estimate
