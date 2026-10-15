"""Simulation runs: start, status/progress, cancel and binary artifacts."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.app.errors import ApiException
from api.app.routes_core import get_state
from api.app.routes_projects import _check_events
from api.app.state import AppState
from api.core.geometry import validate_venue
from api.core.plan import evidence_reference, plan_hash
from api.core.venue_ops import PatchError
from api.db.models import Run
from api.models import Attack, Fix, ScenarioEventIn
from api.orchestrator import seeds, sweep

router = APIRouter(prefix="/api/v1")


def run_out(row: Run, current_plan_hash: str | None = None) -> dict[str, Any]:
    """Run payload for the UI."""
    out = {
        "id": row.id,
        "project_id": row.project_id,
        "session_id": row.session_id,
        "venue_version": row.venue_version,
        "tier": row.tier,
        "status": row.status,
        "label": row.label,
        "attack_id": row.attack_id,
        "fix_id": row.fix_id,
        "parent_run_id": row.parent_run_id,
        "request": row.request,
        "result": row.result,
        "progress": row.progress,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
    if current_plan_hash is not None:
        out["evidence"] = evidence_reference(
            row.id,
            row.status,
            row.request.get("extensions", {}).get("plan_hash"),
            current_plan_hash,
            bool(row.fix_id),
        ).model_dump(mode="json")
    return out


class RunIn(BaseModel):
    """Start a simulation of the project's current (or given) venue version."""

    project_id: str
    tier: Literal[2, 3] = 3
    seed: int | None = None
    version: int | None = None
    attack: Attack | None = None
    fix: Fix | None = None
    blocked_exits: list[str] = Field(default_factory=list)
    events: list[ScenarioEventIn] = Field(default_factory=list)
    intervention_at_s: float | None = Field(default=None, ge=0)
    parent_run_id: str | None = None
    label: str = Field(default="", max_length=120)


@router.post("/runs", status_code=202)
async def start_run(body: RunIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Start (or reuse) a run. Same inputs and seed give the same run id."""
    p = st.projects.get(body.project_id)
    version = body.version or p.current_version
    venue = st.projects.venue(body.project_id, version)
    report = validate_venue(venue)
    if not report.ok:
        first = report.errors[0]
        raise ApiException(
            422,
            "venue_invalid",
            f"The simulation couldn't start: {first.message}",
            first.hint,
            {"checks": [c.model_dump() for c in report.errors]},
        )
    extra = [ScenarioEventIn(type="block_exit", exit_id=e, at_s=0) for e in body.blocked_exits]
    extra += body.events
    _check_events(st, venue, extra)
    try:
        job = st.runs.build_job(
            venue,
            tier=body.tier,
            seed=body.seed,
            attack=body.attack,
            fix=body.fix,
            intervention_at_s=body.intervention_at_s,
            parent_run_id=body.parent_run_id,
            extra=extra,
        )
    except PatchError as exc:
        raise ApiException(422, "invalid_fix", exc.problems[0]) from exc
    total = job.tier1.metrics.agents_total if job.tier1 else venue.total_people()
    if total > st.settings.max_people:
        raise ApiException(
            422,
            "too_many_people",
            f"This scenario has {total:,} people; the limit is {st.settings.max_people:,}.",
            "Raise the people limit in Settings or lower a headcount.",
        )
    job.request.extensions["events"] = job.events
    label = body.label or ("Stress test" if not (body.attack or body.fix or extra) else "Scenario")
    rid = st.runs.submit(job, project_id=body.project_id, venue_version=version, label=label)
    row = st.runs.get(rid)
    assert row is not None
    return run_out(row, plan_hash(st.projects.venue(body.project_id))) | {
        "tier1": job.tier1.model_dump(mode="json") if job.tier1 else None
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Status, progress and result."""
    row = st.runs.get(run_id)
    if row is None:
        raise ApiException(404, "not_found", f"Run {run_id} does not exist.")
    digest = plan_hash(st.projects.venue(row.project_id)) if row.project_id else None
    return run_out(row, digest)


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: str, st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """Recent runs of a project (without heavy fields)."""
    out = []
    digest = plan_hash(st.projects.venue(project_id))
    for r in st.runs.list(project_id):
        d = run_out(r, digest)
        d.pop("request", None)
        out.append(d)
    return out


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Stop a running simulation."""
    ok = await st.runs.cancel(run_id)
    return {"cancelled": ok}


def _artifact(st: AppState, run_id: str, kind: str, media: str) -> FileResponse:
    path = st.runs.artifact_path(run_id, kind)
    if path is None:
        raise ApiException(
            404,
            "no_artifact",
            "This run has no replay data.",
            "Instant estimates have no replay; run a simulation.",
        )
    return FileResponse(path, media_type=media, headers={"Cache-Control": "max-age=86400"})


@router.get("/runs/{run_id}/trajectory")
def trajectory(run_id: str, st: AppState = Depends(get_state)) -> FileResponse:
    """Binary trajectories (see sim/metrics.py for the layout)."""
    return _artifact(st, run_id, "trajectory", "application/octet-stream")


@router.get("/runs/{run_id}/trajectory/index")
def trajectory_index(run_id: str, st: AppState = Depends(get_state)) -> FileResponse:
    """Frame times and byte offsets."""
    return _artifact(st, run_id, "trajectory_index", "application/json")


@router.get("/runs/{run_id}/density")
def density(run_id: str, st: AppState = Depends(get_state)) -> FileResponse:
    """Binary density grid uint8 [frames, floors, ny, nx]."""
    return _artifact(st, run_id, "density_grid", "application/octet-stream")


@router.get("/runs/{run_id}/density/index")
def density_index(run_id: str, st: AppState = Depends(get_state)) -> FileResponse:
    """Grid geometry, times and the peak map."""
    return _artifact(st, run_id, "density_index", "application/json")


@router.get("/runs/{run_id}/venue")
def run_venue(run_id: str, st: AppState = Depends(get_state)) -> Any:
    """The venue this run simulated (fix runs include the fix's layout edits)."""
    import json

    row = st.runs.get(run_id)
    if row is None:
        raise ApiException(404, "not_found", f"Run {run_id} does not exist.")
    path = (st.settings.runs_dir / run_id / "venue.json").resolve()
    if st.settings.runs_dir.resolve() not in path.parents or not path.exists():
        raise ApiException(404, "no_venue", "This run has no stored venue.")
    return json.loads(path.read_text())


@router.post("/projects/{project_id}/sweep", status_code=202)
def start_sweep(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Simulate the plan under six what-ifs, each in its own sandbox."""
    report = validate_venue(st.projects.venue(project_id))
    if not report.ok:
        raise ApiException(422, "venue_invalid", report.errors[0].message, report.errors[0].hint)
    return sweep.start_sweep(st, project_id)


@router.get("/projects/{project_id}/sweep")
def get_sweep(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """The latest scenario sweep and its runs (empty when none was started)."""
    return sweep.sweep_status(st, project_id) or {"items": [], "version": None}


# --- Stress test at scale (SANDBOX_SCOPE idea 4) -----------------------------------------------


class StressIn(BaseModel):
    """Attacks from the latest test (or the standard rules) × the plan and each kept change
    × `seeds` random seeds, all as quick simulations."""

    attacks: Literal["session", "rules"] = "session"
    seeds: int = Field(default=2, ge=1, le=5)
    include_fixes: bool = True


@router.post("/projects/{project_id}/stress", status_code=202)
async def start_stress(
    project_id: str, body: StressIn | None = None, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Fan the runs out over parallel sandboxes; poll `GET /stress/{id}` for the counter."""
    from api.orchestrator.stress import StressError
    from api.orchestrator.stress import start_stress as start

    body = body or StressIn()
    st.projects.get(project_id)  # 404 when missing
    try:
        return start(st, project_id, body.attacks, body.seeds, body.include_fixes)
    except StressError as exc:
        raise ApiException(422, "stress_too_big", str(exc)) from exc


@router.get("/stress/{stress_id}")
def get_stress(stress_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Live counter (done / total / failed) and one row per run; failures stay listed."""
    from api.orchestrator.stress import get_stress as load

    rec = load(st, stress_id)
    if rec is None:
        raise ApiException(404, "not_found", f"Stress test {stress_id} does not exist.")
    return rec


@router.get("/projects/{project_id}/stress")
def latest_project_stress(project_id: str, st: AppState = Depends(get_state)) -> Any:
    """The project's latest stress test at scale, or null."""
    from api.orchestrator.stress import latest_stress

    return latest_stress(st, project_id)


# --- Ranges across seeds (N05) ----------------------------------------------------------------


class SeedCheckIn(BaseModel):
    """How many more seeds to run (default: 3 locally, 5 with parallel sandboxes)."""

    n: int | None = Field(default=None, ge=1, le=5)


def _tested_session(st: AppState, session_id: str) -> Any:
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    return row


@router.post("/sessions/{session_id}/seeds", status_code=202)
async def start_seed_check(
    session_id: str, body: SeedCheckIn | None = None, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Repeat the plan's key run (after the kept fixes, else the baseline) with more seeds:
    same venue, events and tier. Repeating a check reuses the runs it already has.

    Async on purpose: runs start as tasks on the server's event loop."""
    row = _tested_session(st, session_id)
    try:
        return seeds.start_seed_check(st, row, body.n if body else None)
    except seeds.SeedCheckError as exc:
        raise ApiException(409, "seed_check_unavailable", str(exc)) from exc


@router.get("/sessions/{session_id}/seeds")
def get_seed_check(session_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """The latest seed check: status, each run with its basis, and the range over the runs
    that finished (`status` is "none" before the first check)."""
    return seeds.seed_check_status(st, _tested_session(st, session_id))
