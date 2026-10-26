"""Autopilot (N13): one request taken to a tested plan, in eight plain-language steps.

A thin driver over the Copilot graph (orchestrator/copilot_graph.py), which does the work: from
a sentence it reads the brief, builds the venue, estimates the plan and saves the project; from
an existing project it starts at the simulation; then it runs a Red Team Night session and
writes the plan. This module holds the quick/thorough presets, turns the graph's progress into
steps, persists runs and events, streams them (replayable with `after`) and stops gracefully.

Nothing is applied on the organizer's behalf: the tested fixes wait on Your plan.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, select

from api.adapters.llm import BudgetExceeded, LLMError
from api.agents.base import AgentUnavailable
from api.db.models import AutopilotEventRow, AutopilotRunRow
from api.db.session import db_session
from api.models import Usage
from api.models.autopilot import (
    STEP_ORDER,
    STEP_PHASES,
    AutopilotDepth,
    AutopilotEvent,
    AutopilotRequest,
    AutopilotRun,
    AutopilotStep,
    AutopilotStepKey,
    initial_steps,
)
from api.orchestrator.copilot_graph import GRAPH, cost_record

log = logging.getLogger("showtime.autopilot")

# Red Team Night settings per depth; the session budgets (runs, wall clock, tokens) come from
# Settings like any other session. Thorough also runs the six-scenario sweep (graph routing).
QUICK: dict[str, Any] = {
    "max_rounds": 1,
    "attacks_per_round": 3,
    "fixes_per_attack": 2,
    "fix_targets": 2,
}
THOROUGH: dict[str, Any] = {
    "max_rounds": 3,
    "attacks_per_round": 5,
    "fixes_per_attack": 2,
    "fix_targets": 2,
}
PRESETS: dict[str, dict[str, Any]] = {"quick": QUICK, "thorough": THOROUGH}

PHASE_STEP: dict[str, AutopilotStepKey] = {
    phase: key for key, phases in STEP_PHASES.items() for phase in phases
}
OWN_VENUE = "Not needed: you started from your own venue."
NOT_REACHED = "Not reached."
STOPPED_BEFORE = "Stopped before this step."
STOPPED_DURING = "Stopped before this finished."
RESTARTED = "Stopped when the server restarted."
LLM_DOWN = (
    "The AI isn't answering right now, so it couldn't read your request. Try again in a "
    "minute, or draw your venue instead."
)
BUDGET_DOWN = "The AI budget ran out. Raise it in Settings, or try again later."
GENERIC = "Something went wrong while planning. Try again."


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def fmt_duration(s: float) -> str:
    """Seconds as plain words: "45 s", "4 min 12 s"."""
    s = max(0, round(s))
    m, sec = divmod(s, 60)
    return f"{m} min {sec} s" if m else f"{sec} s"


def _escape_time(metrics: dict[str, Any]) -> float | None:
    v = metrics.get("evac_time_p95_s") or metrics.get("evac_time_estimate_s")
    return float(v) if v is not None else None


@dataclass
class _Meter:
    """Tokens and money of the run's own (intake) agent calls."""

    usd: float = 0.0
    tokens: int = 0
    calls: int = 0

    def add(self, u: Usage) -> None:
        self.usd += u.cost_usd
        self.tokens += u.prompt_tokens + u.completion_tokens
        self.calls += 1


@dataclass
class LiveAutopilot:
    """In-memory state of a running Autopilot."""

    id: str
    depth: AutopilotDepth
    text: str | None
    project_id: str | None
    project_name: str | None
    steps: list[AutopilotStep]
    events: list[AutopilotEvent] = field(default_factory=list)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    graph: asyncio.Task[dict[str, Any]] | None = None
    session_id: str | None = None
    stop_requested: bool = False
    finished: bool = False
    meter: _Meter = field(default_factory=_Meter)
    red_usd: float = 0.0
    red_tokens: int = 0
    runs: list[str] = field(default_factory=list)  # background simulations this run started
    failure: str | None = None
    # what each finished step found, shown once the step is done
    results: dict[str, str] = field(default_factory=dict)
    tested: int = 0
    breaks: int = 0
    kept: int = 0
    before_s: float | None = None
    before_danger_s: float | None = None

    def step(self, key: str) -> AutopilotStep:
        return next(s for s in self.steps if s.key == key)


def _news(live: LiveAutopilot, last: int) -> Callable[[], bool]:
    """Wake a stream follower when the run ends or has events after `last`."""
    return lambda: live.finished or bool(live.events and live.events[-1].seq > last)


@dataclass
class _Hooks:
    """The driver's side of copilot_graph.AutopilotHooks."""

    manager: AutopilotManager
    live: LiveAutopilot
    session_config: dict[str, Any]

    def should_stop(self) -> bool:
        return self.live.stop_requested

    def on_session(self, session_id: str) -> None:
        self.manager._on_session(self.live, session_id)

    def on_usage(self, usage: Usage) -> None:
        self.live.meter.add(usage)
        self.manager._emit_cost(self.live)

    def intake(self) -> dict[str, float]:
        m = self.live.meter
        return {"usd": m.usd, "tokens": float(m.tokens), "calls": float(m.calls)}


def manager_for(st: Any) -> AutopilotManager:
    """The app's Autopilot manager (created on first use, kept on the app state)."""
    mgr: AutopilotManager | None = getattr(st, "autopilot", None)
    if mgr is None:
        mgr = AutopilotManager(st)
        st.autopilot = mgr
    return mgr


class AutopilotManager:
    """Starts, follows, stops and replays Autopilot runs."""

    def __init__(self, state: Any) -> None:
        self.st = state
        self.live: dict[str, LiveAutopilot] = {}
        self._bg: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ API
    def start(self, req: AutopilotRequest) -> AutopilotRun:
        """Create the run and work on it in the background (call from the event loop).

        A project that is already being planned returns its running Autopilot."""
        name: str | None = None
        if req.project_id:
            name = self.st.projects.get(req.project_id).name  # NotFound for unknown projects
            for other in self.live.values():
                if other.project_id == req.project_id and not other.finished:
                    return self._require(other.id)
        steps = initial_steps()
        if req.project_id:  # straight to the simulation
            for s in steps[:3]:
                s.status, s.detail = "skipped", OWN_VENUE
        rid = f"ap_{uuid.uuid4().hex[:10]}"
        row = AutopilotRunRow(
            id=rid,
            project_id=req.project_id,
            status="running",
            depth=req.depth,
            text=req.text.strip() if req.text else None,
            steps=[s.model_dump(mode="json") for s in steps],
            result={"project_name": name},
        )
        with db_session() as db:
            db.add(row)
            db.commit()
        live = LiveAutopilot(
            id=rid,
            depth=req.depth,
            text=row.text,
            project_id=req.project_id,
            project_name=name,
            steps=steps,
        )
        self.live[rid] = live
        live.task = asyncio.create_task(self._run(live))
        return self._require(rid)

    def get(self, run_id: str) -> AutopilotRun | None:
        """The run as the API returns it (None if unknown)."""
        with db_session() as db:
            row = db.get(AutopilotRunRow, run_id)
        if row is None:
            return None
        run = self._out(row)
        if run.status in ("queued", "running") and run_id not in self.live:
            # the server restarted mid-run and the work stopped with it
            steps = [
                s.model_copy(update={"status": "skipped", "detail": RESTARTED})
                if s.status in ("running", "pending")
                else s
                for s in run.steps
            ]
            run = run.model_copy(
                update={"status": "stopped", "partial_reason": "restart", "steps": steps}
            )
        return run

    def latest_for_project(self, project_id: str) -> AutopilotRun | None:
        """The newest Autopilot run of a project, if any."""
        with db_session() as db:
            row = db.exec(
                select(AutopilotRunRow)
                .where(AutopilotRunRow.project_id == project_id)
                .order_by(col(AutopilotRunRow.created_at).desc())
            ).first()
        return self.get(row.id) if row is not None else None

    def stop(self, run_id: str) -> bool:
        """Finish gracefully: a running red-team session stops after its current simulation;
        before that, the work in progress is cancelled. Returns False when nothing runs."""
        live = self.live.get(run_id)
        if live is None or live.finished or live.stop_requested:
            return False
        live.stop_requested = True
        self._emit(live, "log", {"level": "info", "message": "Stopping after the current step."})
        if live.session_id:
            self.st.sessions.stop(live.session_id)
        elif live.graph is not None and not live.graph.done():
            live.graph.cancel()
        return True

    def stored_events(self, run_id: str, after: int = 0) -> list[AutopilotEvent]:
        """Persisted events after `after`, in order."""
        with db_session() as db:
            rows = list(
                db.exec(
                    select(AutopilotEventRow)
                    .where(AutopilotEventRow.run_id == run_id, AutopilotEventRow.seq > after)
                    .order_by(col(AutopilotEventRow.seq))
                )
            )
        return [
            AutopilotEvent.model_validate(
                {"seq": r.seq, "type": r.type, "ts": r.ts, "payload": r.payload}
            )
            for r in rows
        ]

    async def stream(self, run_id: str, after: int = 0) -> AsyncIterator[AutopilotEvent]:
        """Replay stored events after `after`, then follow live ones until the run ends."""
        live = self.live.get(run_id)  # taken first: a run ending meanwhile keeps its events here
        last = after
        for ev in self.stored_events(run_id, after):
            last = ev.seq
            yield ev
        while live is not None:
            fresh = [e for e in live.events if e.seq > last]
            for ev in fresh:
                last = ev.seq
                yield ev
            if fresh:
                continue
            if live.finished:
                return
            async with live.cond:
                await live.cond.wait_for(_news(live, last))

    # -------------------------------------------------------------- the run
    async def _run(self, live: LiveAutopilot) -> None:
        start: dict[str, Any] = {"autopilot": True, "depth": live.depth}
        if live.project_id:
            start["project_id"] = live.project_id
        else:
            start["text"] = live.text or ""
        thread = f"autopilot-{live.id}"
        hooks = _Hooks(self, live, dict(PRESETS[live.depth]))
        config = {"configurable": {"st": self.st, "thread_id": thread, "autopilot": hooks}}
        final: dict[str, Any] = {}
        error: str | None = None
        if not live.stop_requested:  # Stop can come before the work starts
            live.graph = asyncio.create_task(self._drive(live, start, config))
            await asyncio.wait({live.graph})
            if not live.graph.cancelled():
                exc = live.graph.exception()
                if exc is None:
                    final = live.graph.result()
                elif isinstance(exc, (AgentUnavailable, LLMError)):
                    error = LLM_DOWN
                elif isinstance(exc, BudgetExceeded):
                    error = BUDGET_DOWN
                else:
                    log.error("autopilot %s failed", live.id, exc_info=exc)
                    error = GENERIC
        try:
            await self._finish(live, final, error)
        except Exception:  # a run must always end, even if saving its outcome failed
            log.exception("autopilot %s could not finish cleanly", live.id)
            live.finished = True
            await self._notify(live)
        finally:
            self.live.pop(live.id, None)
            try:
                GRAPH.checkpointer.delete_thread(thread)
            except Exception:  # checkpoints are only a cache here
                log.debug("could not drop checkpoints of %s", thread)

    async def _drive(
        self, live: LiveAutopilot, start: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        final: dict[str, Any] = {}
        async for mode, chunk in GRAPH.astream(start, config, stream_mode=["custom", "values"]):
            if mode == "custom":
                self._on_chunk(live, chunk)
            else:
                final = chunk
        return final

    async def _finish(self, live: LiveAutopilot, final: dict[str, Any], error: str | None) -> None:
        result: dict[str, Any] = dict(final.get("result") or {})
        if error or final.get("failed"):
            status, error = "failed", error or live.failure or GENERIC
        elif result.get("partial_reason") == "stopped" or (live.stop_requested and not result):
            status = "stopped"  # by the organizer, before or during the red team
        elif not final:
            status, error = "failed", GENERIC
        else:
            status = "finished"
        self._close_steps(live, status, error)
        if status != "finished":
            await self._cancel_runs(live)  # no simulation outlives a stopped or failed run
        if status == "stopped" and "partial_reason" not in result:
            result["partial_reason"] = "stopped"
        if "cost" not in result:
            session = self.st.sessions.get(live.session_id) if live.session_id else None
            result["cost"] = cost_record(
                self.st,
                session,
                {"usd": live.meter.usd, "tokens": live.meter.tokens, "calls": live.meter.calls},
                live.runs,
            )
        notes = [*result.get("notes", []), *final.get("notes", [])]
        result["notes"] = list(dict.fromkeys(n for n in notes if n))[:8]
        result["project_name"] = live.project_name
        with db_session() as db:
            row = db.get(AutopilotRunRow, live.id)
            if row is not None:
                row.status = status
                row.project_id = live.project_id
                row.session_id = live.session_id
                row.steps = [s.model_dump(mode="json") for s in live.steps]
                row.result = result
                row.error = error if status == "failed" else None
                row.finished_at = datetime.now(UTC)
                db.add(row)
                db.commit()
        self._emit(live, "done", self._require(live.id).model_dump(mode="json"))
        live.finished = True
        await self._notify(live)

    async def _cancel_runs(self, live: LiveAutopilot) -> None:
        runs = self.st.runs
        for rid in dict.fromkeys(live.runs):
            task = runs.tasks.get(rid)
            if task is None or task.done():
                continue
            try:
                await runs.cancel(rid)
                await asyncio.wait({task}, timeout=10)
            except Exception:
                log.exception("could not cancel run %s", rid)

    # -------------------------------------------------------- graph progress
    def _on_chunk(self, live: LiveAutopilot, c: dict[str, Any]) -> None:
        key, status = c.get("step"), c.get("status")
        title, detail = str(c.get("title") or ""), str(c.get("detail") or "")
        if key == "brief":
            if status == "running":
                self._enter(live, "understand", "Reading your request")
            elif status == "done":
                self._done(live, "understand", title)
            elif status == "failed":
                live.failure = f"The AI couldn't read the request. {detail}".strip()
                self._fail(live, "understand", live.failure)
        elif key in ("site", "layout"):
            if status == "failed":
                why = detail or "Describe the space in more detail, or draw it on the map."
                live.failure = f"The venue couldn't be built. {why}"
                self._fail(live, "venue", live.failure)
            else:
                self._enter(live, "venue", title)
                if status == "done":
                    live.results["venue"] = title
                if status == "warn":
                    self._log(live, "info", f"{title}. {detail}".strip())
        elif key == "estimates":
            if status == "running":
                self._enter(live, "capacity", "Estimating capacity, staff and facilities")
            else:
                live.results["capacity"] = detail or title
                self._enter(live, "capacity", detail or title)
                if status == "warn":
                    self._log(
                        live, "warning", "More people are planned than the venue holds safely."
                    )
        elif key == "project":
            self._done(live, "capacity")
            self._on_project(live, str(c.get("project_id")), c.get("name"))
        elif key == "simulate":
            if status == "running":
                people = int(c.get("people") or 0)
                self._enter(live, "simulate", f"Simulating how {people:,} people move and leave")
            elif status == "done" and c.get("run_id"):
                live.runs.append(str(c["run_id"]))
            elif status in ("failed", "warn"):
                live.failure = f"The crowd can't be simulated yet: {detail or title}"
                self._fail(live, "simulate", live.failure)
        elif key == "sweep":
            if status == "running":
                self._enter(live, "simulate", "Also simulating six what-if scenarios")
            elif status == "done":
                live.runs.extend(str(r) for r in c.get("run_ids") or [])
            elif status == "warn":
                self._log(live, "warning", f"The what-if scenarios didn't start: {detail}")
        elif key == "red_team" and isinstance(c.get("session_event"), dict):
            self._on_session_event(live, c["session_event"])
        elif key == "deliver":
            if status == "running":
                self._enter(live, "deliver", "Writing your plan")
            elif status == "done":
                self._done(live, "deliver", title)

    def _on_session_event(self, live: LiveAutopilot, ev: dict[str, Any]) -> None:
        kind, p = ev.get("type"), dict(ev.get("payload") or {})
        if kind == "status":
            key = PHASE_STEP.get(str(p.get("phase")))
            if key is not None:
                self._enter(live, key, self._phase_detail(p))
        elif kind == "score":
            board = p.get("scoreboard") or []
            live.tested = sum(int(r.get("attacks", 0)) for r in board)
            live.breaks = sum(int(r.get("breaks", 0)) for r in board)
            live.kept = int(p.get("fixes_accepted") or 0)
            live.results["attack"] = (
                f"{live.breaks} of {live.tested} broke the plan"
                if live.breaks
                else f"None of the {live.tested} broke the plan"
            )
            live.results["fix"] = (
                f"{live.kept} {'fix' if live.kept == 1 else 'fixes'} worked in testing"
                if live.kept
                else "No fix worked well enough"
            )
        elif kind == "run_finished":
            self._on_run(live, p)
        elif kind == "cost":
            live.red_usd = float(p.get("cost_usd") or 0.0)
            live.red_tokens = int(p.get("tokens_total") or 0)
            self._emit_cost(live)

    def _on_run(self, live: LiveAutopilot, p: dict[str, Any]) -> None:
        node, metrics = p.get("node_id"), dict(p.get("metrics") or {})
        t = _escape_time(metrics)
        preview = " (preview: no real simulation)" if p.get("provider") == "fake" else ""
        if node == "baseline" and t is not None:
            people = int(metrics.get("agents_total") or 0)
            who = f"of {people:,} people " if people else ""
            live.results["simulate"] = f"95% {who}got out in {fmt_duration(t)}{preview}"
        elif node == "final:before":
            live.before_s = t
            live.before_danger_s = metrics.get("time_above_danger_s")
        elif node == "final:after" and t is not None:
            was = f" (was {fmt_duration(live.before_s)})" if live.before_s is not None else ""
            parts = [f"95% out in {fmt_duration(t)}{was}"]
            # a fix may trade a few seconds of evacuation for a crowd that never reaches danger:
            # say both, not only the number that moved the wrong way
            danger, before = metrics.get("time_above_danger_s"), live.before_danger_s
            if danger is not None and before is not None and (danger or before):
                parts.append(f"above danger density for {danger:.0f} s (was {before:.0f} s)")
            live.results["confirm"] = f"Worst case with the fixes: {'; '.join(parts)}{preview}"

    @staticmethod
    def _phase_detail(p: dict[str, Any]) -> str | None:
        phase, msg = str(p.get("phase")), str(p.get("message") or "")
        if phase == "baseline":  # the simulate step already says what is simulated
            return None
        rnd = int(p.get("round") or 0)
        n = re.search(r"\d+", msg)
        quoted = re.search(r"“(.+)”", msg)
        text = {
            "red_team": "Thinking up what could go wrong",
            "screening": "Ranking the ideas with an instant estimate",
            "simulating": f"Simulating the {n.group(0)} most serious ideas"
            if n
            else "Simulating the most serious ideas",
            "blue_team": f"Trying fixes for “{quoted.group(1)}”"
            if quoted
            else "Trying fixes for the weak spots",
            "confirming": "Simulating the worst case again, with the fixes",
            "judging": "Checking every number in your plan",
        }.get(phase, msg)
        return f"Round {rnd}: {text}" if rnd > 1 and phase in PHASE_STEP else text

    def _on_project(self, live: LiveAutopilot, project_id: str, name: Any) -> None:
        live.project_id = project_id
        live.project_name = str(name) if name else live.project_name
        self._update(live, project_id=project_id)
        self._emit(live, "project", {"project_id": project_id, "name": live.project_name})

    def _on_session(self, live: LiveAutopilot, session_id: str) -> None:
        live.session_id = session_id
        self._update(live, session_id=session_id)
        self._emit(live, "session", {"session_id": session_id})
        if live.stop_requested:
            self.st.sessions.stop(session_id)

    # ---------------------------------------------------------------- steps
    def _skip_detail(self, live: LiveAutopilot, key: str) -> str:
        if live.stop_requested:
            return STOPPED_BEFORE
        if key == "fix" and live.tested and not live.breaks:
            return "Nothing broke, so no fixes were needed."
        if key == "confirm" and live.step("fix").status in ("done", "skipped") and not live.kept:
            return "No fix to confirm."
        return NOT_REACHED

    def _close(self, live: LiveAutopilot, s: AutopilotStep, now: str) -> None:
        if live.stop_requested and s.key not in live.results and s.key != "deliver":
            s.status, s.finished_at, s.detail = "skipped", now, STOPPED_DURING  # cut short
            return
        s.status, s.finished_at = "done", now
        s.detail = live.results.get(s.key, s.detail)

    def _enter(self, live: LiveAutopilot, key: AutopilotStepKey, detail: str | None) -> None:
        """Make `key` the running step: earlier running steps are done, steps it jumped over
        are skipped, and a later step that was running (a new red-team round) is done."""
        idx, now = STEP_ORDER.index(key), _now()
        for i, s in enumerate(live.steps):
            if i != idx and s.status == "running":
                self._close(live, s, now)
            elif i < idx and s.status == "pending":
                s.status, s.detail = "skipped", self._skip_detail(live, s.key)
        cur = live.steps[idx]
        if cur.status != "running":
            cur.status, cur.finished_at = "running", None
            cur.started_at = cur.started_at or now
        if detail:
            cur.detail = detail
        self._steps_changed(live)

    def _done(self, live: LiveAutopilot, key: AutopilotStepKey, detail: str | None = None) -> None:
        s, now = live.step(key), _now()
        if s.status != "running":
            self._enter(live, key, None)
        if detail:
            live.results[key] = detail
        self._close(live, s, now)
        self._steps_changed(live)

    def _fail(self, live: LiveAutopilot, key: AutopilotStepKey, detail: str) -> None:
        s = live.step(key)
        if s.status != "running":
            self._enter(live, key, None)
        s.status, s.finished_at, s.detail = "failed", _now(), detail
        self._steps_changed(live)

    def _close_steps(self, live: LiveAutopilot, status: str, error: str | None) -> None:
        """Final state of every step for a finished, stopped or failed run."""
        now = _now()
        for s in live.steps:
            if s.status == "running":
                if status == "finished":
                    self._close(live, s, now)
                elif status == "stopped":
                    s.status, s.finished_at, s.detail = "skipped", now, STOPPED_DURING
                else:
                    s.status, s.finished_at, s.detail = "failed", now, error
            elif s.status == "pending":
                s.status = "skipped"
                s.detail = STOPPED_BEFORE if status == "stopped" else self._skip_detail(live, s.key)
        if status == "failed" and not any(s.status == "failed" for s in live.steps):
            first = next((s for s in live.steps if s.detail == NOT_REACHED), live.steps[-1])
            first.status, first.detail = "failed", error
        self._steps_changed(live)

    def _steps_changed(self, live: LiveAutopilot) -> None:
        steps = [s.model_dump(mode="json") for s in live.steps]
        self._update(live, steps=steps)
        self._emit(live, "step", {"steps": steps})

    # ------------------------------------------------------- events and rows
    def _log(self, live: LiveAutopilot, level: str, message: str) -> None:
        self._emit(live, "log", {"level": level, "message": message})

    def _emit_cost(self, live: LiveAutopilot) -> None:
        m = live.meter
        cost = {
            "usd_total": round(m.usd + live.red_usd, 6),
            "tokens_total": m.tokens + live.red_tokens,
        }
        self._emit(live, "cost", cost)

    def _emit(self, live: LiveAutopilot, type_: str, payload: dict[str, Any]) -> None:
        ev = AutopilotEvent.model_validate(
            {"seq": len(live.events) + 1, "type": type_, "payload": payload}
        )
        live.events.append(ev)
        try:
            with db_session() as db:
                db.add(
                    AutopilotEventRow(
                        run_id=live.id, seq=ev.seq, type=ev.type, ts=ev.ts, payload=payload
                    )
                )
                db.commit()
        except Exception:
            log.exception("could not persist autopilot event")
        task = asyncio.get_running_loop().create_task(self._notify(live))
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    async def _notify(self, live: LiveAutopilot) -> None:
        async with live.cond:
            live.cond.notify_all()

    def _update(self, live: LiveAutopilot, **changes: Any) -> None:
        try:
            with db_session() as db:
                row = db.get(AutopilotRunRow, live.id)
                if row is None:
                    return
                for k, v in changes.items():
                    setattr(row, k, v)
                db.add(row)
                db.commit()
        except Exception:
            log.exception("could not save autopilot run %s", live.id)

    def _require(self, run_id: str) -> AutopilotRun:
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    @staticmethod
    def _out(row: AutopilotRunRow) -> AutopilotRun:
        res = dict(row.result or {})
        return AutopilotRun.model_validate(
            {
                "id": row.id,
                "status": row.status,
                "depth": row.depth,
                "text": row.text,
                "project_id": row.project_id,
                "project_name": res.get("project_name"),
                "session_id": row.session_id,
                "steps": row.steps or [s.model_dump() for s in initial_steps()],
                "report_url": res.get("report_url"),
                "headline": res.get("headline"),
                "cost": res.get("cost"),
                "notes": res.get("notes") or [],
                "evidence": res.get("evidence") or [],
                "ai_outage": bool(res.get("ai_outage")),
                "partial_reason": res.get("partial_reason"),
                "error": row.error,
                "created_at": _iso(row.created_at),
                "finished_at": _iso(row.finished_at),
            }
        )
