"""Stress test at scale (SANDBOX_SCOPE idea 4): every attack × (plan as it is + each kept
change) × several seeds, as quick simulations fanned out over parallel sandboxes.

The runner bounds how many run at once (SANDBOX_MAX_PARALLEL). The record keeps a live
counter (done / total / failed) and one row per run; failed runs stay listed with their
reason. Records are internal user settings (`_stress:<id>`), so no table changes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

from api.adapters.sandbox import SimJob
from api.agents.red_team import incident_query, venue_features
from api.core.extensions import IncidentRecord
from api.core.extensions.breaks import BreakRule, break_reasons
from api.core.plan import PlanError
from api.core.venue_ops import PatchError
from api.models import Attack, Fix, RunResult, Venue
from api.orchestrator.fallbacks import rule_attacks
from api.orchestrator.rewind import live_or_interrupted, load_record, now_iso, numbers, save_record

log = logging.getLogger("showtime.stress")

MAX_RUNS = 120
TIER = 2  # quick simulations
_TASKS: dict[str, asyncio.Task[None]] = {}

AttackSource = Literal["session", "rules"]


class StressError(ValueError):
    """The stress test can't start (too many runs, nothing to test)."""


def _latest_session(st: Any, project_id: str) -> Any | None:
    for row in st.sessions.list_sessions(project_id):
        if row.status in ("finished", "stopped") and (row.summary or {}).get("attacks"):
            return row
    return None


def _incidents(st: Any, venue: Venue) -> list[IncidentRecord]:
    """Real incidents the standard attacks cite (as the red-team session finds them)."""
    srcs = st.registry.all("IncidentSource")
    if not srcs:
        return []
    found: list[IncidentRecord] = srcs[0].search(
        incident_query(venue, venue_features(venue, None)), 8
    )
    return found


def plan_runs(
    st: Any, project_id: str, attacks: AttackSource, seeds: int, include_fixes: bool
) -> tuple[Venue, int, list[Attack], list[Fix | None], list[int], list[str], str | None]:
    """What the stress test will run: (venue, version, attacks, variants, seeds, notes, session)."""
    p = st.projects.get(project_id)
    version = p.current_version
    venue: Venue = st.projects.venue(project_id, version)
    notes: list[str] = []
    session = _latest_session(st, project_id)
    chosen: list[Attack] = []
    if attacks == "session" and session is not None:
        chosen = [Attack.model_validate(a) for a in session.summary["attacks"]]
    elif attacks == "session":
        notes.append("No finished test yet, so the standard attacks are used.")
    if not chosen:
        chosen = rule_attacks(venue, None, _incidents(st, venue), 4, set(), 0)
    if not chosen:
        raise StressError("There is nothing to test: the plan has no exits or zones to attack.")
    variants: list[Fix | None] = [None]
    if include_fixes and session is not None:
        fixes = {f["fix_id"]: f for f in session.summary.get("fixes") or []}
        for fid in session.summary.get("accepted_fixes") or []:
            if fid in fixes:
                variants.append(Fix.model_validate(fixes[fid]))
        if session.venue_version != version and len(variants) > 1:
            notes.append(
                f"The kept changes were found on version {session.venue_version}; they are "
                f"tried on version {version} as it is now."
            )
    elif include_fixes:
        notes.append("No finished test yet, so there are no kept changes to add.")
    seed_list = [int(st.settings.default_seed) + i for i in range(seeds)]
    total = len(chosen) * len(variants) * len(seed_list)
    if total > MAX_RUNS:
        raise StressError(
            f"That is {total} simulations, more than the {MAX_RUNS} allowed at once. "
            "Choose fewer seeds or leave out the kept changes."
        )
    return venue, version, chosen, variants, seed_list, notes, session.id if session else None


def start_stress(
    st: Any,
    project_id: str,
    attacks: AttackSource = "session",
    seeds: int = 2,
    include_fixes: bool = True,
) -> dict[str, Any]:
    """Plan every run, store the record and start the fan-out in the background."""
    venue, version, chosen, variants, seed_list, notes, session_id = plan_runs(
        st, project_id, attacks, seeds, include_fixes
    )
    sid = f"st_{uuid.uuid4().hex[:10]}"
    rows: list[dict[str, Any]] = []
    jobs: list[tuple[SimJob, str]] = []
    for a in chosen:
        for fx in variants:
            for seed in seed_list:
                variant = fx.title if fx else "Plan as it is"
                row: dict[str, Any] = {
                    "attack_id": a.attack_id,
                    "attack": a.title,
                    "variant": variant,
                    "fix_id": fx.fix_id if fx else None,
                    "seed": seed,
                    "run_id": None,
                    "status": "queued",
                    "basis": None,
                    "metrics": {},
                    "breaks": None,
                    "error": None,
                }
                try:
                    job = st.runs.build_job(venue, tier=TIER, seed=seed, attack=a, fix=fx)
                except (PlanError, PatchError, ValueError) as exc:
                    problems = getattr(exc, "problems", None) or [str(exc)]
                    row.update(status="failed", error=f"Couldn't be set up: {problems[0]}")
                    rows.append(row)
                    continue
                job.request.extensions["stress_id"] = sid
                row["run_id"] = job.request.run_id
                row["_job"] = len(jobs)
                jobs.append((job, f"Stress · {a.title} · {variant} · seed {seed}"))
                rows.append(row)
    setup_failed = sum(r["status"] == "failed" for r in rows)
    record: dict[str, Any] = {
        "id": sid,
        "project_id": project_id,
        "venue_version": version,
        "session_id": session_id,
        "attacks_from": attacks,
        "seeds": seed_list,
        "include_fixes": include_fixes,
        "tier": TIER,
        "status": "running" if jobs else "done",
        "created_at": now_iso(),
        "finished_at": None if jobs else now_iso(),
        "total": len(rows),
        "done": setup_failed,
        "failed": setup_failed,
        "rows": rows,
        "notes": notes,
        "parallel": int(getattr(st.settings, "sandbox_max_parallel", 1)),
        "message": None,
    }
    by_job = {r.pop("_job"): r for r in rows if "_job" in r}
    _save(st, record)
    if jobs:
        _TASKS[sid] = asyncio.create_task(_run(st, record, jobs, by_job))
    return record


def _save(st: Any, record: dict[str, Any]) -> None:
    save_record(st, f"_stress:{record['id']}", record)
    save_record(st, f"_stress_latest:{record['project_id']}", {"id": record["id"]})


def get_stress(st: Any, stress_id: str) -> dict[str, Any] | None:
    return live_or_interrupted(load_record(st, f"_stress:{stress_id}"), _TASKS)  # type: ignore[no-any-return]


def latest_stress(st: Any, project_id: str) -> dict[str, Any] | None:
    ref = load_record(st, f"_stress_latest:{project_id}")
    return get_stress(st, str(ref["id"])) if ref else None


def _fill(st: Any, row: dict[str, Any], venue: Venue, res: RunResult) -> None:
    s = st.settings
    ok = res.status in ("ok", "partial")
    target = float(s.target_evac_indoor_s if venue.mode == "indoor" else s.target_evac_outdoor_s)
    row.update(
        status=res.status,
        basis=res.basis,
        metrics=numbers(res) if ok else {},
        error=None if ok else (res.error or res.status),
        breaks=bool(break_reasons(res, BreakRule.of(s, target))) if ok else None,
    )


async def _run(
    st: Any,
    record: dict[str, Any],
    jobs: list[tuple[SimJob, str]],
    by_job: dict[int, dict[str, Any]],
) -> None:
    venue = jobs[0][0].venue

    def on_done(i: int, res: RunResult) -> None:
        row = by_job[i]
        _fill(st, row, venue, res)
        record["done"] = int(record["done"]) + 1
        if row["status"] not in ("ok", "partial"):
            record["failed"] = int(record["failed"]) + 1
        _save(st, record)

    try:
        await st.runs.run_many(
            jobs,
            project_id=record["project_id"],
            venue_version=record["venue_version"],
            on_done=on_done,
        )
        record["status"] = "done"
    except asyncio.CancelledError:
        record.update(status="cancelled", message="Cancelled.")
        raise
    except Exception as exc:  # the record must always end readable
        log.exception("stress %s failed", record["id"])
        record.update(status="failed", message=f"The stress test couldn't finish: {exc}")
    finally:
        record["finished_at"] = now_iso()
        _save(st, record)
        _TASKS.pop(record["id"], None)
