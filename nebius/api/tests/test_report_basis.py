"""The HTML report's wording follows the evidence basis (P2-03) and it says how the plan was
made (N16). Sessions run with FakeLLM and fake runners only."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import RunResult
from api.orchestrator.reports import build_bundle
from api.tests.evidence_fakes import (
    PricedLLM,
    app_state,
    is_after,
    reset_engine,
    use_test_settings,
)
from plugins.export_html_report import render, source_label, verdict

NEVER = re.compile(r"confirmed by simulation|everyone (is )?out", re.IGNORECASE)


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)
    yield lambda **kw: app_state(settings, **kw)
    reset_engine()


async def _report(st: Any, **cfg: Any) -> tuple[Any, str]:
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    row = st.sessions.start(
        p.id,
        {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1, **cfg},
    )
    await st.sessions.live[row.id].task
    row = st.sessions.get(row.id)
    return row, render(build_bundle(st, p.id, row.id))


@pytest.mark.parametrize(
    ("kw", "label"),
    [
        ({"tier": 3}, "full simulation"),
        ({"tier": 2}, "quick simulation (ran to the end)"),
        ({"tier": 2, "status": "partial"}, "quick simulation (first minutes only)"),
        ({"tier": 3, "status": "partial"}, "full simulation, stopped before everyone was out"),
        ({"tier": 1, "engine": "tier1"}, "instant estimate"),
        ({"tier": 3, "status": "timeout"}, "simulation did not complete"),
        ({"tier": 3, "engine": "fake", "provider": "fake"}, "preview only (no simulation)"),
        (
            {"tier": 1, "extensions": {"fallback_for": "r_x"}},
            "instant estimate (the simulation did not finish)",
        ),
    ],
)
def test_source_labels_follow_the_basis(kw: dict[str, Any], label: str) -> None:
    r = RunResult.model_validate({"run_id": "r_t", "status": "ok", **kw})
    assert source_label(r) == label
    assert not NEVER.search(source_label(r))


def test_an_instant_estimate_never_holds() -> None:
    r = RunResult(run_id="r_t", tier=1, status="ok", engine="tier1")
    assert verdict(r, 5) == ("Instant estimate only — not simulated", "neutral")


async def test_report_of_a_confirmed_plan(make_state: Callable[..., Any]) -> None:
    row, html = await _report(make_state(llm_cls=PricedLLM))
    assert row.summary["evaluation"]["status"] == "confirmed"
    assert "Evaluation: Confirmed by full simulations.</b>" in html
    assert "<td>Based on</td><td class='muted'>full simulation</td>" in html
    # people still inside sit next to the 95% time, and the 95% time is not "everyone out"
    assert "Still inside at the end" in html and "People still inside at the end" in html
    assert "for 95% of people to get out, not everyone" in html
    assert not NEVER.search(html)
    assert "Planning aid, not a safety certification." in html
    # how the plan was made: measured cost, models, simulations by kind and times
    cost = row.summary["cost"]
    assert "<h2>How this plan was made</h2>" in html
    assert f"${cost['usd_total']:.4f}" in html
    assert all(model in html for model in cost["by_model"])
    assert f"<td>Full simulations</td><td>{cost['sims']['full_sims']}</td>" in html
    assert "<td>Wall time</td>" in html and "<td>Simulation compute time</td>" in html
    assert "consultant" not in html.lower()
    # the simulator check from api/data/validation.json, pointing to Help
    assert "Simulator check: against a published bottleneck experiment" in html
    assert "See Help › How good is the simulator?" in html


async def test_report_of_a_timed_out_confirmation(make_state: Callable[..., Any]) -> None:
    row, html = await _report(make_state(outcome=lambda j: "timeout" if is_after(j) else None))
    ev = row.summary["evaluation"]
    assert ev["status"] == "failed"
    assert "Evaluation: Confirmation failed.</b>" in html
    assert "did not finish (timeout)" in html
    assert "<td class='muted'>instant estimate (the simulation did not finish)</td>" in html
    # the headline result is the linked estimate, labelled as such and never a pass
    assert "Instant estimate only — not simulated" in html
    assert "This plan holds" not in html and "<b>Holds</b>" not in html
    assert not NEVER.search(html)
    assert "$0 (free or local models)" in html  # FakeLLM is free


async def test_report_of_an_old_session_without_evidence_fields(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    row, _ = await _report(st)
    summary = dict(row.summary)
    for key in ("evaluation", "cost"):
        summary.pop(key)
    rid = summary["final_run_id"]
    summary["countdown"] = {**summary["countdown"], "rset_source": f"run {rid}"}
    with db_session() as db:
        stored = db.get(RedTeamSession, row.id)
        assert stored is not None
        stored.summary = summary
        db.add(stored)
        db.commit()
    html = render(build_bundle(st, row.project_id, row.id))
    # the old countdown label is derived from the stored run, not assumed confirmed
    assert f"the worst red-team attack (full simulation, run {rid})" in html
    assert not NEVER.search(html)
    assert 'class="evaluation' not in html  # nothing is invented for sessions that lack it
    assert "Simulation counts were not recorded for this session." in html
