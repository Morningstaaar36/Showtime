"""Red Team Night (section 12.1): red/blue loop over sandboxed simulation branches.

Events are persisted (SessionEventRow) and streamed to the UI; every budget ends the
session gracefully with what exists.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import col, select

from api.adapters.llm import Budget, BudgetExceeded, LLMError
from api.agents.base import AgentEnv, AgentUnavailable, audit_decision
from api.agents.blue_team import blue_team
from api.agents.context import readable
from api.agents.judge import judge
from api.agents.red_team import (
    incident_query,
    is_script_attack,
    red_team,
    signature,
    venue_features,
)
from api.core.annotations import carry_annotations
from api.core.countdown import choose_hazard, compute_countdown
from api.core.evidence import (
    CostMeter,
    attempt_id,
    comparable,
    describe_run,
    evaluate,
    evaluation_sentence,
    evidence_sentence,
    fallback_for,
)
from api.core.extensions import HazardContext, HazardResult, IncidentRecord
from api.core.plan import (
    PlanConflict,
    PlanError,
    append_legacy_measures,
    apply_fix_bundle,
    plan_hash,
    validate_operational,
)
from api.core.venue_ops import PatchError, apply_patch
from api.db.models import RedTeamSession, SessionEventRow
from api.db.session import db_session
from api.models import (
    Attack,
    Countdown,
    Fix,
    RunResult,
    ScenarioEventIn,
    SessionEvent,
    Venue,
    VenuePatch,
)
from api.orchestrator.archive import (
    KIND_IDS,
    Archive,
    BreakRule,
    Cell,
    Elite,
    Insert,
    pick_candidates,
    severity_score,
)
from api.orchestrator.fallbacks import rule_attacks, rule_attacks_for_cells, rule_fixes

# who proposes attacks and fixes in a session (`config["agents"]`): "model" (the default) lets
# the AI design them and uses the rules only when no model answers; "hybrid" also mixes rule
# attacks and standard fixes in; "rules" uses no model (the evaluation's baseline arm)
AGENT_MODES = ("model", "hybrid", "rules")

log = logging.getLogger("showtime.session")


class StopSession(Exception):
    """A budget or the user ended the session."""


class SessionConfigError(ValueError):
    """A session setting from the request has the wrong type or is out of range."""

    def __init__(self, message: str, errors: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.errors = errors


class SessionConfigIn(BaseModel):
    """The session settings a caller may choose; other keys are ignored. The budgets (runs,
    wall clock, tokens) can only be lowered: values above the Settings caps are capped."""

    model_config = ConfigDict(extra="ignore")

    max_rounds: int | None = Field(default=None, ge=1, le=10)
    attacks_per_round: int | None = Field(default=None, ge=1, le=10)
    fixes_per_attack: int | None = Field(default=None, ge=1, le=10)
    fix_targets: int | None = Field(default=None, ge=1, le=10)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    confirm_tier3: bool | None = None
    max_runs: int | None = Field(default=None, ge=1)
    max_wall_s: float | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, ge=1)
    parallel_branches: bool | None = None
    agents: str | None = None  # one of AGENT_MODES; an unknown mode falls back to "model"
    judge: bool | None = None  # false: keep the computed summary, no model call at the end


def session_config(settings: Any, config: dict[str, Any] | None) -> dict[str, Any]:
    """Validated session settings over the defaults (raises SessionConfigError)."""
    try:
        given = SessionConfigIn.model_validate(config or {}).model_dump(exclude_none=True)
    except ValidationError as exc:
        errs = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        first = errs[0]
        raise SessionConfigError(f"{'.'.join(first['loc'])}: {first['msg']}", errs) from exc
    caps = {
        "max_runs": settings.session_max_runs,
        "max_wall_s": settings.session_max_wall_s,
        "max_tokens": settings.session_max_tokens,
    }
    for key, cap in caps.items():
        if key in given:
            given[key] = min(given[key], cap)
    cfg = {
        "max_rounds": settings.max_rounds,
        "attacks_per_round": settings.attacks_per_round,
        "fixes_per_attack": settings.fixes_per_attack,
        "fix_targets": settings.fix_targets,
        "seed": settings.default_seed,
        "confirm_tier3": True,
        **caps,
        # independent branches of a step run at once (the runner bounds how many)
        "parallel_branches": True,
        # who proposes attacks and fixes (see AGENT_MODES): "model" is the product default
        "agents": "model",
        **given,
    }
    if cfg["agents"] not in AGENT_MODES:
        cfg["agents"] = "model"
    return cfg


class StalePlan(PlanConflict):
    """A session's fixed plan was computed for an earlier venue geometry."""


class FixSelectionError(ValueError):
    """The organizer's choice of kept fixes is empty or names fixes the session did not keep."""


class FixConflict(PlanConflict):
    """The chosen fixes cannot be rebuilt without fixes that were left out."""


NOT_TESTED_TOGETHER = (
    "These changes were tested one by one, not together: test again before relying on them."
)


def severity(r: RunResult) -> float:
    """One number to compare runs (lower is better). Danger time dominates, then density,
    then people left inside, then evacuation time."""
    m = r.metrics
    rset = m.evac_time_p95_s or m.extra.get("rset_extrapolated_s") or 0.0
    return (
        m.time_above_danger_s * 10.0
        + max(0.0, m.peak_density_ppm2 - 3.5) * 60.0
        + m.agents_not_evacuated * 2.0
        + float(rset) / 10.0
    )


def evac_estimate(r: RunResult) -> float | None:
    """95% evacuation time, or the extrapolated estimate for partial (Tier 2) runs."""
    m = r.metrics
    v = m.evac_time_p95_s if m.evac_time_p95_s is not None else m.extra.get("rset_extrapolated_s")
    return float(v) if v is not None else None


def break_reasons(
    r: RunResult,
    danger: float,
    min_s: float,
    target_s: float | None = None,
    safety_factor: float = 1.5,
) -> list[str]:
    """Why a run counts as a break (contract: docs/API_CONTRACT.md)."""
    m = r.metrics
    out: list[str] = []
    if r.status in ("failed", "timeout"):
        return []
    rset = evac_estimate(r)
    if target_s and rset is not None and rset * safety_factor > target_s:
        out.append(
            f"evacuation time {rset:.0f} s × safety factor {safety_factor:g} exceeds the "
            f"{target_s / 60:.0f} min target"
        )
    if m.time_above_danger_s >= min_s:
        out.append(
            f"density at or above {danger:g} people per m² for {m.time_above_danger_s:.0f} s"
        )
    trapped = int(m.extra.get("trapped", 0))
    if trapped:
        out.append(f"{trapped} people trapped with no open exit")
    tol = max(5, round(m.agents_total * 0.005))
    if m.agents_not_evacuated > tol and r.tier != 2:
        out.append(f"{m.agents_not_evacuated} people still inside at the end")
    if r.tier == 2 and m.agents_not_evacuated > tol and m.evac_time_p95_s is None:
        frac = m.extra.get("evacuated_fraction")
        if frac is not None and frac < 0.5:
            out.append(f"only {frac * 100:.0f}% out after {r.sim_time_s:.0f} s")
    return out


# attack_card `screening` label for AI-written scenarios: the instant estimate cannot run
# code, so they skip tier-1 ranking and go straight to a quick simulation
SCRIPT_SCREENING = "quick_simulation"


def headline(r: RunResult | None) -> dict[str, Any]:
    """Compact metrics for events and the judge."""
    if r is None:
        return {}
    m = r.metrics
    return {
        "evac_time_p95_s": m.evac_time_p95_s,
        "evac_time_estimate_s": m.extra.get("rset_extrapolated_s"),
        "peak_density_ppm2": m.peak_density_ppm2,
        "time_above_danger_s": m.time_above_danger_s,
        "agents_not_evacuated": m.agents_not_evacuated,
        "agents_total": m.agents_total,
    }


PLAIN = {
    "evac_time_p95_s": "evacuation time for 95% of people (seconds)",
    "evac_time_estimate_s": "estimated evacuation time for 95% of people (seconds)",
    "evacuation_time_95_s": "evacuation time for 95% of people (seconds)",
    "peak_density_ppm2": "peak density (people per square metre)",
    "peak_density_people_per_m2": "peak density (people per square metre)",
    "time_above_danger_s": "time above the danger density (seconds)",
    "seconds_above_danger_density": "time above the danger density (seconds)",
    "agents_not_evacuated": "people still inside at the end",
    "agents_total": "people simulated",
    "evacuation_target_s": "planning target for everyone out (seconds)",
    "breaks_plan": "breaks the plan",
    "before_fixes": "worst attack before fixes",
    "after_fixes": "worst attack after fixes",
    "fixes_kept": "fixes kept",
    "worst_attack": "worst attack",
    "stopped_reason": "why the session stopped",
    "inspired_by": "inspired by",
}


def plain_keys(obj: Any) -> Any:
    """Facts for the judge with plain-language keys (so prose never shows field names)."""
    if isinstance(obj, dict):
        return {PLAIN.get(k, k.replace("_", " ")): plain_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [plain_keys(v) for v in obj]
    return obj


@dataclass
class LiveSession:
    """In-memory state of a running session."""

    id: str
    project_id: str
    venue_version: int
    config: dict[str, Any]
    events: list[SessionEvent] = field(default_factory=list)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    stop_requested: bool = False
    finished: bool = False
    started: float = field(default_factory=time.monotonic)
    runs: int = 0
    budget: Budget | None = None
    final_venue: Venue | None = None
    measures: list[ScenarioEventIn] = field(default_factory=list)
    tested: list[str] = field(default_factory=list)
    cost: CostMeter = field(default_factory=CostMeter)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    branch_runs: dict[str, str] = field(default_factory=dict)  # node id -> run id
    inflight: set[str] = field(default_factory=set)  # node ids waiting for their run
    archive: dict[str, Any] | None = None  # latest failure-map snapshot (GET .../archive)


Maker = tuple[str, Callable[[], Awaitable[RunResult]]]


def _time_out(r: RunResult) -> float | None:
    """Time for 95% to get out: measured, else extrapolated from the exit flow at the end."""
    m = r.metrics
    if m.evac_time_p95_s is not None:
        return float(m.evac_time_p95_s)
    ext = (m.extra or {}).get("rset_extrapolated_s")
    return float(ext) if ext is not None else None


def made_worse(before: RunResult, after: RunResult, margin: float, danger: float) -> str:
    """What a change makes clearly worse under the same attack ("" when nothing does)."""
    worse: list[str] = []
    t0, t1 = _time_out(before), _time_out(after)
    if t0 is not None and t1 is not None and t1 > t0 * (1 + margin):
        worse.append("the time to get out")
    n0 = before.metrics.agents_not_evacuated or 0
    n1 = after.metrics.agents_not_evacuated or 0
    if n1 > n0:
        worse.append("the number of people left inside")
    d0 = before.metrics.peak_density_ppm2 or 0.0
    d1 = after.metrics.peak_density_ppm2 or 0.0
    if d1 >= danger and d1 > d0 * (1 + margin):
        worse.append("the peak density")
    return " and ".join(worse)


class Branches:
    """Independent simulations of one step (the screened attacks of a round, or the candidate
    fixes of one attack), started together and read back in their original order, so scoring,
    events and the summary follow the sequential order.

    The runner bounds how many sandboxes actually run at once. With `parallel` off each
    simulation starts only when it is read (the sequential behaviour). A stop request ends a
    wait at once. Leaving the block cancels every unfinished branch, its sandbox run
    included unless another caller still waits for that run, and closes the tree node of
    every branch that was started but not read.
    """

    def __init__(
        self,
        mgr: SessionManager,
        live: LiveSession,
        makers: list[Maker],
        parallel: bool,
        unread_note: str = "Not needed: an earlier change was kept.",
    ) -> None:
        self.mgr = mgr
        self.live = live
        self.makers = makers
        self.parallel = parallel
        self.unread_note = unread_note
        self.tasks: list[asyncio.Task[RunResult] | None] = [None] * len(makers)
        self.read: set[int] = set()

    def _start(self, i: int) -> asyncio.Task[RunResult]:
        task = self.tasks[i]
        if task is None:
            coro = self.makers[i][1]()
            task = self.tasks[i] = asyncio.ensure_future(coro)
        return task

    async def __aenter__(self) -> Branches:
        if self.parallel:
            for i in range(len(self.makers)):
                self._start(i)
        return self

    async def get(self, i: int) -> RunResult:
        """The result of branch i (raises what its simulation raised)."""
        task = self._start(i)
        self.read.add(i)
        stop = asyncio.ensure_future(self.live.stop_event.wait())
        try:
            await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
        if not task.done():
            raise StopSession("stopped by user")
        return task.result()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        live = self.live
        pending: list[asyncio.Task[RunResult]] = []
        # a branch whose wait was cut short by a stop was never used either
        self.read = {i for i in self.read if (t := self.tasks[i]) is not None and t.done()}
        for task in self.tasks:
            if task is None or task.done():
                continue
            # its wait ends; the sandbox run stops too unless another caller still waits for it
            task.cancel()
            pending.append(task)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for i, task in enumerate(self.tasks):
            if task is None or i in self.read:
                continue
            if not task.cancelled():
                task.exception()  # retrieved: an unread branch's error is not an error here
            node_id = self.makers[i][0]
            rid = live.branch_runs.get(node_id)
            if rid is None:
                continue  # never started, so never shown
            self.mgr.emit(
                live,
                "branch_node",
                {
                    "node_id": node_id,
                    "run_id": rid,
                    "status": "failed" if exc_type is not None else "rejected",
                    "skipped": True,
                    "note": "Stopped before this branch was used."
                    if exc_type is not None
                    else self.unread_note,
                },
            )


class SessionManager:
    """Starts, streams, stops and applies Red Team Night sessions."""

    def __init__(self, state: Any) -> None:
        self.st = state
        self.live: dict[str, LiveSession] = {}

    # ------------------------------------------------------------------ API
    def start(self, project_id: str, config: dict[str, Any] | None = None) -> RedTeamSession:
        """Create a session row and launch the loop in the background.

        Raises SessionConfigError for a setting of the wrong type or out of range."""
        cfg = session_config(self.st.settings, config)
        p = self.st.projects.get(project_id)
        sid = f"s_{uuid.uuid4().hex[:10]}"
        row = RedTeamSession(
            id=sid,
            project_id=project_id,
            venue_version=p.current_version,
            status="running",
            config=cfg,
        )
        with db_session() as db:
            db.add(row)
            db.commit()
            db.refresh(row)
        live = LiveSession(
            id=sid,
            project_id=project_id,
            venue_version=p.current_version,
            config=cfg,
            budget=Budget(max_tokens=int(cfg["max_tokens"])),
        )
        self.live[sid] = live
        live.task = asyncio.create_task(self._run(live))
        return row

    def get(self, sid: str) -> RedTeamSession | None:
        with db_session() as db:
            return db.get(RedTeamSession, sid)

    def list_sessions(self, project_id: str) -> list[RedTeamSession]:
        with db_session() as db:
            return list(
                db.exec(
                    select(RedTeamSession)
                    .where(RedTeamSession.project_id == project_id)
                    .order_by(col(RedTeamSession.created_at).desc())
                )
            )

    def recover_interrupted(self) -> int:
        """At server start: sessions left running by the previous process are stopped
        (returns how many)."""
        with db_session() as db:
            rows = list(db.exec(select(RedTeamSession).where(RedTeamSession.status == "running")))
            rows = [r for r in rows if r.id not in self.live]
            for row in rows:
                row.status = "stopped"
                row.error = "Stopped when the server restarted."
                row.finished_at = datetime.now(UTC)
                db.add(row)
            db.commit()
        if rows:
            log.warning("marked %d interrupted sessions as stopped", len(rows))
        return len(rows)

    def stop(self, sid: str) -> bool:
        live = self.live.get(sid)
        if live is None or live.finished:
            return False
        live.stop_requested = True
        live.stop_event.set()
        return True

    def stored_events(self, sid: str, after: int = 0) -> list[SessionEvent]:
        with db_session() as db:
            rows = list(
                db.exec(
                    select(SessionEventRow)
                    .where(SessionEventRow.session_id == sid, SessionEventRow.seq > after)
                    .order_by(col(SessionEventRow.seq))
                )
            )
        return [SessionEvent(seq=r.seq, type=r.type, ts=r.ts, payload=r.payload) for r in rows]

    async def stream(self, sid: str, after: int = 0) -> AsyncIterator[SessionEvent]:
        """Replay stored events after `after`, then follow live events until finished."""
        last = after
        for ev in self.stored_events(sid, after):
            last = ev.seq
            yield ev
        live = self.live.get(sid)
        while live is not None and not live.finished:
            async with live.cond:
                await live.cond.wait_for(
                    lambda: live.finished or (live.events and live.events[-1].seq > last)  # noqa: B023
                )
            for ev in [e for e in live.events if e.seq > last]:
                last = ev.seq
                yield ev

    # -------------------------------------------------------------- internals
    def emit(self, live: LiveSession, type_: str, payload: dict[str, Any]) -> None:
        ev = SessionEvent(seq=len(live.events) + 1, type=type_, payload=payload)
        live.events.append(ev)
        try:
            with db_session() as db:
                db.add(
                    SessionEventRow(
                        session_id=live.id, seq=ev.seq, type=ev.type, ts=ev.ts, payload=payload
                    )
                )
                db.commit()
        except Exception:
            log.exception("could not persist session event")
        try:
            self.st.host.pm.hook.on_session_event(session_id=live.id, event=ev)
        except Exception:
            log.exception("plugin hook on_session_event failed")
        asyncio.get_event_loop().create_task(self._notify(live))

    async def _notify(self, live: LiveSession) -> None:
        async with live.cond:
            live.cond.notify_all()

    def _status(
        self, live: LiveSession, phase: str, round_: int, message: str, status: str = "running"
    ) -> None:
        self.emit(
            live, "status", {"status": status, "phase": phase, "round": round_, "message": message}
        )

    def _check(self, live: LiveSession) -> None:
        cfg = live.config
        if live.stop_requested:
            raise StopSession("stopped by user")
        if live.runs >= int(cfg["max_runs"]):
            raise StopSession("budget: simulation runs")
        if time.monotonic() - live.started > float(cfg["max_wall_s"]):
            raise StopSession("budget: wall clock")

    async def _sim(
        self,
        live: LiveSession,
        venue: Venue,
        tier: int,
        label: str,
        node_id: str,
        parent: str | None,
        kind: str,
        attack: Attack | None = None,
        fix: Fix | None = None,
        extra: list[ScenarioEventIn] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> RunResult:
        self._check(live)
        st = self.st
        job = st.runs.build_job(
            venue,
            tier=tier,
            seed=int(live.config["seed"]),
            attack=attack,
            fix=fix,
            extra=extra,
            parent_run_id=parent,
        )
        job.request.extensions["events"] = job.events
        rid = job.request.run_id
        live.branch_runs[node_id] = rid
        node = {
            "node_id": node_id,
            "parent_id": parent,
            "kind": kind,
            "label": label,
            "run_id": rid,
            "status": "running",
            "attack_id": attack.attack_id if attack else None,
            "fix_id": fix.fix_id if fix else None,
            **(meta or {}),
        }
        self.emit(live, "branch_node", node)
        self.emit(
            live,
            "run_started",
            {
                "run_id": rid,
                "tier": tier,
                "label": label,
                "attack_id": node["attack_id"],
                "fix_id": node["fix_id"],
                "parent_run_id": parent,
            },
        )
        self.emit(
            live,
            "tool_call",
            {
                "tool": "run_sim",
                "args": {"tier": tier, "label": label},
                "summary": f"Tier {tier} simulation in the sandbox",
            },
        )
        live.runs += 1
        live.inflight.add(node_id)
        try:
            res: RunResult = await st.runs.run(
                job,
                project_id=live.project_id,
                venue_version=live.venue_version,
                session_id=live.id,
                label=label,
            )
        finally:
            live.inflight.discard(node_id)
        me = asyncio.current_task()
        if me is not None and me.cancelling():
            raise asyncio.CancelledError  # a cancelled branch: no fallback, no events
        live.cost.add_run(res)
        if res.status not in ("failed", "timeout", "cancelled"):
            return res
        # Never stall the session: show the instant estimate for this branch. The failed
        # simulation stays on record as it is (basis unknown); the estimate is a separate,
        # linked run that may rank attacks but can never confirm anything.
        fb: RunResult | None = st.runs.record_fallback(
            job,
            res,
            project_id=live.project_id,
            venue_version=live.venue_version,
            session_id=live.id,
            label=label,
        )
        if fb is None:
            return res
        live.cost.add_estimates()
        self.emit(
            live,
            "run_finished",
            {
                "run_id": res.run_id,
                "node_id": node_id,
                "status": res.status,
                "tier": res.tier,
                "metrics": headline(res),
                "provider": res.provider,
                "engine": res.engine,
                "basis": res.basis,
                "error": res.error,
                "fallback_run_id": fb.run_id,
                "cache_hit": bool(res.extensions.get("cache_hit")),
                "is_break": False,
                "break_reasons": [],
                "accepted": None,
            },
        )
        self.emit(
            live,
            "log",
            {
                "level": "warning",
                "message": f"{label}: simulation {res.status}; showing the instant estimate "
                f"(run {fb.run_id}) in its place",
            },
        )
        return fb

    async def _run(self, live: LiveSession) -> None:
        st = self.st
        cfg = live.config
        s = st.settings
        env = AgentEnv(
            llm=st.llm,
            budget=live.budget,
            project_id=live.project_id,
            session_id=live.id,
            emit=lambda t, p: self.emit(live, t, p),
            on_usage=lambda u: self._cost(live, u),
        )
        reason = "no new breaks"
        attacks_all: list[Attack] = []
        fixes_all: list[Fix] = []
        results: dict[str, RunResult] = {}
        accepted: list[str] = []
        scoreboard: list[dict[str, Any]] = []
        baseline: RunResult | None = None
        worst: tuple[float, Attack, RunResult] | None = None
        venue = st.projects.venue(live.project_id, live.venue_version)
        working = venue
        parallel = bool(cfg.get("parallel_branches", True))
        try:
            self._status(live, "baseline", 0, "Running the baseline")
            baseline = await self._sim(live, venue, 3, "Baseline", "baseline", None, "baseline")
            results[baseline.run_id] = baseline
            self._node_done(live, "baseline", baseline, None)
            incidents = self._incidents(working, baseline)
            self.emit(
                live,
                "tool_call",
                {
                    "tool": "incidents",
                    "args": {"n": len(incidents)},
                    "summary": f"{len(incidents)} similar real incidents found",
                },
            )
            seen: set[str] = set()
            archive = Archive(venue)
            rule = BreakRule(
                s.density_danger_ppm2, s.danger_min_duration_s, self._target(venue), s.safety_factor
            )
            self._archive_event(live, archive, 0, None)
            n_menu = int(cfg["attacks_per_round"])
            menu_kinds = set(KIND_IDS) - {"adaptive"}
            for rnd in range(1, int(cfg["max_rounds"]) + 1):
                self._check(live)
                # quality-diversity search: aim at empty cells of the failure map first, then
                # at the weakest ones (docs/RAINBOW.md)
                aim = archive.targets(n_menu, menu_kinds)
                aim_script = archive.targets(1, {"adaptive"})
                self._status(live, "red_team", rnd, "Red team is designing attacks")
                self.emit(
                    live,
                    "tool_call",
                    {
                        "tool": "failure_map",
                        "args": {"targets": [list(c) for c in aim + aim_script]},
                        "summary": "Aiming at "
                        + "; ".join(archive.describe(c).split(":")[0] for c in aim + aim_script),
                    },
                )
                proposed = await self._attacks(
                    env,
                    working,
                    baseline,
                    incidents,
                    n_menu,
                    seen,
                    len(attacks_all),
                    live.tested,
                    mode=str(cfg.get("agents", "model")),
                    archive=archive,
                    aim=aim + aim_script,
                )
                proposed = [
                    x.model_copy(update={"title": readable(x.title, working)}) for x in proposed
                ]
                if not proposed:
                    reason = "no new attacks"
                    break
                self._status(live, "screening", rnd, "Ranking attacks with the instant estimate")
                cells = {a.attack_id: archive.cell_of(a) for a in proposed}
                if cfg.get("agents") != "rules":
                    # how well the model follows the map (rule fills hit by construction)
                    landed = {
                        cells[a.attack_id]
                        for a in proposed
                        if a.extensions.get("generated_by") != "rules"
                    }
                    archive.aimed += len(aim) + len(aim_script)
                    archive.hit += sum(1 for c in aim + aim_script if c in landed)
                tier1: dict[str, RunResult] = {}
                menu: list[tuple[Attack, Cell | None, float]] = []
                scripted: list[Attack] = []
                for a in proposed:
                    if is_script_attack(a):
                        scripted.append(a)
                        continue
                    est = self._estimate(live, working, a, extra=live.measures)
                    tier1[a.attack_id] = est
                    menu.append((a, cells[a.attack_id], severity_score(est, rule)[0]))
                # the instant estimate cannot run code: at most one script, the model's first
                scripted.sort(key=lambda a: a.extensions.get("generated_by") == "rules")
                picked = [menu[i] for i in pick_candidates(menu, archive, n_menu, aim)]
                chosen = list(scripted[:1]) + [a for a, _, _ in picked]
                chosen_ids = {a.attack_id for a in chosen}
                # what was not simulated may be proposed again in a later round
                for a in proposed:
                    if a.attack_id not in chosen_ids:
                        seen.discard(signature([e.model_dump() for e in a.events]))
                left_out = [a.title for a in proposed if a.attack_id not in chosen_ids]
                if left_out:
                    self.emit(
                        live,
                        "log",
                        {
                            "level": "info",
                            "message": "Screened out by the instant estimate (not simulated): "
                            + "; ".join(left_out),
                        },
                    )
                # ids follow the simulated attacks, so they stay in sequence
                renamed = {
                    a.attack_id: f"A{len(attacks_all) + i + 1}" for i, a in enumerate(chosen)
                }
                ranked: list[tuple[float, Attack]] = []
                cell_by_id: dict[str, Cell | None] = {}
                for a in chosen:
                    cell = cells[a.attack_id]
                    old_id = a.attack_id
                    a = a.model_copy(update={"attack_id": renamed[old_id]})
                    cell_by_id[a.attack_id] = cell
                    where = {"cell": {"kind": cell[0], "where": cell[1]} if cell else None}
                    if is_script_attack(a):
                        ranked.append((math.inf, a))
                        self.emit(
                            live,
                            "attack_card",
                            {
                                "round": rnd,
                                "attack": a.model_dump(mode="json"),
                                "tier1": {},
                                "screening": SCRIPT_SCREENING,
                                **where,
                            },
                        )
                        self.emit(
                            live,
                            "log",
                            {
                                "level": "info",
                                "message": f"“{a.title}” is an AI-written scenario; the instant "
                                "estimate cannot run its code, so it goes straight to a quick "
                                "simulation.",
                            },
                        )
                        continue
                    est = tier1[old_id]
                    ranked.append((severity(est), a))
                    self.emit(
                        live,
                        "attack_card",
                        {
                            "round": rnd,
                            "attack": a.model_dump(mode="json"),
                            "tier1": headline(est),
                            **where,
                        },
                    )
                ranked.sort(key=lambda x: -x[0])
                attacks_all.extend(a for _, a in ranked)
                live.tested = [
                    f"{a.title} ({', '.join(e.type for e in a.events)})" for a in attacks_all
                ]
                self._status(live, "simulating", rnd, f"Simulating {len(ranked)} attacks")
                breaks: list[tuple[float, Attack, RunResult]] = []
                attack_sims: list[Maker] = [
                    (
                        f"atk:{a.attack_id}",
                        partial(
                            self._sim,
                            live,
                            working,
                            2,
                            a.title,
                            f"atk:{a.attack_id}",
                            "baseline",
                            "attack",
                            attack=a,
                            extra=list(live.measures),
                        ),
                    )
                    for _, a in ranked
                ]
                async with Branches(self, live, attack_sims, parallel) as screened:
                    for i, (_, a) in enumerate(ranked):
                        r = await screened.get(i)
                        results[r.run_id] = r
                        reasons = break_reasons(
                            r,
                            s.density_danger_ppm2,
                            s.danger_min_duration_s,
                            self._target(working),
                            s.safety_factor,
                        )
                        self._node_done(live, f"atk:{a.attack_id}", r, reasons)
                        if r.status not in ("failed", "timeout", "cancelled"):
                            score, parts = severity_score(r, rule)
                            ins = archive.insert(
                                Elite(
                                    attack_id=a.attack_id,
                                    title=a.title,
                                    run_id=r.run_id,
                                    severity=score,
                                    is_break=bool(reasons),
                                    round=rnd,
                                    metrics=headline(r),
                                    parts=parts,
                                    basis=r.basis,
                                    generated_by=str(a.extensions.get("generated_by", "ai")),
                                ),
                                cell_by_id.get(a.attack_id),
                            )
                            self._archive_event(live, archive, rnd, ins, a.attack_id, score)
                        if reasons:
                            breaks.append((severity(r), a, r))
                            if worst is None or severity(r) > worst[0]:
                                worst = (severity(r), a, r)
                point = archive.end_round(rnd)
                scoreboard.append(
                    {
                        "round": rnd,
                        "breaks": len(breaks),
                        "attacks": len(ranked),
                        "coverage": point["coverage"],
                        "qd_score": point["qd_score"],
                    }
                )
                self._archive_event(live, archive, rnd, None)
                self.emit(
                    live,
                    "score",
                    {
                        "round": rnd,
                        "breaks": len(breaks),
                        "attacks_tested": len(ranked),
                        "fixes_accepted": len(accepted),
                        "scoreboard": scoreboard,
                    },
                )
                if not breaks:
                    if not archive.empty():
                        reason = "no new breaks"
                        break
                    continue  # nothing to fix, but the map still has gaps to search
                # the worst elites of the map first, then other breaks of this round
                breaks.sort(key=lambda x: (not archive.contains(x[1].attack_id), -x[0]))
                accepted_before_round = len(accepted)
                for sev, a, r in breaks[: int(cfg["fix_targets"])]:
                    self._check(live)
                    if len(accepted) > accepted_before_round:
                        current = f"atk:{a.attack_id}:current:{len(accepted)}"
                        r = await self._sim(
                            live,
                            working,
                            2,
                            a.title,
                            current,
                            None,
                            "attack",
                            attack=a,
                            extra=live.measures,
                        )
                        results[r.run_id] = r
                        self._node_done(
                            live,
                            current,
                            r,
                            break_reasons(
                                r,
                                s.density_danger_ppm2,
                                s.danger_min_duration_s,
                                self._target(working),
                                s.safety_factor,
                            ),
                        )
                        sev = severity(r)
                    self._status(live, "blue_team", rnd, f"Blue team is fixing “{a.title}”")
                    fixes = await self._fixes(
                        env,
                        working,
                        a,
                        r,
                        int(cfg["fixes_per_attack"]),
                        f"F{len(fixes_all) + 1}_",
                        mode=str(cfg.get("agents", "model")),
                    )
                    fixes = [
                        fx.model_copy(update={"title": readable(fx.title, working)}) for fx in fixes
                    ]
                    # every candidate is checked against the same plan (it changes only when
                    # a fix is kept, which ends this attack), so the checks and the
                    # simulations of all candidates can happen up front
                    checked: list[tuple[Fix, Venue | None, Exception | None]] = []
                    for fx in fixes:
                        try:
                            candidate = apply_fix_bundle(working, fx, st.registry)
                            validate_operational(
                                candidate, [*live.measures, *fx.operational], st.registry
                            )
                            checked.append((fx, candidate, None))
                        except (PlanError, PatchError, ValueError) as exc:
                            checked.append((fx, None, exc))
                    fix_sims: list[Maker] = [
                        (
                            f"fix:{fx.fix_id}",
                            partial(
                                self._sim,
                                live,
                                working,
                                2,
                                fx.title,
                                f"fix:{fx.fix_id}",
                                f"atk:{a.attack_id}",
                                "fix",
                                attack=a,
                                fix=fx,
                                extra=list(live.measures),
                            ),
                        )
                        for fx, cand, _ in checked
                        if cand is not None
                    ]
                    async with Branches(self, live, fix_sims, parallel) as tried:
                        k = -1
                        for fx, cand, problem in checked:
                            if cand is None:
                                self.emit(
                                    live,
                                    "log",
                                    {
                                        "level": "warning",
                                        "message": f"Rejected complete fix bundle: {problem}",
                                    },
                                )
                                continue
                            candidate, k = cand, k + 1
                            fixes_all.append(fx)
                            self.emit(
                                live,
                                "fix_card",
                                {
                                    "round": rnd,
                                    "fix": fx.model_dump(mode="json"),
                                    "attack_id": a.attack_id,
                                },
                            )
                            fr = await tried.get(k)
                            results[fr.run_id] = fr
                            gain = (sev - severity(fr)) / sev if sev > 0 else 0.0
                            fr_reasons = break_reasons(
                                fr,
                                s.density_danger_ppm2,
                                s.danger_min_duration_s,
                                self._target(working),
                                s.safety_factor,
                            )
                            # kept when it removes the break, or improves the result by
                            # FIX_MIN_GAIN, and never when it makes the plan worse without the
                            # attack. Both sides must be simulations (or both previews): an
                            # instant estimate shown in place of a failed simulation is never
                            # enough to keep a change.
                            helps = (not fr_reasons and gain > 0) or gain >= float(s.fix_min_gain)
                            evidence_ok = comparable(r, fr)
                            # a better composite score is not enough when an outcome people
                            # read first (time out, people inside, peak density) gets worse
                            worse = made_worse(
                                r, fr, float(s.fix_min_gain), float(s.density_danger_ppm2)
                            )
                            if helps and worse:
                                self.emit(
                                    live,
                                    "log",
                                    {
                                        "level": "info",
                                        "message": f"{fx.title}: not kept, because it makes "
                                        f"{worse} worse under this attack",
                                    },
                                )
                            ok = (
                                helps
                                and not worse
                                and evidence_ok
                                and not self._hurts_baseline(working, fx, baseline, live)
                            )
                            if helps and not evidence_ok:
                                self.emit(
                                    live,
                                    "log",
                                    {
                                        "level": "warning",
                                        "message": f"{fx.title}: not kept, because there is no "
                                        "finished simulation to compare (only an instant "
                                        "estimate)",
                                    },
                                )
                            self._node_done(
                                live,
                                f"fix:{fx.fix_id}",
                                fr,
                                fr_reasons,
                                accepted=ok,
                                gain=round(gain, 3),
                            )
                            audit_decision(
                                env,
                                "orchestrator",
                                "fix accepted" if ok else "fix rejected",
                                {
                                    "fix_id": fx.fix_id,
                                    "gain": round(gain, 3),
                                    "comparable_evidence": evidence_ok,
                                },
                            )
                            if ok:
                                accepted.append(fx.fix_id)
                                working = candidate
                                archive.learn(working)
                                live.measures.extend(fx.operational)
                                fixed_cell = archive.mark_fixed(
                                    a.attack_id, fx.fix_id, severity_score(fr, rule)[0], fr.run_id
                                )
                                if fixed_cell is not None:
                                    self._archive_event(
                                        live,
                                        archive,
                                        rnd,
                                        Insert("fixed", fixed_cell),
                                        a.attack_id,
                                        severity_score(fr, rule)[0],
                                        fix_id=fx.fix_id,
                                    )
                                self.emit(
                                    live,
                                    "score",
                                    {
                                        "round": rnd,
                                        "breaks": len(breaks),
                                        "attacks_tested": len(ranked),
                                        "fixes_accepted": len(accepted),
                                        "scoreboard": scoreboard,
                                    },
                                )
                                break  # one accepted fix per attack is enough
            else:
                reason = "all rounds done"
        except StopSession as exc:
            reason = str(exc)
        except BudgetExceeded:
            reason = "budget: tokens"
        except Exception as exc:  # the session must always finish with what exists
            log.exception("session %s failed", live.id)
            self.emit(live, "log", {"level": "error", "message": f"Session error: {exc}"})
            reason = f"error: {type(exc).__name__}"
        live.final_venue = working
        try:
            await self._finish(
                live,
                env,
                venue,
                working,
                baseline,
                worst,
                attacks_all,
                fixes_all,
                results,
                accepted,
                scoreboard,
                reason,
            )
        except Exception as exc:  # the row must never stay "running"
            log.exception("session %s could not finish", live.id)
            self._fail(live, exc)
        finally:
            live.finished = True
            await self._notify(live)

    def _archive_event(
        self,
        live: LiveSession,
        archive: Archive,
        rnd: int,
        change: Insert | None,
        attack_id: str | None = None,
        score: float | None = None,
        fix_id: str | None = None,
    ) -> None:
        """Stream the failure map after a change (and keep it for GET .../archive)."""
        snap = archive.snapshot()
        live.archive = snap
        payload: dict[str, Any] = {"round": rnd, "change": None, "archive": snap}
        if change is not None:
            payload["change"] = {
                "outcome": change.outcome,
                "kind": change.cell[0] if change.cell else None,
                "where": change.cell[1] if change.cell else None,
                "attack_id": attack_id,
                "severity": score,
                "replaced_attack_id": change.replaced,
                "fix_id": fix_id,
            }
        self.emit(live, "archive", payload)

    def _fail(self, live: LiveSession, exc: Exception) -> None:
        """Mark a session that could not write its summary as failed (status, error, end)."""
        message = f"{type(exc).__name__}: {exc}"[:500]
        b = live.budget
        try:
            with db_session() as db:
                row = db.get(RedTeamSession, live.id)
                if row is not None:
                    row.status = "failed"
                    row.error = message
                    row.tokens = b.used if b else 0
                    row.cost_usd = round(b.cost_usd, 6) if b else 0.0
                    row.finished_at = datetime.now(UTC)
                    db.add(row)
                    db.commit()
        except Exception:
            log.exception("could not mark session %s failed", live.id)
        self._status(live, "done", 0, f"The session failed: {message}", status="failed")

    def _target(self, venue: Venue) -> float:
        s = self.st.settings
        return float(s.target_evac_indoor_s if venue.mode == "indoor" else s.target_evac_outdoor_s)

    def _estimate(
        self,
        live: LiveSession,
        venue: Venue,
        attack: Attack | None = None,
        fix: Fix | None = None,
        extra: list[ScenarioEventIn] | None = None,
    ) -> RunResult:
        """An instant estimate the session uses as evidence (counted in its cost record)."""
        live.cost.add_estimates()
        est: RunResult = self.st.runs.estimate(venue, attack, fix, extra=extra)
        return est

    def _cost(self, live: LiveSession, u: Any) -> None:
        self.st.usage.add(u)
        live.cost.add_usage(u)
        b = live.budget
        if b is not None:
            self.emit(
                live,
                "cost",
                {
                    "tokens_total": b.used,
                    "cost_usd": round(b.cost_usd, 6),
                    "by_role": b.by_role,
                    "budget_tokens": b.max_tokens,
                },
            )

    def _incidents(self, venue: Venue, baseline: RunResult | None) -> list[IncidentRecord]:
        srcs = self.st.registry.all("IncidentSource")
        if not srcs:
            return []
        q = incident_query(venue, venue_features(venue, baseline))
        return srcs[0].search(q, 8)  # type: ignore[no-any-return]

    async def _attacks(
        self,
        env: AgentEnv,
        venue: Venue,
        baseline: RunResult | None,
        incidents: list[IncidentRecord],
        n: int,
        seen: set[str],
        offset: int,
        tested: list[str],
        mode: str = "model",
        archive: Archive | None = None,
        aim: list[Cell] | None = None,
    ) -> list[Attack]:
        """Candidate attacks for one round. With a failure map, the model is asked to fill the
        `aim` cells; the rules fill the cells it missed (hybrid) or all of them (rules)."""
        aim = aim or []
        if mode == "rules":
            return self._rule_fill(venue, baseline, incidents, n, seen, offset, archive, aim)
        menu_aim = [c for c in aim if c[0] != "adaptive"]
        script_aim = [c for c in aim if c[0] == "adaptive"]
        try:
            out = await red_team(
                env,
                self.st.registry,
                venue,
                baseline,
                incidents,
                n,
                seen,
                offset,
                tested=tested,
                aim=[archive.describe(c) for c in menu_aim] if archive else None,
                aim_script=archive.describe(script_aim[0]) if archive and script_aim else None,
            )
        except (AgentUnavailable, LLMError) as exc:  # LLMError: e.g. a replay-cache miss
            if env.emit:
                env.emit(
                    "log",
                    {
                        "level": "warning",
                        "message": f"Red team model unavailable ({exc}); using rule-based attacks",
                    },
                )
            if mode == "model":  # the AI designs the attacks; the rules stand in only now
                return self._rule_fill(venue, baseline, incidents, n, seen, offset, archive, aim)
            out = []
        if mode == "model":
            return out
        if not out:
            out = self._rule_fill(venue, baseline, incidents, n, seen, offset, archive, aim)
            if out and env.emit:
                env.emit("log", {"level": "info", "message": "Rule-based attacks were added."})
            return out
        if archive is not None and aim:
            # cells of the map the model aimed at but missed: the rules fill them, and the
            # instant estimate decides which candidates are simulated
            landed = {archive.cell_of(a) for a in out}
            missed = [c for c in aim if c not in landed]
            if not any(is_script_attack(a) for a in out) and not any(
                c[0] == "adaptive" for c in missed
            ):
                missed += [c for c in archive.targets(1, {"adaptive"}) if c not in missed]
            fills = rule_attacks_for_cells(
                venue,
                baseline,
                incidents,
                [(k, archive.region(w)) for k, w in missed],
                seen,
                offset + len(out),
            )
            if fills and env.emit:
                env.emit(
                    "log",
                    {
                        "level": "info",
                        "message": "Rule-based attacks for gaps in the failure map the AI "
                        "missed: " + "; ".join(a.title for a in fills),
                    },
                )
                if not any(is_script_attack(a) for a in out) and any(
                    is_script_attack(a) for a in fills
                ):
                    env.emit(
                        "log",
                        {
                            "level": "info",
                            "message": "The AI wrote no scenario script this round, so the "
                            "built-in example script was added.",
                        },
                    )
            return out + fills
        if not any(is_script_attack(a) for a in out):
            # every test includes a scenario written as code; the built-in example stands in
            extra = rule_attacks(venue, baseline, incidents, n, set(seen), offset + len(out))
            example = [a for a in extra if is_script_attack(a)][:1]
            if example:
                # the next id in sequence (its id from `extra` skips ahead), and remembered so
                # later rounds neither repeat it nor reuse its id
                ex = example[0].model_copy(update={"attack_id": f"A{offset + len(out) + 1}"})
                seen.add(signature([e.model_dump() for e in ex.events]))
                out.append(ex)
                if env.emit:
                    env.emit(
                        "log",
                        {
                            "level": "info",
                            "message": "The AI wrote no scenario script this round, so the "
                            "built-in example script was added.",
                        },
                    )
        return out

    def _rule_fill(
        self,
        venue: Venue,
        baseline: RunResult | None,
        incidents: list[IncidentRecord],
        n: int,
        seen: set[str],
        offset: int,
        archive: Archive | None,
        aim: list[Cell],
    ) -> list[Attack]:
        """Rule-based attacks for the aimed cells, topped up to n menu attacks by the
        standard rule set (one scenario script at most)."""
        out: list[Attack] = []
        if archive is not None and aim:
            out = rule_attacks_for_cells(
                venue, baseline, incidents, [(k, archive.region(w)) for k, w in aim], seen, offset
            )
        menu = [a for a in out if not is_script_attack(a)]
        if len(menu) < n:
            more = rule_attacks(venue, baseline, incidents, n - len(menu), seen, offset + len(out))
            has_script = any(is_script_attack(a) for a in out)
            for a in more:
                if is_script_attack(a) and has_script:
                    seen.discard(signature([e.model_dump() for e in a.events]))
                    continue
                out.append(a.model_copy(update={"attack_id": f"A{offset + len(out) + 1}"}))
        return out

    async def _fixes(
        self,
        env: AgentEnv,
        venue: Venue,
        attack: Attack,
        result: RunResult,
        n: int,
        prefix: str,
        mode: str = "model",
    ) -> list[Fix]:
        if mode == "rules":
            return rule_fixes(self.st.registry, venue, attack, result, n, prefix + "R")
        try:
            out = await blue_team(env, self.st.registry, venue, attack, result, n, prefix)
        except (AgentUnavailable, LLMError) as exc:
            if mode == "model":  # the AI designs the fixes; standard ones stand in only now
                if env.emit:
                    env.emit(
                        "log",
                        {
                            "level": "warning",
                            "message": f"Blue team model unavailable ({exc}); using standard fixes",
                        },
                    )
                return rule_fixes(self.st.registry, venue, attack, result, n, prefix + "R")
            out = []
        if mode == "model":
            return out
        # Standard engineering responses compete with the AI's ideas; the simulation decides.
        rules = rule_fixes(self.st.registry, venue, attack, result, n + 2, prefix + "R")
        kinds = {
            e.type for f in out for e in [*f.operational, *(a.event for a in f.actions if a.event)]
        } | {o.op for f in out for o in f.patch.ops}
        extra = [
            f
            for f in rules
            if (
                (
                    any(
                        e.type == "one_way"
                        for e in [*f.operational, *(a.event for a in f.actions if a.event)]
                    )
                    and "one_way" not in kinds
                )
                or (any(o.op == "add_exit" for o in f.patch.ops) and "add_exit" not in kinds)
                # buildings: a wider stairwell and a phased evacuation (several zones held)
                or (any(o.op == "widen_stair" for o in f.patch.ops) and "widen_stair" not in kinds)
                or (
                    sum(e.type == "staggered_release" for e in f.operational) > 1
                    and "staggered_release" not in kinds
                )
            )
        ]
        if not out:
            extra = rules[:n]
        if extra and env.emit:
            env.emit(
                "log",
                {
                    "level": "info",
                    "message": "Added standard responses: " + "; ".join(f.title for f in extra),
                },
            )
        return out + extra

    def _hurts_baseline(
        self, venue: Venue, fix: Fix, baseline: RunResult | None, live: LiveSession
    ) -> bool:
        """A fix must not make the plan worse without the attack (instant estimate)."""
        if baseline is None:
            return False
        before = self._estimate(live, venue, None, extra=live.measures)
        after = self._estimate(live, venue, None, fix, extra=live.measures)
        return severity(after) > severity(before) * 1.05 + 1.0

    def _apply_ops(self, venue: Venue, ops: list[dict[str, Any]], live: LiveSession) -> Venue:
        if not ops:
            return venue
        return apply_patch(venue, VenuePatch.model_validate({"ops": ops}), self.st.registry).venue

    def _node_done(
        self,
        live: LiveSession,
        node_id: str,
        r: RunResult,
        reasons: list[str] | None,
        accepted: bool | None = None,
        gain: float | None = None,
    ) -> None:
        status = (
            "failed"
            if r.status in ("failed", "timeout", "cancelled")
            else "rejected"
            if accepted is False
            else "break"
            if reasons
            else "ok"
        )
        # what the node's numbers are based on; a fallback names the failed run it replaces
        evidence: dict[str, Any] = {"basis": r.basis}
        if fallback_for(r):
            evidence["fallback_for"] = fallback_for(r)
        payload: dict[str, Any] = {
            "node_id": node_id,
            "run_id": r.run_id,
            "status": status,
            "metrics": headline(r),
            "tier": r.tier,
            **evidence,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        if gain is not None:
            payload["gain"] = gain
        self.emit(live, "branch_node", payload)
        self.emit(
            live,
            "run_finished",
            {
                "run_id": r.run_id,
                "node_id": node_id,
                "status": r.status,
                "tier": r.tier,
                "metrics": headline(r),
                "provider": r.provider,
                "engine": r.engine,
                **evidence,
                "cache_hit": bool(r.extensions.get("cache_hit")),
                "is_break": bool(reasons),
                "break_reasons": reasons or [],
                "accepted": accepted,
            },
        )

    async def _finish(
        self,
        live: LiveSession,
        env: AgentEnv,
        venue: Venue,
        working: Venue,
        baseline: RunResult | None,
        worst: tuple[float, Attack, RunResult] | None,
        attacks: list[Attack],
        fixes: list[Fix],
        results: dict[str, RunResult],
        accepted: list[str],
        scoreboard: list[dict[str, Any]],
        reason: str,
    ) -> None:
        s = self.st.settings
        before: RunResult | None = worst[2] if worst else baseline
        after: RunResult | None = None
        final_run_id: str | None = None
        stopped = reason.startswith("stopped") or reason.startswith("budget")
        # Session status (did it finish?) and evaluation status (what do the results show?)
        # are separate; only the confirmation runs under the worst attack can confirm a plan.
        confirming = False
        confirm_before: RunResult | None = None
        confirm_after: RunResult | None = None
        confirm_error: str | None = None
        try:
            if worst and accepted and live.config.get("confirm_tier3") and not stopped:
                self._status(live, "confirming", len(scoreboard), "Confirming the best plan")
                a = worst[1]
                kept = [f for f in fixes if f.fix_id in accepted]
                live.stop_requested = False
                live.stop_event.clear()
                live.config["max_runs"] = int(live.config["max_runs"]) + 2
                self._check(live)  # the wall clock may already be spent
                confirming = True
                confirm_before = before = await self._sim(
                    live,
                    venue,
                    3,
                    f"Before fixes · {a.title}",
                    "final:before",
                    "baseline",
                    "final",
                    attack=a,
                )
                results[before.run_id] = before
                self._node_done(
                    live,
                    "final:before",
                    before,
                    break_reasons(
                        before,
                        s.density_danger_ppm2,
                        s.danger_min_duration_s,
                        self._target(venue),
                        s.safety_factor,
                    ),
                )
                confirm_after = after = await self._sim(
                    live,
                    working,
                    3,
                    f"After fixes · {a.title}",
                    "final:after",
                    "final:before",
                    "final",
                    attack=a,
                    extra=live.measures,
                    meta={"fixes": [f.fix_id for f in kept]},
                )
                results[after.run_id] = after
                # the simulation attempted, even when an estimate is shown in its place
                final_run_id = attempt_id(after)
                self._node_done(
                    live,
                    "final:after",
                    after,
                    break_reasons(
                        after,
                        s.density_danger_ppm2,
                        s.danger_min_duration_s,
                        self._target(working),
                        s.safety_factor,
                    ),
                )
        except Exception as exc:
            confirm_error = str(exc) or type(exc).__name__
            self.emit(live, "log", {"level": "warning", "message": f"Confirmation skipped: {exc}"})
        evaluation = evaluate(
            confirm_before if confirming else before,
            confirm_after,
            confirmation_ran=confirming,
            kept=len(accepted),
            had_breaks=worst is not None,
            stopped_reason=reason,
            baseline=baseline,
            error=confirm_error,
        )
        # external hazards only (wind, or a time the user set); attack events are scenario
        # details, not the event's hazard deadline
        scenario = (
            "the worst red-team attack" + (" with the kept fixes" if after else "")
            if worst
            else "the baseline"
        )
        countdown = await self._countdown(live, working, None, after or before, scenario)
        if countdown is not None:
            self.emit(live, "countdown", {"countdown": countdown.model_dump()})
        facts = {
            "venue": working.name,
            "people": working.total_people(),
            "baseline": headline(baseline),
            "attacks": [self._attack_fact(a, results, self._target(venue)) for a in attacks],
            "evacuation_target_s": self._target(venue),
            "safety_factor": s.safety_factor,
            "scoreboard": scoreboard,
            "fixes_kept": [f.title for f in fixes if f.fix_id in accepted],
            "worst_attack": worst[1].title if worst else None,
            "before_fixes": headline(before),
            "after_fixes": headline(after),
            "countdown": countdown.model_dump() if countdown else None,
            "stopped_reason": reason,
            # wording follows the evidence: what the results are, whether before and after
            # may be compared, and the evaluation status with its reasons
            "evidence_basis": evidence_sentence(after or before or baseline),
            "comparable": comparable(before, after),
            "evaluation": evaluation_sentence(evaluation),
        }
        template = self._template(facts)
        facts_for_judge = plain_keys(facts)
        recs: list[str]
        if live.config.get("judge", True) is False:
            # a session that must not call the model (rule-based real cases): the computed
            # summary stands as written
            text, recs, checked = template, [], False
        else:
            self._status(live, "judging", len(scoreboard), "Judge is checking every number")
            try:
                text, recs, checked = await judge(
                    env, facts_for_judge, template, computed_summary=True
                )
            except (AgentUnavailable, BudgetExceeded, LLMError):
                text, recs, checked = template, [], False
        summary = {
            "baseline_run_id": baseline.run_id if baseline else None,
            "final_run_id": final_run_id,
            "scoreboard": scoreboard,
            "accepted_fixes": accepted,
            "attacks": [a.model_dump(mode="json") for a in attacks],
            "fixes": [f.model_dump(mode="json") for f in fixes],
            "worst_attack_id": worst[1].attack_id if worst else None,
            "before": headline(before),
            "after": headline(after) if after else None,
            "judge_text": text,
            "recommendations": recs,
            "numbers_checked": checked,
            "countdown": countdown.model_dump() if countdown else None,
            "stopped_reason": reason,
            "final_venue": working.model_dump(mode="json"),
            "measures": [m.model_dump() for m in live.measures],
            "evaluation": evaluation,
            # the failure map (quality-diversity archive) the red team searched
            "archive": live.archive,
            # measured after the judge, so every model call of the session is included
            "cost": live.cost.record(wall_s=time.monotonic() - live.started),
        }
        status = "stopped" if reason == "stopped by user" else "finished"
        b = live.budget
        with db_session() as db:
            row = db.get(RedTeamSession, live.id)
            if row is not None:
                row.status = status
                row.summary = summary
                row.tokens = b.used if b else 0
                row.cost_usd = round(b.cost_usd, 6) if b else 0.0
                row.finished_at = datetime.now(UTC)
                db.add(row)
                db.commit()
        self._status(live, "done", len(scoreboard), f"Finished: {reason}", status=status)
        try:
            self.st.host.pm.hook.on_session_finished(session_id=live.id, summary=summary)
        except Exception:
            log.exception("plugin hook on_session_finished failed")

    def _attack_fact(
        self, a: Attack, results: dict[str, RunResult], target: float
    ) -> dict[str, Any]:
        """What the judge sees about one attack (computed numbers, clearly named)."""
        s = self.st.settings
        r = next(
            (
                x
                for x in results.values()
                if x.attack_id == a.attack_id and x.fix_id is None and x.tier == 2
            ),
            None,
        )
        fact: dict[str, Any] = {
            "title": a.title,
            "inspired_by": a.inspired_by.incident,
            "year": a.inspired_by.year,
        }
        if r is not None:
            est = evac_estimate(r)
            fact.update(
                {
                    "evacuation_time_95_s": round(est) if est is not None else None,
                    "peak_density_people_per_m2": r.metrics.peak_density_ppm2,
                    "seconds_above_danger_density": r.metrics.time_above_danger_s,
                    "breaks_plan": bool(
                        break_reasons(
                            r,
                            s.density_danger_ppm2,
                            s.danger_min_duration_s,
                            target,
                            s.safety_factor,
                        )
                    ),
                }
            )
        return fact

    @staticmethod
    def _template(f: dict[str, Any]) -> str:
        """Outcome summary built only from recorded facts, regardless of model fluency."""
        parts = [
            f"Red team tested {sum(r['attacks'] for r in f['scoreboard'])} attacks on "
            f"{f['venue']} ({f['people']:,} people)."
        ]
        if f.get("evidence_basis"):
            parts.insert(0, f["evidence_basis"])
        if f["scoreboard"]:
            parts.append(
                "Breaks per round: " + ", ".join(str(r["breaks"]) for r in f["scoreboard"]) + "."
            )
        if f["worst_attack"]:
            parts.append(f"The worst scenario was “{f['worst_attack']}”.")
        if f["fixes_kept"]:
            parts.append("Fixes kept: " + "; ".join(f["fixes_kept"]) + ".")
        else:
            parts.append("No fixes were accepted.")
        b, a = f["before_fixes"], f["after_fixes"]
        # an estimate standing in for a failed simulation is not compared with a simulation
        if b and a and f["fixes_kept"] and f.get("comparable", True):
            parts.append(
                f"Under that scenario, peak density went from {b['peak_density_ppm2']} to "
                f"{a['peak_density_ppm2']} people per m² and time above danger from "
                f"{b['time_above_danger_s']:.0f} s to {a['time_above_danger_s']:.0f} s."
            )
        if f.get("evaluation"):
            parts.append(f["evaluation"])
        parts.append("Planning aid, not a safety certification.")
        return " ".join(parts)

    async def _countdown(
        self,
        live: LiveSession,
        venue: Venue,
        attack: Attack | None,
        run: RunResult | None,
        scenario: str = "the worst red-team attack",
    ) -> Countdown | None:
        st = self.st
        s = st.settings
        rset = None
        if run is not None:
            rset = run.metrics.evac_time_p95_s or run.metrics.extra.get("rset_extrapolated_s")

        async def forecast(lat: float, lon: float, day: str, tz: str) -> dict[str, Any]:
            from datetime import date

            out: dict[str, Any] = await st.weather.hourly_gusts(
                lat, lon, tz, date.fromisoformat(day)
            )
            return out

        ctx = HazardContext(venue=venue, attack=attack, get_forecast=forecast)
        hazards: list[HazardResult] = []
        for src in st.registry.all("HazardSource"):
            if venue.mode not in src.modes:
                continue
            try:
                h = await src.evaluate(ctx)
            except Exception as exc:
                # one broken hazard (no forecast, a plugin bug) must not stop the countdown, but
                # a countdown that silently left the wind out would look safer than it is
                name = getattr(src, "id", None) or type(src).__name__
                log.warning("hazard source %s failed: %s", name, exc, exc_info=True)
                self.emit(
                    live,
                    "log",
                    {
                        "level": "warning",
                        "message": f"The {name} hazard could not be evaluated ({exc}); the "
                        "countdown leaves it out.",
                    },
                )
                continue
            if h is not None:
                hazards.append(h)
        chosen = choose_hazard(hazards)
        # the wording follows the run's basis; it never claims more than that run shows
        source = f"{scenario} ({describe_run(run)})" if run else ""
        return compute_countdown(
            chosen,
            rset,
            s.pre_movement_s,
            s.safety_factor,
            source,
        )

    def apply_final(self, sid: str, fix_ids: list[str] | None = None) -> Any:
        """Save the session's fixed venue, or the chosen kept fixes, as a new project version.

        `fix_ids` (default: every kept fix) must be a non-empty subset of the kept fixes. All
        of them use the venue the session tested together; a subset is rebuilt from the
        tested venue with only those fix bundles, validated as the session validated them,
        and is recorded as not tested together. Refused when the complete plan changed after
        the session started: replacing it would silently discard those edits. Organizer
        annotations come from the current version; objects the fixes added are marked as
        proposed construction. The session summary keeps an `applied` record per version.
        """
        row = self.get(sid)
        if row is None or not row.summary or not row.summary.get("final_venue"):
            raise ValueError("This session has no fixed plan to apply.")
        summary: dict[str, Any] = dict(row.summary)
        accepted = [str(f) for f in summary.get("accepted_fixes") or []]
        if not accepted:
            # saving would only add a version identical to the current one
            raise ValueError("This session kept no fixes, so there is nothing to apply.")
        chosen = self._chosen(accepted, fix_ids)
        projects = self.st.projects
        tested = projects.version(row.project_id, row.venue_version)
        current = projects.version(row.project_id)
        original = Venue.model_validate(tested.venue)
        present = Venue.model_validate(current.venue)
        if plan_hash(present) != plan_hash(original):
            raise StalePlan(
                "The plan changed after this test, so its fixes no longer match. "
                "Test the current plan again before accepting changes."
            )
        together = chosen == accepted
        if together:
            fixed = Venue.model_validate(summary["final_venue"])
            measures = [ScenarioEventIn.model_validate(e) for e in summary.get("measures", [])]
        else:
            fixed, measures = self._rebuild(original, summary, chosen)
        v = carry_annotations(present, fixed)
        v = append_legacy_measures(v, measures, self.st.registry)
        titles = {
            str(f.get("fix_id")): str(f.get("title") or "")
            for f in summary.get("fixes") or []
            if isinstance(f, dict)
        }
        named = "; ".join(f"{f} ({titles[f]})" if titles.get(f) else f for f in chosen)
        message = (
            f"Applied red-team plan ({len(chosen)} fixes): {named}"
            if together
            else f"Applied {len(chosen)} of {len(accepted)} red-team fixes: {named}. "
            + NOT_TESTED_TOGETHER
        )
        saved = projects.replace_venue(
            row.project_id,
            v,
            message[:1000],
            author="agent",
            expected_version=current.version,
        )
        self._record_applied(
            sid,
            {
                "version": saved.version,
                "plan_hash": plan_hash(Venue.model_validate(saved.venue)),
                "fix_ids": chosen,
                "tested_together": together,
                "note": None if together else NOT_TESTED_TOGETHER,
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        )
        return saved

    @staticmethod
    def _chosen(accepted: list[str], fix_ids: list[str] | None) -> list[str]:
        """The chosen kept fixes in the order the session kept them (all when not given)."""
        if fix_ids is None:
            return list(accepted)
        wanted = list(dict.fromkeys(str(f).strip() for f in fix_ids if str(f).strip()))
        if not wanted:
            raise FixSelectionError("Choose at least one change to accept.")
        unknown = [f for f in wanted if f not in accepted]
        if unknown:
            what = "This change is" if len(unknown) == 1 else "These changes are"
            raise FixSelectionError(
                f"{what} not among the changes this test kept: {', '.join(unknown)}. "
                "Reload the page and choose again."
            )
        return [f for f in accepted if f in wanted]

    def _rebuild(
        self, venue: Venue, summary: dict[str, Any], chosen: list[str]
    ) -> tuple[Venue, list[ScenarioEventIn]]:
        """The tested venue with only the chosen fix bundles, applied as the session did."""
        fixes: dict[str, Fix] = {}
        for raw in summary.get("fixes") or []:
            try:
                fx = Fix.model_validate(raw)
            except ValueError:
                continue
            fixes[fx.fix_id] = fx
        missing = [f for f in chosen if f not in fixes]
        if missing:
            raise FixSelectionError(
                "This test did not record the details of "
                + ", ".join(missing)
                + ", so the changes can't be applied one by one. Accept all of them, "
                "or test again."
            )
        measures: list[ScenarioEventIn] = []
        for fid in chosen:
            fx = fixes[fid]
            try:
                venue = apply_fix_bundle(venue, fx, self.st.registry)
                validate_operational(venue, [*measures, *fx.operational], self.st.registry)
            except (PlanError, PatchError, ValueError) as exc:
                problems = getattr(exc, "problems", None) or [str(exc)]
                raise FixConflict(
                    f"“{fx.title}” can't be applied without the changes you left out "
                    f"({problems[0]}). Also choose the change it builds on, or accept all "
                    "changes."
                ) from exc
            measures.extend(fx.operational)
        return venue, measures

    def _record_applied(self, sid: str, record: dict[str, Any]) -> None:
        """Remember which fixes went into which version (read by Your plan and exports)."""
        with db_session() as db:
            row = db.get(RedTeamSession, sid)
            if row is None:
                return
            summary = dict(row.summary or {})
            summary["applied"] = [*(summary.get("applied") or []), record]
            row.summary = summary
            db.add(row)
            db.commit()
