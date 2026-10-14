"""Red Team Night (section 12.1): red/blue loop over sandboxed simulation branches.

Events are persisted (SessionEventRow) and streamed to the UI; every budget ends the
session gracefully with what exists.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, select

from api.adapters.llm import Budget, BudgetExceeded
from api.agents.base import AgentEnv, AgentUnavailable, audit_decision
from api.agents.blue_team import blue_team
from api.agents.judge import judge
from api.agents.red_team import incident_query, red_team, venue_features
from api.core.annotations import carry_annotations
from api.core.countdown import compute_countdown
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
from api.orchestrator.fallbacks import rule_attacks, rule_fixes

log = logging.getLogger("showtime.session")


class StopSession(Exception):
    """A budget or the user ended the session."""


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


class SessionManager:
    """Starts, streams, stops and applies Red Team Night sessions."""

    def __init__(self, state: Any) -> None:
        self.st = state
        self.live: dict[str, LiveSession] = {}

    # ------------------------------------------------------------------ API
    def start(self, project_id: str, config: dict[str, Any] | None = None) -> RedTeamSession:
        """Create a session row and launch the loop in the background."""
        p = self.st.projects.get(project_id)
        s = self.st.settings
        cfg = {
            "max_rounds": s.max_rounds,
            "attacks_per_round": s.attacks_per_round,
            "fixes_per_attack": s.fixes_per_attack,
            "fix_targets": s.fix_targets,
            "seed": s.default_seed,
            "confirm_tier3": True,
            "max_runs": s.session_max_runs,
            "max_wall_s": s.session_max_wall_s,
            "max_tokens": s.session_max_tokens,
        }
        cfg.update({k: v for k, v in (config or {}).items() if k in cfg and v is not None})
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

    def stop(self, sid: str) -> bool:
        live = self.live.get(sid)
        if live is None or live.finished:
            return False
        live.stop_requested = True
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
        res: RunResult = await st.runs.run(
            job,
            project_id=live.project_id,
            venue_version=live.venue_version,
            session_id=live.id,
            label=label,
        )
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
            for rnd in range(1, int(cfg["max_rounds"]) + 1):
                self._check(live)
                self._status(live, "red_team", rnd, "Red team is designing attacks")
                attacks = await self._attacks(
                    env,
                    working,
                    baseline,
                    incidents,
                    int(cfg["attacks_per_round"]),
                    seen,
                    len(attacks_all),
                    live.tested,
                )
                if not attacks:
                    reason = "no new attacks"
                    break
                self._status(live, "screening", rnd, "Ranking attacks with the instant estimate")
                ranked: list[tuple[float, Attack]] = []
                for a in attacks:
                    est = self._estimate(live, working, a, extra=live.measures)
                    ranked.append((severity(est), a))
                    self.emit(
                        live,
                        "attack_card",
                        {"round": rnd, "attack": a.model_dump(mode="json"), "tier1": headline(est)},
                    )
                ranked.sort(key=lambda x: -x[0])
                attacks_all.extend(a for _, a in ranked)
                live.tested = [
                    f"{a.title} ({', '.join(e.type for e in a.events)})" for a in attacks_all
                ]
                self._status(live, "simulating", rnd, f"Simulating {len(ranked)} attacks")
                breaks: list[tuple[float, Attack, RunResult]] = []
                for _, a in ranked:
                    r = await self._sim(
                        live,
                        working,
                        2,
                        a.title,
                        f"atk:{a.attack_id}",
                        "baseline",
                        "attack",
                        attack=a,
                        extra=live.measures,
                    )
                    results[r.run_id] = r
                    reasons = break_reasons(
                        r,
                        s.density_danger_ppm2,
                        s.danger_min_duration_s,
                        self._target(working),
                        s.safety_factor,
                    )
                    self._node_done(live, f"atk:{a.attack_id}", r, reasons)
                    if reasons:
                        breaks.append((severity(r), a, r))
                        if worst is None or severity(r) > worst[0]:
                            worst = (severity(r), a, r)
                scoreboard.append({"round": rnd, "breaks": len(breaks), "attacks": len(ranked)})
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
                    reason = "no new breaks"
                    break
                breaks.sort(key=lambda x: -x[0])
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
                        env, working, a, r, int(cfg["fixes_per_attack"]), f"F{len(fixes_all) + 1}_"
                    )
                    for fx in fixes:
                        try:
                            candidate = apply_fix_bundle(working, fx, st.registry)
                            validate_operational(
                                candidate, [*live.measures, *fx.operational], st.registry
                            )
                        except (PlanError, PatchError, ValueError) as exc:
                            self.emit(
                                live,
                                "log",
                                {
                                    "level": "warning",
                                    "message": f"Rejected complete fix bundle: {exc}",
                                },
                            )
                            continue
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
                        fr = await self._sim(
                            live,
                            working,
                            2,
                            fx.title,
                            f"fix:{fx.fix_id}",
                            f"atk:{a.attack_id}",
                            "fix",
                            attack=a,
                            fix=fx,
                            extra=live.measures,
                        )
                        results[fr.run_id] = fr
                        gain = (sev - severity(fr)) / sev if sev > 0 else 0.0
                        fr_reasons = break_reasons(
                            fr,
                            s.density_danger_ppm2,
                            s.danger_min_duration_s,
                            self._target(working),
                            s.safety_factor,
                        )
                        # kept when it removes the break, or improves the result by FIX_MIN_GAIN,
                        # and never when it makes the plan worse without the attack. Both sides
                        # must be simulations (or both previews): an instant estimate shown in
                        # place of a failed simulation is never enough to keep a change.
                        helps = (not fr_reasons and gain > 0) or gain >= float(s.fix_min_gain)
                        evidence_ok = comparable(r, fr)
                        ok = (
                            helps
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
                                    "finished simulation to compare (only an instant estimate)",
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
                            live.measures.extend(fx.operational)
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
    ) -> list[Attack]:
        try:
            out = await red_team(
                env, self.st.registry, venue, baseline, incidents, n, seen, offset, tested=tested
            )
        except AgentUnavailable as exc:
            if env.emit:
                env.emit(
                    "log",
                    {
                        "level": "warning",
                        "message": f"Red team model unavailable ({exc}); using rule-based attacks",
                    },
                )
            out = []
        if not out:
            out = rule_attacks(venue, baseline, incidents, n, seen, offset)
            if out and env.emit:
                env.emit("log", {"level": "info", "message": "Rule-based attacks were added."})
        return out

    async def _fixes(
        self, env: AgentEnv, venue: Venue, attack: Attack, result: RunResult, n: int, prefix: str
    ) -> list[Fix]:
        try:
            out = await blue_team(env, self.st.registry, venue, attack, result, n, prefix)
        except AgentUnavailable:
            out = []
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
        self._status(live, "judging", len(scoreboard), "Judge is checking every number")
        try:
            text, recs, checked = await judge(env, facts_for_judge, template, computed_summary=True)
        except (AgentUnavailable, BudgetExceeded):
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
        live.finished = True
        await self._notify(live)

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
            except Exception:
                continue
            if h is not None:
                hazards.append(h)
        timed = [h for h in hazards if h.t_hazard_s is not None]
        chosen = (
            min(timed, key=lambda h: h.t_hazard_s or 0.0)
            if timed
            else (hazards[0] if hazards else None)
        )
        # the wording follows the run's basis; it never claims more than that run shows
        source = f"{scenario} ({describe_run(run)})" if run else ""
        return compute_countdown(
            chosen,
            rset,
            s.pre_movement_s,
            s.safety_factor,
            source,
            venue.location.event_start if venue.location else None,
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
