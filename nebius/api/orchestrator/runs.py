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

from api.adapters.sandbox import SandboxRunner, SimJob, failed_result
from api.core.extensions import Registry
from api.core.plan import (
    STAFF_MEASURES,
    PlanError,
    fail,
    apply_fix_bundle,
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
        self.tasks: dict[str, asyncio.Task[RunResult]] = {}
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
    ) -> SimJob:
        """Everything the sandbox needs; the exit plan comes from Tier 1."""
        st = self.settings
        patched = self.apply_fix(venue, fix)
        if intervention_at_s is not None and fix is not None:
            for action in [*fix.actions, *fix.replace_actions]:
                if action.start_s < intervention_at_s:
                    raise PlanError([fail("action_before_intervention", "A proposed action starts before the intervention; update its interval and allocation.", action.action_id)])
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
        """Start (or attach to) a run in the background; returns the run id."""
        rid = job.request.run_id
        if rid in self.tasks and not self.tasks[rid].done():
            return rid
        if self.cached(rid) is not None:
            self._touch(rid, project_id, session_id, label)
            return rid
        self._upsert(job, project_id, venue_version, session_id, label)
        self.tasks[rid] = asyncio.create_task(self._execute(job))
        return rid

    async def run(
        self,
        job: SimJob,
        project_id: str | None = None,
        venue_version: int | None = None,
        session_id: str | None = None,
        label: str = "",
    ) -> RunResult:
        """Run (or reuse) and wait for the result."""
        rid = self.submit(job, project_id, venue_version, session_id, label)
        task = self.tasks.get(rid)
        if task is not None:
            return await task
        cached = self.cached(rid)
        assert cached is not None
        return cached

    async def _execute(self, job: SimJob) -> RunResult:
        rid = job.request.run_id
        self._set_status(rid, "running")
        self._notify(rid, {"status": "running"})
        if self.hooks is not None:
            self._hook("on_run_started", request=job.request)
        t0 = time.monotonic()

        def on_progress(p: dict[str, Any]) -> None:
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
        self._notify(rid, {"status": result.status, "result": result.model_dump(mode="json")})
        if self.hooks is not None:
            self._hook("on_run_finished", result=result)
        return result

    async def cancel(self, run_id: str) -> bool:
        """Cancel a running job."""
        task = self.tasks.get(run_id)
        if task is None or task.done():
            return False
        cancel = getattr(self.runner, "cancel", None)
        if cancel is not None:
            await cancel(run_id)
        task.cancel()
        return True

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

    def get(self, run_id: str) -> Run | None:
        """Run row with live progress merged in."""
        with db_session(self.db_url) as s:
            row = s.get(Run, run_id)
        if row is not None and run_id in self.progress:
            row.progress = self.progress[run_id]
        return row

    def list(self, project_id: str, limit: int = 50) -> list[Run]:
        """Recent runs of a project."""
        with db_session(self.db_url) as s:
            return project_runs(s, project_id, limit)

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
