"""Runs: instant estimates and sandboxed simulations, idempotent and cached.

The run id is a hash of everything that determines the result (venue hash, events,
tier, seed, caps, engine, sim settings), so the same request returns the same run.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import col, select

from api.adapters.sandbox import SandboxRunner, SimJob, failed_result
from api.core.evidence import fallback_estimate
from api.core.extensions import Registry
from api.core.plan import (
    STAFF_MEASURES,
    PlanError,
    apply_fix_bundle,
    fail,
    plan_hash,
    saved_events,
    validate_operational,
    validate_run_horizon,
)
from api.core.settings import Settings
from api.core.tier1 import run_tier1
from api.core.venue_ops import venue_hash
from api.db.models import Run
from api.db.queries import project_runs
from api.db.session import db_session
from api.models import Attack, Fix, RunRequest, RunResult, ScenarioEventIn, Venue

log = logging.getLogger("showtime.runs")
RESTARTED = "Stopped when the server restarted. Run it again."
Listener = Callable[[str, dict[str, Any]], None]


def compose_events(
    attack: Attack | None,
    fix: Fix | None,
    intervention_at_s: float | None = None,
    extra: list[ScenarioEventIn] | None = None,
) -> list[ScenarioEventIn]:
    """Attack events, then fix measures (which start no earlier than the intervention time)."""
    out: list[ScenarioEventIn] = []
    if attack is not None:
        out.extend(attack.events)
    if fix is not None:
        t0 = intervention_at_s or 0.0
        for ev in fix.operational:
            data = ev.model_dump()
            data["at_s"] = max(float(data.get("at_s", 0.0)), t0)
            out.append(ScenarioEventIn.model_validate(data))
    out.extend(extra or [])
    return out


def sim_settings(settings: Settings, tier: int) -> dict[str, Any]:
    """Physical parameters passed to the sim image (all documented in ASSUMPTIONS.md)."""
    s = {
        "walk_speed_mean": settings.walk_speed_mean,
        "walk_speed_sd": settings.walk_speed_sd,
        "slow_walker_fraction": settings.slow_walker_fraction,
        "agent_radius": settings.agent_radius,
        "agent_time_gap": settings.agent_time_gap,
        "specific_flow": settings.specific_flow,
        "stair_speed": settings.stair_speed,
        "stair_flow": settings.stair_flow,
        "density_warn_ppm2": settings.density_warn_ppm2,
        "density_danger_ppm2": settings.density_danger_ppm2,
    }
    if tier == 2:
        s["dt"] = settings.sim_dt_s
        s["frame_hz"] = 2.0
    return s


def run_id_for(payload: dict[str, Any]) -> str:
    """Deterministic id from the request content."""
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return "r_" + hashlib.sha256(blob.encode()).hexdigest()[:12]


class RunService:
    """Creates, executes, caches and reports runs."""

    def __init__(
        self,
        settings: Settings,
        registry: Registry,
        runner: SandboxRunner,
        db_url: str | None = None,
        hooks: Any | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.runner = runner
        self.db_url = db_url
        self.hooks = hooks
        # runs in flight only: a finished run leaves (its result stays in the database)
        self.tasks: dict[str, asyncio.Task[RunResult]] = {}
        # Run ids are content hashes, so callers share one run. `waiters` counts the calls of
        # `run()` waiting for it, and `detached` holds runs someone started to follow over the
        # API (`submit()`); a waiter that is cancelled stops the run only when neither is left.
        self.waiters: dict[str, int] = {}
        self.detached: set[str] = set()
        self.progress: dict[str, dict[str, Any]] = {}
        self.listeners: list[Listener] = []

    # -- instant estimate ------------------------------------------------------------
    def estimate(
        self,
        venue: Venue,
        attack: Attack | None = None,
        fix: Fix | None = None,
        extra: list[ScenarioEventIn] | None = None,
    ) -> RunResult:
        """Tier 1 for a venue (fix patch applied) under attack/fix events."""
        v = self.apply_fix(venue, fix)
        events = self._events(v, attack, fix, None, extra)
        rid = run_id_for(
            {"t1": venue_hash(v), "plan_hash": plan_hash(v), "ev": [e.model_dump() for e in events]}
        )
        result = run_tier1(
            v,
            events,
            self.registry,
            self.settings,
            run_id=rid,
            attack_id=attack.attack_id if attack else None,
            fix_id=fix.fix_id if fix else None,
        )
        result.extensions["plan_hash"] = plan_hash(v)
        return result

    def _events(
        self,
        venue: Venue,
        attack: Attack | None,
        fix: Fix | None,
        intervention_at_s: float | None,
        extra: list[ScenarioEventIn] | None,
    ) -> list[ScenarioEventIn]:
        validate_operational(
            venue,
            [
                e
                for e in (attack.events if attack else [])
                if e.type in STAFF_MEASURES or e.type == "unblock_exit"
            ],
            self.registry,
        )
        validate_operational(venue, fix.operational if fix else [], self.registry)
        validate_operational(
            venue,
            [e for e in (extra or []) if e.type in STAFF_MEASURES or e.type == "unblock_exit"],
            self.registry,
        )
        return compose_events(attack, fix, intervention_at_s, extra) + saved_events(
            venue, self.registry
        )

    def apply_fix(self, venue: Venue, fix: Fix | None) -> Venue:
        """Venue with the fix's patch applied (geometry errors are rejected)."""
        return apply_fix_bundle(venue, fix, self.registry)

    # -- simulations ------------------------------------------------------------------------
    def build_job(
        self,
        venue: Venue,
        tier: int,
        seed: int | None = None,
        attack: Attack | None = None,
        fix: Fix | None = None,
        intervention_at_s: float | None = None,
        parent_run_id: str | None = None,
        max_people: int | None = None,
        extra: list[ScenarioEventIn] | None = None,
        checkpoint_at_s: float | None = None,
        resume_from: str | None = None,
        speed_factor: float | None = None,
    ) -> SimJob:
        """Everything the sandbox needs; the exit plan comes from Tier 1.

        `checkpoint_at_s` asks the run to write checkpoint.json at that simulated time;
        `resume_from` starts the run from the checkpoint of that run (rewind branches).
        `speed_factor` scales every free walking speed (level mean and spread, stairs) from
        the start; exit and stair flow capacities stay as set (sensitivity runs).
        """
        st = self.settings
        patched = self.apply_fix(venue, fix)
        if intervention_at_s is not None and fix is not None:
            for action in [*fix.actions, *fix.replace_actions]:
                if action.start_s < intervention_at_s:
                    raise PlanError(
                        [
                            fail(
                                "action_before_intervention",
                                "A proposed action starts before the intervention; "
                                "update its interval and allocation.",
                                action.action_id,
                            )
                        ]
                    )
        events = self._events(patched, attack, fix, intervention_at_s, extra)
        t1 = run_tier1(
            patched,
            events,
            self.registry,
            st,
            attack_id=attack.attack_id if attack else None,
            fix_id=fix.fix_id if fix else None,
        )
        base_venue = (
            venue if (intervention_at_s is not None and fix is not None and fix.patch.ops) else None
        )
        plan: dict[str, Any] = t1.extensions.get("plan", {})
        if base_venue is not None:
            # identical start to the parent run: use the parent's exit plan
            parent_events = self._events(venue, attack, None, None, extra)
            plan = run_tier1(venue, parent_events, self.registry, st).extensions.get("plan", {})
        settings_payload = sim_settings(st, tier)
        if speed_factor is not None and abs(speed_factor - 1.0) > 1e-9:
            for k in ("walk_speed_mean", "walk_speed_sd", "stair_speed"):
                settings_payload[k] = round(float(settings_payload[k]) * speed_factor, 4)
        max_sim = st.tier2_max_sim_s if tier == 2 else st.max_sim_s
        validate_run_horizon(patched, max_sim, self.registry)
        payload = {
            "v": venue_hash(patched),
            "plan_hash": plan_hash(patched),
            "base": venue_hash(base_venue) if base_venue else None,
            "ev": [e.model_dump() for e in events],
            "tier": tier,
            "seed": seed if seed is not None else st.default_seed,
            "max_people": max_people or st.max_people,
            "max_sim_s": max_sim,
            "iv": intervention_at_s,
            "engine": "jupedsim",
            # Mock and real providers must never reuse each other's cached runs.
            "sandbox_provider": self.runner.provider,
            "sim": settings_payload,
            "plan": plan,
        }
        # rewind fields only enter the hash when used, so existing run ids stay the same
        if checkpoint_at_s is not None:
            payload["ckpt"] = checkpoint_at_s
        if resume_from is not None:
            payload["resume_from"] = resume_from
        rid = run_id_for(payload)
        req = RunRequest(
            run_id=rid,
            venue_id=venue.venue_id,
            venue_hash=venue_hash(patched),
            attack_id=attack.attack_id if attack else None,
            fix_id=fix.fix_id if fix else None,
            tier=tier,
            seed=payload["seed"],
            max_people=payload["max_people"],
            max_sim_s=max_sim,
            max_wall_s=st.max_wall_s,
            intervention_at_s=intervention_at_s,
            parent_run_id=parent_run_id,
            checkpoint_at_s=checkpoint_at_s,
            resume=resume_from is not None,
            extensions={
                "plan_hash": plan_hash(patched),
                "sandbox_provider": self.runner.provider,
            },
        )
        return SimJob(
            request=req,
            venue=patched,
            events=[e.model_dump() for e in events],
            plan=plan,
            sim_settings=settings_payload,
            base_venue=base_venue,
            attack=attack,
            fix=fix,
            parent_node=parent_run_id,
            tier1=t1,
            resume_from=resume_from,
        )

    def cached(self, run_id: str) -> RunResult | None:
        """A finished, successful run with this id (artifacts still on disk)."""
        with db_session(self.db_url) as s:
            row = s.get(Run, run_id)
        if row is None or row.result is None or row.status not in ("ok", "partial"):
            return None
        res = RunResult.model_validate(row.result)
        if (
            res.artifacts.trajectory
            and not (self.settings.root_dir / res.artifacts.trajectory).exists()
        ):
            return None
        return res

    def submit(
        self,
        job: SimJob,
        project_id: str | None = None,
        venue_version: int | None = None,
        session_id: str | None = None,
        label: str = "",
    ) -> str:
        """Start (or attach to) a run in the background; returns the run id.

        The run is followed over the API, so a cancelled waiter of the same run (another
        caller's `run()`) never stops it; only `cancel()` does."""
        rid = job.request.run_id
        if self._start(job, project_id, venue_version, session_id, label) is not None:
            self.detached.add(rid)
        return rid

    def _start(
        self,
        job: SimJob,
        project_id: str | None,
        venue_version: int | None,
        session_id: str | None,
        label: str,
    ) -> asyncio.Task[RunResult] | None:
        """The task of the run in flight (started now if needed); None for a cached result."""
        rid = job.request.run_id
        task = self.tasks.get(rid)
        if task is not None and not task.done():
            return task
        if self.cached(rid) is not None:
            self._touch(rid, project_id, session_id, label)
            self._sandbox(rid, "reused", 0.0, label=label)
            return None
        self._upsert(job, project_id, venue_version, session_id, label)
        task = self.tasks[rid] = asyncio.create_task(self._execute(job))
        task.add_done_callback(lambda t: self._forget(rid, t))
        return task

    def _forget(self, rid: str, task: asyncio.Task[RunResult]) -> None:
        if self.tasks.get(rid) is task:
            del self.tasks[rid]
            self.detached.discard(rid)

    async def run(
        self,
        job: SimJob,
        project_id: str | None = None,
        venue_version: int | None = None,
        session_id: str | None = None,
        label: str = "",
    ) -> RunResult:
        """Run (or reuse) and wait for the result.

        A result this call did not compute (a cached run, or one already in flight) comes
        back as a copy tagged `extensions["cache_hit"]`, so usage records count it as reused.
        """
        rid = job.request.run_id
        prior = self.tasks.get(rid)
        task = self._start(job, project_id, venue_version, session_id, label)
        if task is not None:
            self.waiters[rid] = self.waiters.get(rid, 0) + 1
            released = False
            try:
                # shielded: cancelling this caller must not cancel a run others still wait for
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                released = True
                self._release(rid)
                if not task.done() and not self._held(rid):
                    await self._stop(rid, task)
                raise
            finally:
                if not released:
                    self._release(rid)
            return _reused(result) if task is prior else result
        cached = self.cached(rid)
        assert cached is not None
        return _reused(cached)

    async def run_many(
        self,
        jobs: list[tuple[SimJob, str]],
        project_id: str | None = None,
        venue_version: int | None = None,
        session_id: str | None = None,
        on_done: Callable[[int, RunResult], None] | None = None,
    ) -> list[RunResult]:
        """Run independent jobs (job, label) at once; results come back in the given order.

        The runner bounds how many sandboxes run together (SANDBOX_MAX_PARALLEL). A job that
        raises gives a failed result instead of stopping the others. `on_done(index, result)`
        is called as each one finishes. Cancelling the caller cancels every unfinished run
        nobody else is waiting for.
        """

        async def one(i: int, job: SimJob, label: str) -> RunResult:
            try:
                res = await self.run(job, project_id, venue_version, session_id, label)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # one bad job must not stop the fan-out
                log.exception("fan-out job %s failed", job.request.run_id)
                res = failed_result(job, self.runner.provider, f"The run couldn't start: {exc}")
            if on_done is not None:
                on_done(i, res)
            return res

        tasks = [asyncio.create_task(one(i, j, lb)) for i, (j, lb) in enumerate(jobs)]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            # each cancelled wait stops its run unless another caller still waits for it
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    def record_fallback(
        self,
        job: SimJob,
        failed: RunResult,
        project_id: str | None = None,
        venue_version: int | None = None,
        session_id: str | None = None,
        label: str = "",
    ) -> RunResult | None:
        """Store the instant estimate shown in place of a failed simulation as its own run,
        linked to the failed one (`extensions.fallback_for`). The failed run is untouched."""
        if job.tier1 is None:
            return None
        fb = fallback_estimate(failed, job.tier1)
        fb.extensions.setdefault("plan_hash", job.request.extensions.get("plan_hash"))
        request = job.request.model_copy(
            update={
                "run_id": fb.run_id,
                "tier": 1,
                "extensions": {**job.request.extensions, "fallback_for": failed.run_id},
            }
        )
        with db_session(self.db_url) as s:
            row = s.get(Run, fb.run_id) or Run(id=fb.run_id)
            row.project_id = project_id or row.project_id
            row.session_id = session_id or row.session_id
            row.venue_version = venue_version if venue_version is not None else row.venue_version
            row.venue_hash = fb.venue_hash
            row.tier = 1
            row.status = fb.status
            row.label = f"{label} (instant estimate)" if label else row.label
            row.attack_id, row.fix_id = fb.attack_id, fb.fix_id
            row.parent_run_id = fb.parent_run_id
            row.request = request.model_dump(mode="json")
            row.result = fb.model_dump(mode="json")
            row.error = None
            row.created_at = datetime.now(UTC)
            row.finished_at = row.created_at
            s.add(row)
            s.commit()
        return fb

    async def _execute(self, job: SimJob) -> RunResult:
        rid = job.request.run_id
        self._set_status(rid, "running")
        self._notify(rid, {"status": "running"})
        if self.hooks is not None:
            self._hook("on_run_started", request=job.request)
        t0 = time.monotonic()
        started: list[float] = []  # when the runner's container started (after any queue)
        self._sandbox(rid, "queued", 0.0, tier=job.request.tier)

        def on_progress(p: dict[str, Any]) -> None:
            if p.get("sandbox_started"):
                started.append(time.monotonic())
                self._sandbox(rid, "running", time.monotonic() - t0, tier=job.request.tier)
                return
            self.progress[rid] = p
            self._notify(rid, {"status": "running", "progress": p})

        try:
            result = await self.runner.run(job, on_progress)
            if result.status == "failed" and "crashed" in (result.error or ""):
                log.warning("run %s crashed, retrying once", rid)
                result = await self.runner.run(job, on_progress)
        except asyncio.CancelledError:
            result = failed_result(
                job,
                getattr(self.runner, "provider", "?"),
                "Cancelled.",
                status="cancelled",
                runtime=time.monotonic() - t0,
            )
        except Exception as exc:  # the sandbox must never take the API down
            log.exception("run %s failed", rid)
            result = failed_result(
                job,
                getattr(self.runner, "provider", "?"),
                f"The simulation couldn't run: {exc}",
                runtime=time.monotonic() - t0,
            )
        result.parent_run_id = job.request.parent_run_id
        result.extensions.setdefault(
            "tier1",
            {
                "evac_time_p95_s": job.tier1.metrics.evac_time_p95_s if job.tier1 else None,
                "peak_density_ppm2": job.tier1.metrics.peak_density_ppm2 if job.tier1 else None,
            },
        )
        self._finish(rid, result)
        self.progress.pop(rid, None)
        ran_s = time.monotonic() - (started[0] if started else t0)
        self._sandbox(rid, elapsed_s=ran_s, tier=result.tier, **sandbox_outcome(result, job))
        self._notify(rid, {"status": result.status, "result": result.model_dump(mode="json")})
        if self.hooks is not None:
            self._hook("on_run_finished", result=result)
        return result

    async def cancel(self, run_id: str) -> bool:
        """Cancel a running job for everyone (the organizer's Cancel). Callers that only stop
        waiting cancel their own `run()` instead, which keeps a run others still need."""
        task = self.tasks.get(run_id)
        if task is None or task.done():
            return False
        await self._stop(run_id, task)
        return True

    def _release(self, rid: str) -> None:
        n = self.waiters.get(rid, 0) - 1
        if n > 0:
            self.waiters[rid] = n
        else:
            self.waiters.pop(rid, None)

    def _held(self, rid: str) -> bool:
        """Someone still needs this run: a waiting `run()` or an API follower."""
        return self.waiters.get(rid, 0) > 0 or rid in self.detached

    async def _stop(self, rid: str, task: asyncio.Task[RunResult]) -> None:
        """Stop the sandbox run and wait until its cancelled result is stored."""
        cancel = getattr(self.runner, "cancel", None)
        if cancel is not None:
            try:
                await cancel(rid)
            except Exception:  # cancelling the task below still stops the wait for it
                log.exception("sandbox cancel of %s failed", rid)
        task.cancel()
        await asyncio.wait({task})

    # -- persistence ------------------------------------------------------------------------
    def _upsert(
        self,
        job: SimJob,
        project_id: str | None,
        venue_version: int | None,
        session_id: str | None,
        label: str,
    ) -> None:
        req = job.request
        with db_session(self.db_url) as s:
            row = s.get(Run, req.run_id) or Run(id=req.run_id)
            row.project_id = project_id or row.project_id
            row.session_id = session_id or row.session_id
            row.venue_version = venue_version if venue_version is not None else row.venue_version
            row.venue_hash = req.venue_hash
            row.tier = req.tier
            row.status = "queued"
            row.label = label or row.label
            row.attack_id, row.fix_id = req.attack_id, req.fix_id
            row.parent_run_id = req.parent_run_id
            row.request = req.model_dump(mode="json")
            row.result = None
            row.error = None
            row.created_at = datetime.now(UTC)
            s.add(row)
            s.commit()

    def _touch(self, rid: str, project_id: str | None, session_id: str | None, label: str) -> None:
        with db_session(self.db_url) as s:
            row = s.get(Run, rid)
            if row is None:
                return
            if project_id and not row.project_id:
                row.project_id = project_id
            if session_id and not row.session_id:
                row.session_id = session_id
            if label and not row.label:
                row.label = label
            s.add(row)
            s.commit()

    def _set_status(self, rid: str, status: str) -> None:
        with db_session(self.db_url) as s:
            row = s.get(Run, rid)
            if row is not None:
                row.status = status
                s.add(row)
                s.commit()

    def _finish(self, rid: str, result: RunResult) -> None:
        with db_session(self.db_url) as s:
            row = s.get(Run, rid)
            if row is None:
                return
            row.status = result.status
            row.result = result.model_dump(mode="json")
            row.error = result.error
            row.finished_at = datetime.now(UTC)
            s.add(row)
            s.commit()

    def recover_interrupted(self) -> int:
        """At server start: runs left queued or running by the previous process are failed,
        with a note, so they are neither shown as running nor reused (returns how many)."""
        with db_session(self.db_url) as s:
            rows = list(s.exec(select(Run).where(col(Run.status).in_(["queued", "running"]))))
            rows = [r for r in rows if r.id not in self.tasks]
            for row in rows:
                row.status = "failed"
                row.error = RESTARTED
                row.finished_at = datetime.now(UTC)
                s.add(row)
            s.commit()
        if rows:
            log.warning("marked %d interrupted runs as failed", len(rows))
        return len(rows)

    def get(self, run_id: str) -> Run | None:
        """Run row with live progress merged in and its evidence basis derived."""
        with db_session(self.db_url) as s:
            row = s.get(Run, run_id)
        if row is not None and run_id in self.progress:
            row.progress = self.progress[run_id]
        return _with_basis(row) if row is not None else None

    def list(self, project_id: str, limit: int = 50) -> list[Run]:
        """Recent runs of a project."""
        with db_session(self.db_url) as s:
            rows = project_runs(s, project_id, limit)
        return [_with_basis(r) for r in rows]

    def artifact_path(self, run_id: str, kind: str) -> Path | None:
        """Absolute path of a run artifact (trajectory, trajectory_index, density_grid...)."""
        row = self.get(run_id)
        if row is None or row.result is None:
            return None
        rel = (row.result.get("artifacts") or {}).get(kind)
        if not rel:
            return None
        p: Path = (self.settings.root_dir / rel).resolve()
        runs_root = self.settings.runs_dir.resolve()
        if runs_root not in p.parents or not p.exists():
            return None
        return p

    def _sandbox(self, rid: str, state: str, elapsed_s: float, **extra: Any) -> None:
        """A structured sandbox lifecycle event for listeners (the session's live feed)."""
        self._notify(
            rid,
            {
                "sandbox": {
                    "run_id": rid,
                    "state": state,
                    "elapsed_s": round(elapsed_s, 1),
                    "provider": getattr(self.runner, "provider", "?"),
                    "limits": _limits(self.runner),
                    **extra,
                }
            },
        )

    def _notify(self, rid: str, data: dict[str, Any]) -> None:
        for fn in list(self.listeners):
            try:
                fn(rid, data)
            except Exception:  # listeners must not break runs
                log.exception("run listener failed")

    def _hook(self, name: str, **kw: Any) -> None:
        if self.hooks is None:
            return
        try:
            getattr(self.hooks.hook, name)(**kw)
        except Exception:
            log.exception("plugin hook %s failed", name)


SCRIPT_STOPPED = "scenario script stopped: "
REFUSED = "it failed the safety check"


def sandbox_outcome(result: RunResult, job: SimJob) -> dict[str, Any]:
    """What happened in the sandbox, for the live feed: the run's state and, for an AI-written
    scenario script, whether it ran, was refused by the in-sandbox check, or was stopped by a
    budget, with the reason exactly as the sandbox wrote it. Built from the result only; no
    container output is ever passed on."""
    has_script = any(e.get("type") == "script" for e in job.events)
    stopped = next((n for n in result.notes if n.startswith(SCRIPT_STOPPED)), None)
    script: dict[str, Any] | None = None
    if has_script:
        if stopped is None:
            script = {"state": "ran", "reason": None}
        else:
            why = stopped[len(SCRIPT_STOPPED) :]
            script = {"state": "refused" if why.startswith(REFUSED) else "stopped", "reason": why}
    error = result.error or ""
    if result.status == "timeout" or "out of memory" in error:
        return {"state": "killed", "reason": error or None, "script": script}
    if result.status in ("failed", "cancelled"):
        return {"state": result.status, "reason": error or None, "script": script}
    if script is not None and script["state"] == "refused":
        return {"state": "refused", "reason": script["reason"], "script": script}
    return {"state": "finished", "reason": None, "script": script}


def _limits(runner: Any) -> str:
    iso = getattr(runner, "isolation", None)
    return str(iso.summary()) if iso is not None else ""


def _reused(result: RunResult) -> RunResult:
    """A copy of a result this call did not compute, tagged as a cache hit."""
    out = result.model_copy(deep=True)
    out.extensions["cache_hit"] = True
    return out


def _with_basis(row: Run) -> Run:
    """Results stored before `basis` existed get it on read; stored copies are re-derived.

    Only the returned (detached) row changes; nothing is written back.
    """
    if row.result:
        try:
            row.result = {**row.result, "basis": RunResult.model_validate(row.result).basis}
        except ValueError:
            log.warning("run %s has a result that no longer validates", row.id)
    return row
