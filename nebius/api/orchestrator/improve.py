"""Let the AI fix it: accept the proven fixes, test again, and repeat until the plan holds.

One test (a Red Team Night session) attacks the plan, simulates every attack in the sandbox and
keeps only the fixes the simulator proved. This loop takes the kept fixes as a new version (the
same as "Accept fixes" on Your plan), starts the same test on it, and goes round again until no
attack breaks the plan, a test keeps no fix, or IMPROVE_ROUNDS tests have run. Every step is a
normal session and a normal version, so the organizer can open, compare or undo any of them.

The loop's record lives in memory (GET /sessions/{id}/improve); the sessions and versions it
made are stored like any others.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

log = logging.getLogger("showtime.improve")

POLL_S = 2.0

LoopStatus = Literal["running", "holds", "no_fix", "rounds_used", "stopped", "failed"]


class ImproveError(Exception):
    """The loop could not start (unknown session, still running, or nothing to build on)."""


@dataclass
class Iteration:
    session_id: str
    version: int
    breaks: int | None = None  # attacks that broke the plan in this test's first round
    attacks: int | None = None
    kept_fixes: list[str] = field(default_factory=list)
    fix_titles: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)  # worst attack, before its fixes
    after: dict[str, Any] = field(default_factory=dict)  # and after
    applied_version: int | None = None  # the version the kept fixes became


@dataclass
class ImproveLoop:
    id: str  # the first session's id
    project_id: str
    max_rounds: int
    status: LoopStatus = "running"
    detail: str = ""
    iterations: list[Iteration] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    task: asyncio.Task[None] | None = None
    stop_requested: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "status": self.status,
            "detail": self.detail,
            "max_rounds": self.max_rounds,
            "started_at": self.started_at,
            "iterations": [vars(i) for i in self.iterations],
            "current_session_id": self.iterations[-1].session_id if self.iterations else None,
        }


_loops: dict[str, ImproveLoop] = {}  # by every session id the loop ran


def loop_for(session_id: str) -> ImproveLoop | None:
    """The loop a session belongs to (as its start or as one of its tests)."""
    return _loops.get(session_id)


def _read(
    row: Any,
) -> tuple[int | None, int | None, list[str], list[str], dict[str, Any], dict[str, Any]]:
    s = row.summary or {}
    board = s.get("scoreboard") or []
    first = board[0] if board else {}
    kept = [str(f) for f in s.get("accepted_fixes") or []]
    titles = [str(f.get("title", "")) for f in s.get("fixes") or [] if f.get("fix_id") in kept]
    return (
        first.get("breaks"),
        first.get("attacks"),
        kept,
        titles,
        s.get("before") or {},
        s.get("after") or {},
    )


def start_improve(st: Any, session_id: str, rounds: int | None = None) -> ImproveLoop:
    """Start the loop from a test session (finished or still running)."""
    if session_id in _loops and _loops[session_id].status == "running":
        return _loops[session_id]
    row = st.sessions.get(session_id)
    if row is None:
        raise ImproveError("There is no such test.")
    n = int(rounds or st.settings.improve_rounds)
    loop = ImproveLoop(id=session_id, project_id=row.project_id, max_rounds=n)
    loop.iterations.append(Iteration(session_id=session_id, version=int(row.venue_version)))
    _loops[session_id] = loop
    # every retest confirms its kept fixes with full simulations: the plan it ends on is final
    config = {**dict(row.config or {}), "confirm_tier3": True}
    loop.task = asyncio.create_task(_drive(st, loop, config))
    return loop


def stop_improve(session_id: str) -> ImproveLoop | None:
    """Ask the loop to stop after the test that is running now."""
    loop = _loops.get(session_id)
    if loop is not None and loop.status == "running":
        loop.stop_requested = True
        loop.detail = "Stopping after the test that is running now."
    return loop


async def _finished(st: Any, session_id: str) -> Any:
    while True:
        row = st.sessions.get(session_id)
        if row is None or row.status not in ("running", "queued"):
            return row
        await asyncio.sleep(POLL_S)


async def _drive(st: Any, loop: ImproveLoop, config: dict[str, Any]) -> None:
    try:
        while True:
            it = loop.iterations[-1]
            n = len(loop.iterations)
            loop.detail = f"Test {n} of at most {loop.max_rounds}: attacking the plan"
            row = await _finished(st, it.session_id)
            if row is None or row.status != "finished":
                loop.status = "failed" if row is None or row.status == "failed" else "stopped"
                loop.detail = f"Test {n} did not finish ({row.status if row else 'missing'})."
                return
            it.breaks, it.attacks, it.kept_fixes, it.fix_titles, it.before, it.after = _read(row)
            if it.breaks == 0:
                loop.status, loop.detail = "holds", f"Test {n}: no attack broke the plan."
                return
            if not it.kept_fixes:
                loop.status = "no_fix"
                loop.detail = (
                    f"Test {n}: {it.breaks} of {it.attacks} attacks broke the plan and no fix "
                    "the AI proposed held up in the simulator. Edit the venue by hand, or "
                    "describe the change you have in mind."
                )
                return
            saved = st.sessions.apply_final(it.session_id)
            it.applied_version = int(saved.version)
            if loop.stop_requested or n >= loop.max_rounds:
                loop.status = "stopped" if loop.stop_requested else "rounds_used"
                loop.detail = f"Saved the fixes of test {n} as version {it.applied_version}; " + (
                    "stopped as asked." if loop.stop_requested else "test it again to confirm."
                )
                return
            nxt = st.sessions.start(loop.project_id, config)
            _loops[nxt.id] = loop
            loop.iterations.append(Iteration(session_id=nxt.id, version=int(nxt.venue_version)))
    except Exception as exc:  # the loop must say why it stopped, never vanish
        log.exception("improve loop %s failed", loop.id)
        loop.status, loop.detail = "failed", f"The loop stopped: {exc}"
