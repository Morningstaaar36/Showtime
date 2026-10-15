"""Chosen fixes tested together (P2-04): a subset of the kept fixes is simulated as one plan.

A session confirms the complete set of kept fixes under its worst attack. When the organizer
accepts only some of them, that combination was never simulated, so it can't be called
confirmed. Accepting a subset therefore starts one more run: the tested venue with only the
chosen fix bundles and their operational measures, under the same worst attack, tier and seed
as the session's after-fixes run. Its identity is a normal run identity, so repeating the check
reuses it.

The `applied` record of that version carries the check under `together`. Only when the run is a
simulation (it ran, fully or partly) does the record become `tested_together`; the check's own
`evaluation` then compares it with the session's before run by the same rules as a session
(`confirmed` only when both are full simulations that ran to the end). A run that fails, or a
preview from the mock sandbox, keeps the version "not tested together", with the reason, and the
check can be started again.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from api.core.evidence import SIMULATION_BASES, attempt_basis, evaluate
from api.core.plan import PlanConflict, PlanError, plan_hash
from api.core.venue_ops import PatchError
from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import RunResult, Venue
from api.orchestrator.seeds import KeyRun, SeedCheckError, key_run

log = logging.getLogger("showtime.together")

TESTED_TOGETHER = "These changes were simulated together under the worst attack."
PENDING = ("queued", "running")


class TogetherCheckError(Exception):
    """The check can't start; the message says why in organizer words."""


def _subset_record(session: Any, current_hash: str | None = None) -> tuple[int, dict[str, Any]]:
    """The latest applied subset record (of the current plan when its hash is given)."""
    applied = list((session.summary or {}).get("applied") or [])
    for i in range(len(applied) - 1, -1, -1):
        rec = applied[i]
        if not isinstance(rec, dict) or not rec.get("fix_ids"):
            continue
        if current_hash is not None and rec.get("plan_hash") != current_hash:
            continue
        if rec.get("together") is not None or not rec.get("tested_together"):
            return i, rec
    raise TogetherCheckError("No version holds only some of this test's changes.")


def _spec(st: Any, session: Any, fix_ids: list[str]) -> KeyRun:
    """The subset's run: the tested venue with only the chosen fixes, under the worst attack."""
    try:
        after = key_run(st, session)
    except SeedCheckError as exc:
        raise TogetherCheckError(str(exc)) from exc
    if after.side != "after" or after.attack is None:
        raise TogetherCheckError("This test has no after-fixes run to compare the changes with.")
    original = st.projects.venue(session.project_id, session.venue_version)
    venue, measures = st.sessions._rebuild(original, dict(session.summary or {}), fix_ids)
    return KeyRun(
        side="together",
        run_id="",
        venue=venue,
        tier=after.tier,
        seed=after.seed,
        attack=after.attack,
        extra=measures,
        label=f"Chosen changes together · {after.attack.title}",
        venue_version=session.venue_version,
    )


def subset_key(st: Any, session: Any) -> KeyRun | None:
    """The key run of the current plan when it holds a subset simulated together, else None."""
    current = st.projects.version(session.project_id)
    cur_hash = plan_hash(Venue.model_validate(current.venue))
    try:
        _, rec = _subset_record(session, cur_hash)
    except TogetherCheckError:
        return None
    check = rec.get("together") or {}
    if check.get("status") != "done" or not check.get("run_id"):
        return None  # not simulated together (yet): its numbers would not be the subset's
    try:
        spec = _spec(st, session, [str(f) for f in rec["fix_ids"]])
    except (TogetherCheckError, PlanConflict, PlanError, PatchError, ValueError):
        return None
    return replace(spec, run_id=str(check["run_id"]))


def plan_key(st: Any, session: Any) -> KeyRun:
    """The run Your plan's numbers rest on: the chosen subset run, else the session's key run."""
    return subset_key(st, session) or key_run(st, session)


def _store(st: Any, session_id: str, index: int, record: dict[str, Any]) -> dict[str, Any]:
    with db_session(st.projects.db_url) as db:
        row = db.get(RedTeamSession, session_id)
        if row is None:
            return record
        summary = dict(row.summary or {})
        applied = list(summary.get("applied") or [])
        if index < len(applied):
            applied[index] = record
            summary["applied"] = applied
            row.summary = summary
            db.add(row)
            db.commit()
    return record


def start_together_check(st: Any, session: Any) -> dict[str, Any]:
    """Simulate the latest subset version's fixes together (needs a running event loop)."""
    index, rec = _subset_record(session)
    fix_ids = [str(f) for f in rec["fix_ids"]]
    try:
        spec = _spec(st, session, fix_ids)
        job = st.runs.build_job(
            spec.venue,
            tier=spec.tier,
            seed=spec.seed,
            attack=spec.attack,
            extra=spec.extra,
            parent_run_id=((session.summary or {}).get("evaluation") or {}).get("before_run_id"),
        )
    except (PlanConflict, PlanError, PatchError, ValueError) as exc:
        problems = getattr(exc, "problems", None) or getattr(exc, "issues", None) or [exc]
        first = problems[0]
        raise TogetherCheckError(
            "The chosen changes can't be simulated together: "
            + str(getattr(first, "message", first))
        ) from exc
    job.request.extensions["events"] = job.events
    rid = str(
        st.runs.submit(
            job,
            project_id=session.project_id,
            venue_version=session.venue_version,
            session_id=session.id,
            label=spec.label[:120],
        )
    )
    rec = {
        **rec,
        "together": {
            "status": "running",
            "run_id": rid,
            "fix_ids": fix_ids,
            "attack_id": spec.attack.attack_id if spec.attack else None,
            "attack_title": spec.attack.title if spec.attack else None,
            "tier": spec.tier,
            "seed": spec.seed,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "evaluation": None,
            "error": None,
        },
    }
    _store(st, session.id, index, rec)
    log.info("together check %s: fixes %s in run %s", session.id, fix_ids, rid)
    task = st.runs.tasks.get(rid)
    if task is not None and not task.done():
        sid = session.id
        task.add_done_callback(lambda _t: _refresh_quietly(st, sid))
    return together_status(st, st.sessions.get(session.id))


def _refresh_quietly(st: Any, session_id: str) -> None:
    try:
        together_status(st, st.sessions.get(session_id))
    except Exception:  # a callback must never raise into the event loop
        log.exception("together check %s: refresh failed", session_id)


def _result(st: Any, run_id: str | None) -> RunResult | None:
    row = st.runs.get(str(run_id)) if run_id else None
    if row is None or not row.result:
        return None
    try:
        return RunResult.model_validate(row.result)
    except ValueError:
        return None


def _before(st: Any, session: Any) -> RunResult | None:
    """The session's before run (the estimate shown in place of a failed one, if any).

    Sessions saved before evaluations existed name it only in their `final:before` node."""
    evaluation = (session.summary or {}).get("evaluation") or {}
    fallback = (evaluation.get("fallback_run_ids") or {}).get("before")
    found = _result(st, fallback) or _result(st, evaluation.get("before_run_id"))
    if found is not None:
        return found
    node = next(
        (
            ev.payload
            for ev in reversed(st.sessions.stored_events(session.id))
            if ev.type == "branch_node" and ev.payload.get("node_id") == "final:before"
        ),
        None,
    )
    return _result(st, node.get("run_id")) if node else None


def together_status(st: Any, session: Any) -> dict[str, Any]:
    """The latest subset version's check; settles the record once its run has finished."""
    base: dict[str, Any] = {"session_id": session.id if session else None}
    if session is None:
        return {**base, "status": "none", "record": None}
    try:
        index, rec = _subset_record(session)
    except TogetherCheckError:
        return {**base, "status": "none", "record": None}
    check = dict(rec.get("together") or {})
    if not check:
        return {**base, "status": "not_started", "record": rec}
    if check.get("status") not in PENDING:
        return {**base, "status": check["status"], "record": rec}
    row = st.runs.get(str(check.get("run_id")))
    if row is None:
        return {**base, "status": "running", "record": rec}
    if row.status in PENDING:
        check["progress"] = row.progress
        return {**base, "status": "running", "record": {**rec, "together": check}}
    after = _result(st, row.id)
    basis = attempt_basis(after) if after is not None else "unknown"
    if row.status in ("ok", "partial") and basis in SIMULATION_BASES and after is not None:
        evaluation = evaluate(
            _before(st, session), after, confirmation_ran=True, kept=len(check["fix_ids"])
        )
        check.update(status="done", basis=basis, evaluation=evaluation, error=None)
        rec = {**rec, "together": check, "tested_together": True, "note": TESTED_TOGETHER}
    elif row.status in ("ok", "partial") and basis == "preview":
        check.update(
            status="preview",
            basis=basis,
            error="The sandbox is a mock: it gives a preview, not a simulation.",
        )
        rec = {**rec, "together": check}
    else:
        check.update(
            status="failed",
            basis=basis,
            error=row.error or "The run did not finish.",
        )
        rec = {**rec, "together": check}
    check.pop("progress", None)
    _store(st, session.id, index, rec)
    return {**base, "status": check["status"], "record": rec}
