"""Chosen fixes tested together (P2-04): a subset of the kept fixes is simulated as one plan.

Accepting only some kept fixes saves a version that was never simulated as a whole. The check
runs that version's fix bundles together under the session's worst attack, with the same tier
and seed as its after-fixes run; only a simulation makes the version "tested together", and its
evaluation uses the session rules. Fake runners only: no Docker, no live model calls.
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
from api.adapters.sandbox import SimJob
from api.app.state import build_state
from api.core.evidence import evaluate
from api.core.plan import apply_fix_bundle
from api.core.venue_ops import venue_hash
from api.db.models import RedTeamSession, SessionEventRow
from api.db.session import db_session
from api.models import Attack, Fix
from api.orchestrator.session import NOT_TESTED_TOGETHER, SessionManager
from api.orchestrator.together import (
    TESTED_TOGETHER,
    TogetherCheckError,
    plan_key,
    start_together_check,
    together_status,
)
from api.tests.evidence_fakes import SimLikeRunner, reset_engine, use_test_settings
from api.tests.test_api import client as client
from api.tests.test_apply_subset import EAST_DOOR, MARSHALS, WIDER_DOOR

ATTACK = {
    "attack_id": "A1",
    "title": "South door lost",
    "events": [{"type": "block_exit", "exit_id": "door_s1", "at_s": 30}],
    "inspired_by": {"incident": "Test incident", "source_url": "https://example.org/incident"},
}
KEPT = (EAST_DOOR, WIDER_DOOR, MARSHALS)


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)

    def make(outcome: Callable[[SimJob], str | None] | None = None) -> Any:
        runner = SimLikeRunner(settings.runs_dir, outcome)
        st = build_state(settings, llm=FakeLLM({}, settings), runner=runner)
        st.sessions = SessionManager(st)
        return st

    yield make
    reset_engine()


async def kept_three_session(st: Any, sid: str = "s_subset") -> Any:
    """A finished session that kept three fixes, confirmed under its worst attack."""
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    venue = st.projects.venue(p.id)
    attack = Attack.model_validate(ATTACK)
    kept = [Fix.model_validate(f) for f in KEPT]
    final = venue
    for fx in kept:
        final = apply_fix_bundle(final, fx, st.registry)
    measures = [e for fx in kept for e in fx.operational]
    before = await st.runs.run(
        st.runs.build_job(venue, tier=3, seed=42, attack=attack), project_id=p.id
    )
    after = await st.runs.run(
        st.runs.build_job(final, tier=3, seed=42, attack=attack, extra=measures),
        project_id=p.id,
    )
    with db_session(st.projects.db_url) as db:
        db.add(
            RedTeamSession(
                id=sid,
                project_id=p.id,
                venue_version=1,
                status="finished",
                config={"seed": 42},
                summary={
                    "final_venue": final.model_dump(mode="json"),
                    "accepted_fixes": [f.fix_id for f in kept],
                    "fixes": [f.model_dump(mode="json") for f in kept],
                    "measures": [e.model_dump(mode="json") for e in measures],
                    "attacks": [attack.model_dump(mode="json")],
                    "worst_attack_id": attack.attack_id,
                    "final_run_id": after.run_id,
                    "evaluation": evaluate(before, after, confirmation_ran=True, kept=3),
                },
            )
        )
        db.commit()
    return st.sessions.get(sid)


async def settle(st: Any, sid: str) -> dict[str, Any]:
    await asyncio.gather(*[t for t in st.runs.tasks.values() if not t.done()])
    await asyncio.sleep(0)  # let done-callbacks run
    return together_status(st, st.sessions.get(sid))


async def test_a_subset_is_simulated_together_under_the_worst_attack(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    row = await kept_three_session(st)
    assert row.summary["evaluation"]["status"] == "confirmed"
    st.sessions.apply_final(row.id, ["F1_R1", "F2"])
    row = st.sessions.get(row.id)
    rec = row.summary["applied"][-1]
    assert rec["tested_together"] is False and rec["note"] == NOT_TESTED_TOGETHER
    assert together_status(st, row)["status"] == "not_started"

    started = start_together_check(st, row)
    assert started["status"] == "running"
    check = started["record"]["together"]
    assert check["fix_ids"] == ["F1_R1", "F2"] and check["attack_id"] == "A1"
    assert (check["tier"], check["seed"]) == (3, 42)

    out = await settle(st, row.id)
    assert out["status"] == "done"
    rec = out["record"]
    assert rec["tested_together"] is True and rec["note"] == TESTED_TOGETHER
    assert rec["together"]["basis"] == "completed_simulation"
    evaluation = rec["together"]["evaluation"]
    assert evaluation["status"] == "confirmed"
    assert evaluation["after_run_id"] == check["run_id"]
    assert evaluation["before_run_id"] == row.summary["evaluation"]["before_run_id"]
    # the record is saved: the checklist and Your plan now read "accepted"
    saved = st.sessions.get(row.id).summary["applied"][-1]
    assert saved["tested_together"] is True and saved["together"]["status"] == "done"

    # the run is exactly the chosen bundles under the worst attack, nothing else
    run = st.runs.get(check["run_id"])
    venue = st.projects.venue(row.project_id, 1)
    subset = venue
    for f in (EAST_DOOR, WIDER_DOOR):
        subset = apply_fix_bundle(subset, Fix.model_validate(f), st.registry)
    assert run.venue_hash == venue_hash(subset)
    assert run.attack_id == "A1" and run.tier == 3 and run.request["seed"] == 42
    types = [e["type"] for e in run.request["extensions"]["events"]]
    assert "block_exit" in types and "marshal_redirect" not in types
    assert run.session_id == row.id and "Chosen changes together" in run.label

    # the plan's key run is now the subset run (sensitivity and Your plan use it)
    key = plan_key(st, st.sessions.get(row.id))
    assert key.side == "together" and key.run_id == check["run_id"]
    assert venue_hash(key.venue) == venue_hash(subset)

    # starting again reuses the same run
    calls = len(st.runner.calls)
    again = start_together_check(st, st.sessions.get(row.id))
    assert again["record"]["together"]["run_id"] == check["run_id"]
    assert (await settle(st, row.id))["status"] == "done"
    assert len(st.runner.calls) == calls


async def test_a_failed_run_keeps_the_subset_untested_and_can_be_retried(
    make_state: Callable[..., Any],
) -> None:
    target: dict[str, Any] = {"hash": None}

    def outcome(job: SimJob) -> str | None:
        return "failed" if venue_hash(job.venue) == target["hash"] else None

    st = make_state(outcome)
    row = await kept_three_session(st)
    subset = st.projects.venue(row.project_id, 1)
    for f in (EAST_DOOR, WIDER_DOOR):
        subset = apply_fix_bundle(subset, Fix.model_validate(f), st.registry)
    target["hash"] = venue_hash(subset)
    st.sessions.apply_final(row.id, ["F1_R1", "F2"])
    start_together_check(st, st.sessions.get(row.id))
    out = await settle(st, row.id)
    assert out["status"] == "failed"
    rec = out["record"]
    assert rec["tested_together"] is False and rec["note"] == NOT_TESTED_TOGETHER
    assert rec["together"]["error"] and rec["together"]["evaluation"] is None
    # the key run stays the session's own after run until the subset is simulated
    assert plan_key(st, st.sessions.get(row.id)).side == "after"

    target["hash"] = None  # the sandbox works again: the same run is simulated again
    start_together_check(st, st.sessions.get(row.id))
    out = await settle(st, row.id)
    assert out["status"] == "done" and out["record"]["tested_together"] is True


async def test_a_session_saved_before_evaluations_finds_its_before_run(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()
    row = await kept_three_session(st)
    before_id = row.summary["evaluation"]["before_run_id"]
    with db_session(st.projects.db_url) as db:
        old = db.get(RedTeamSession, row.id)
        assert old is not None
        summary = dict(old.summary or {})
        summary.pop("evaluation")
        summary["final_run_id"] = row.summary["final_run_id"]
        old.summary = summary
        db.add(old)
        db.add(
            SessionEventRow(
                session_id=row.id,
                seq=1,
                type="branch_node",
                ts="2026-10-01T10:00:00",
                payload={"node_id": "final:before", "run_id": before_id},
            )
        )
        db.commit()
    st.sessions.apply_final(row.id, ["F1_R1", "F2"])
    start_together_check(st, st.sessions.get(row.id))
    out = await settle(st, row.id)
    evaluation = out["record"]["together"]["evaluation"]
    assert evaluation["status"] == "confirmed" and evaluation["before_run_id"] == before_id


async def test_every_kept_fix_needs_no_extra_check(make_state: Callable[..., Any]) -> None:
    st = make_state()
    row = await kept_three_session(st)
    st.sessions.apply_final(row.id)
    row = st.sessions.get(row.id)
    assert row.summary["applied"][-1]["tested_together"] is True
    assert together_status(st, row)["status"] == "none"
    with pytest.raises(TogetherCheckError):
        start_together_check(st, row)


# --- routes ----------------------------------------------------------------------------------


def _wait(client: TestClient, path: str, done: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while True:
        body = client.get(path).json()
        if done(body) or time.monotonic() > deadline:
            return body
        time.sleep(0.05)


def test_accepting_a_subset_starts_the_check(client: TestClient) -> None:
    st = client.app.state.showtime  # type: ignore[attr-defined]
    pid = client.post("/api/v1/projects", json={"template_id": "conference_hall_2f"}).json()["id"]
    venue = st.projects.venue(pid)
    kept = [Fix.model_validate(f) for f in KEPT]
    final = venue
    for fx in kept:
        final = apply_fix_bundle(final, fx, st.registry)
    after = client.post(
        "/api/v1/runs",
        json={"project_id": pid, "tier": 3, "attack": ATTACK},
    ).json()
    _wait(client, f"/api/v1/runs/{after['id']}", lambda r: r["status"] in ("ok", "partial"))
    with db_session(st.projects.db_url) as db:
        db.add(
            RedTeamSession(
                id="s_route",
                project_id=pid,
                venue_version=1,
                status="finished",
                config={"seed": 42},
                summary={
                    "final_venue": final.model_dump(mode="json"),
                    "accepted_fixes": [f.fix_id for f in kept],
                    "fixes": [f.model_dump(mode="json") for f in kept],
                    "attacks": [ATTACK],
                    "worst_attack_id": "A1",
                    "evaluation": {"status": "confirmed", "after_run_id": after["id"]},
                },
            )
        )
        db.commit()
    assert client.get("/api/v1/sessions/s_route/together").json()["status"] == "none"

    r = client.post("/api/v1/sessions/s_route/apply", json={"fix_ids": ["F1_R1", "F2"]})
    assert r.status_code == 200, r.text
    applied = r.json()["applied"]
    assert applied["tested_together"] is False
    assert applied["together"]["status"] == "running" and applied["together"]["run_id"]

    out = _wait(client, "/api/v1/sessions/s_route/together", lambda b: b["status"] != "running")
    # the fake sandbox gives previews: honest, but not a simulation
    assert out["status"] == "preview"
    assert out["record"]["tested_together"] is False
    assert "preview" in out["record"]["together"]["error"]

    assert client.get("/api/v1/sessions/missing/together").status_code == 404
    assert client.post("/api/v1/sessions/missing/together").status_code == 404
    again = client.post("/api/v1/sessions/s_route/together")
    assert again.status_code == 202, again.text


def test_the_check_is_unavailable_without_a_subset(client: TestClient) -> None:
    st = client.app.state.showtime  # type: ignore[attr-defined]
    pid = client.post("/api/v1/projects", json={"template_id": "school_wing"}).json()["id"]
    with db_session(st.projects.db_url) as db:
        db.add(RedTeamSession(id="s_none", project_id=pid, venue_version=1, status="finished"))
        db.commit()
    r = client.post("/api/v1/sessions/s_none/together")
    assert r.status_code == 409 and r.json()["code"] == "together_unavailable"
