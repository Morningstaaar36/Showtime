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
from api.core.venue_ops import PatchError
from api.db.models import Run
from api.models import Attack, Fix, ScenarioEventIn
from api.orchestrator import sweep

router = APIRouter(prefix="/api/v1")


def run_out(row: Run) -> dict[str, Any]:
    """Run payload for the UI."""
    return {
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
    return run_out(row) | {"tier1": job.tier1.model_dump(mode="json") if job.tier1 else None}


@router.get("/runs/{run_id}")
def get_run(run_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Status, progress and result."""
    row = st.runs.get(run_id)
    if row is None:
        raise ApiException(404, "not_found", f"Run {run_id} does not exist.")
    return run_out(row)


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: str, st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """Recent runs of a project (without heavy fields)."""
    out = []
    for r in st.runs.list(project_id):
        d = run_out(r)
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
