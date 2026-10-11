"""Projects, venue versions, edits, validation, instant estimates and the countdown."""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.adapters.weather import WeatherUnavailable
from api.app.errors import ApiException
from api.app.routes_core import get_state
from api.app.state import AppState
from api.core.countdown import compute_countdown
from api.core.estimates import compute_estimates, scale_people
from api.core.extensions import HazardContext, HazardResult
from api.core.geometry import validate_venue
from api.core.scene import SceneInputError, inspect_scene, scene_snapshot
from api.core.score import planning_score, score_inputs
from api.core.templates import get_template
from api.db.models import Project, VenueVersion
from api.models import Attack, Fix, RunResult, ScenarioEventIn, Venue, VenuePatch
from api.models.scene import SceneFacts, SceneSnapshot
from api.orchestrator.projects import validation_for

router = APIRouter(prefix="/api/v1")


def project_out(st: AppState, p: Project) -> dict[str, Any]:
    """Project summary for lists and headers."""
    v = st.projects.version(p.id)
    venue = Venue.model_validate(v.venue)
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "template_id": p.template_id,
        "current_version": p.current_version,
        "can_undo": v.base_version is not None,
        "can_redo": bool(p.redo_stack),
        "sample": p.sample,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
        "mode": venue.mode,
        "people": venue.total_people(),
        "floors": len(venue.floors),
        "venue_name": venue.name,
        "exits": sum(len(f.exits) for f in venue.floors),
        # plan drawing for the card (without heavy extras such as map surroundings)
        "thumb": venue.model_dump(mode="json", exclude={"extensions"}),
    }


def version_out(v: VenueVersion, include_venue: bool = True) -> dict[str, Any]:
    """Venue version payload."""
    out: dict[str, Any] = {
        "version": v.version,
        "message": v.message,
        "author": v.author,
        "created_at": v.created_at.isoformat(),
        "venue_hash": v.venue_hash,
        "base_version": v.base_version,
        "patch": v.patch,
    }
    if include_venue:
        out["venue"] = v.venue
    return out


class ProjectIn(BaseModel):
    """New project from a template or an uploaded venue."""

    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    template_id: str | None = None
    venue: Venue | None = None


@router.get("/projects")
def list_projects(q: str | None = None, st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """All projects, newest first (optional name search)."""
    items = [project_out(st, p) for p in st.projects.list_projects()]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["name"].lower() or ql in i["description"].lower()]
    return items


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Create a project."""
    if body.venue is None and body.template_id is None:
        raise ApiException(422, "missing_venue", "Pick a template or upload a venue.")
    try:
        name = body.name or (
            body.venue.name if body.venue else get_template(body.template_id or "").name
        )
        p = st.projects.create(
            name, template_id=body.template_id, venue=body.venue, description=body.description
        )
    except KeyError as exc:
        raise ApiException(
            404, "unknown_template", f"Template {body.template_id} does not exist."
        ) from exc
    return project_out(st, p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Project with its current venue and validation."""
    p = st.projects.get(project_id)
    v = st.projects.version(project_id)
    venue = Venue.model_validate(v.venue)
    return {**project_out(st, p), "version": version_out(v), "validation": validation_for(venue)}


def _scene_error(exc: SceneInputError) -> ApiException:
    return ApiException(
        422,
        "invalid_scene",
        str(exc),
        "Correct the reported geometry, identifiers, or provenance and try again.",
        {"issues": [issue.model_dump(mode="json") for issue in exc.issues]},
    )


@router.get("/projects/{project_id}/scene", response_model=SceneSnapshot)
def get_scene(
    project_id: str,
    version: int | None = Query(default=None, ge=1),
    st: AppState = Depends(get_state),
) -> SceneSnapshot:
    """Full versioned scene JSON; the same geometry used by the editor and simulator."""
    row = st.projects.version(project_id, version)
    venue = Venue.model_validate(row.venue)
    try:
        return scene_snapshot(venue, project_id=project_id, version=row.version)
    except SceneInputError as exc:
        raise _scene_error(exc) from exc


@router.get("/projects/{project_id}/scene-facts", response_model=SceneFacts)
def get_scene_facts(
    project_id: str,
    version: int | None = Query(default=None, ge=1),
    include_routes: bool = True,
    st: AppState = Depends(get_state),
) -> SceneFacts:
    """Computed area, connectivity, point clearances, and bounded geometric routes."""
    row = st.projects.version(project_id, version)
    venue = Venue.model_validate(row.venue)
    try:
        return inspect_scene(
            venue, project_id=project_id, version=row.version, include_routes=include_routes
        )
    except SceneInputError as exc:
        raise _scene_error(exc) from exc


class ProjectPatchIn(BaseModel):
    """Rename / describe."""

    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str, body: ProjectPatchIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Rename a project."""
    p = st.projects.get(project_id)
    p = st.projects.rename(project_id, body.name or p.name, body.description)
    return project_out(st, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, st: AppState = Depends(get_state)) -> Response:
    """Delete a project."""
    st.projects.delete(project_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Copy a project."""
    return project_out(st, st.projects.duplicate(project_id))


@router.get("/projects/{project_id}/versions")
def versions(project_id: str, st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """Version history (without full venues)."""
    return [version_out(v, include_venue=False) for v in st.projects.versions(project_id)]


@router.get("/projects/{project_id}/versions/{version}")
def get_version(project_id: str, version: int, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """One version with its venue."""
    return version_out(st.projects.version(project_id, version))


def _after_edit(
    st: AppState, project_id: str, row: VenueVersion, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    p = st.projects.get(project_id)
    venue = Venue.model_validate(row.venue)
    with contextlib.suppress(Exception):  # plugin hooks never break an edit
        st.host.pm.hook.on_venue_changed(project_id=project_id, venue=venue, version=row.version)
    return {
        "project": project_out(st, p),
        "version": version_out(row),
        "validation": validation_for(venue),
        **(extra or {}),
    }


class PatchIn(BaseModel):
    """A patch from the UI (drag, inspector) or an agent."""

    patch: VenuePatch
    message: str = ""
    allow_new_errors: bool = False


@router.post("/projects/{project_id}/patch")
def patch_project(
    project_id: str, body: PatchIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Apply a patch and save a new version."""
    row, res = st.projects.apply(
        project_id, body.patch, body.message, allow_new_errors=body.allow_new_errors
    )
    return _after_edit(st, project_id, row, {"warnings": [w.model_dump() for w in res.warnings]})


@router.post("/projects/{project_id}/undo")
def undo(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Undo the last change."""
    return _after_edit(st, project_id, st.projects.undo(project_id))


@router.post("/projects/{project_id}/redo")
def redo(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Redo the last undone change."""
    return _after_edit(st, project_id, st.projects.redo(project_id))


@router.post("/projects/{project_id}/restore/{version}")
def restore(project_id: str, version: int, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Restore an older version as the current one."""
    return _after_edit(st, project_id, st.projects.restore(project_id, version))


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, st: AppState = Depends(get_state)) -> Response:
    """Download the project as `.showtime.zip`."""
    p = st.projects.get(project_id)
    data = st.projects.export_zip(project_id)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in p.name)[:60] or "project"
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.showtime.zip"'},
    )


@router.post("/projects/import", status_code=201)
async def import_project(
    file: UploadFile = File(...), st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Import a `.showtime.zip` (or a venue JSON / DXF through the importer plugins)."""
    data = await file.read(st.settings.upload_max_bytes + 1)
    if len(data) > st.settings.upload_max_bytes:
        raise ApiException(
            413,
            "too_large",
            f"The file is larger than {st.settings.upload_max_bytes // 1_000_000} MB.",
        )
    name = (file.filename or "").lower()
    if name.endswith(".zip"):
        try:
            return project_out(st, st.projects.import_zip(data))
        except ValueError as exc:
            raise ApiException(422, "bad_import", str(exc)) from exc
    for imp in st.registry.all("VenueImporter"):
        if any(name.endswith(ext) for ext in imp.file_extensions):
            try:
                venue = imp.import_bytes(data, file.filename or "venue")
            except ValueError as exc:
                raise ApiException(
                    422, "bad_import", str(exc), "Check the file and try again."
                ) from exc
            p = st.projects.create(venue.name, venue=venue)
            return project_out(st, p)
    raise ApiException(
        415,
        "unsupported_file",
        "This file type is not supported.",
        "Use a .showtime.zip export, a venue .json or a .dxf drawing.",
    )


# --- spec aliases: /venues/{id} == current venue of project {id} -------------------------


@router.post("/venues", status_code=201)
def create_venue(body: ProjectIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Create a venue (a project) from a template or JSON."""
    out = create_project(body, st)
    return {"venue": st.projects.venue(out["id"]).model_dump(), "project": out}


@router.get("/venues/{venue_id}")
def get_venue(venue_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Current venue."""
    return st.projects.venue(venue_id).model_dump()


@router.post("/venues/{venue_id}/patch")
def patch_venue(venue_id: str, body: PatchIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Alias of /projects/{id}/patch."""
    return patch_project(venue_id, body, st)


@router.post("/venues/{venue_id}/validate")
def validate(venue_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Geometry checks plus rule checks from enabled rule packs."""
    venue = st.projects.venue(venue_id)
    out = validation_for(venue)
    rules: list[dict[str, Any]] = []
    t1 = st.runs.estimate(venue) if out["ok"] else None
    for pack in st.registry.all("RulesPack"):
        try:
            rules.extend(r.model_dump() | {"pack": pack.id} for r in pack.check(venue, t1))
        except Exception as exc:
            st.host.mark_unhealthy(pack.id, str(exc))
    out["rules"] = rules
    return out


class Tier1In(BaseModel):
    """Instant estimate inputs ("Break it yourself" sends blocked exits)."""

    blocked_exits: list[str] = Field(default_factory=list)
    events: list[ScenarioEventIn] = Field(default_factory=list)
    attack: Attack | None = None
    fix: Fix | None = None


@router.post("/venues/{venue_id}/tier1")
def tier1(venue_id: str, body: Tier1In, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Instant estimate (formula), in milliseconds."""
    venue = st.projects.venue(venue_id)
    extra = [ScenarioEventIn(type="block_exit", exit_id=e, at_s=0) for e in body.blocked_exits]
    extra += body.events
    _check_events(st, venue, extra)
    try:
        res = st.runs.estimate(venue, body.attack, body.fix, extra)
    except ValueError as exc:
        raise ApiException(422, "invalid_scenario", str(exc)) from exc
    return res.model_dump(mode="json")


def _check_events(st: AppState, venue: Venue, events: list[ScenarioEventIn]) -> None:
    for ev in events:
        if not st.registry.has("ScenarioEvent", ev.type):
            raise ApiException(422, "unknown_event", f"Unknown event '{ev.type}'.")
        spec = st.registry.event(ev.type)
        problems = spec.validate_refs(venue, spec.params_model.model_validate(ev.model_dump()))
        if problems:
            raise ApiException(422, "invalid_event", problems[0])


# --- countdown --------------------------------------------------------------------------


class CountdownIn(BaseModel):
    """Countdown inputs. Manual values override the forecast/scenario."""

    run_id: str | None = None
    attack: Attack | None = None
    gust_ms: float | None = Field(default=None, ge=0, le=100)
    storm_gust_ms: float | None = Field(default=None, gt=0, le=100)
    hazard_time_s: float | None = Field(default=None, ge=0)
    rset_s: float | None = Field(default=None, gt=0)


@router.get("/projects/{project_id}/estimates")
def project_estimates(
    project_id: str, version: int | None = None, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Safe capacity, exits, staff, sanitation, fencing and budget for a venue version."""
    venue = st.projects.venue(project_id, version)
    est = compute_estimates(venue, st.registry, st.settings, st.settings.unit_costs or None)
    return est.model_dump(mode="json")


class WhatIfIn(BaseModel):
    """A what-if scenario on the current plan (nothing is saved)."""

    people_scale: float = Field(default=1.0, ge=0.1, le=4.0)
    speed_factor: float = Field(default=1.0, ge=0.3, le=1.0)
    blocked_exits: list[str] = Field(default_factory=list)
    version: int | None = None
    run_id: str | None = Field(default=None, description="use this run when nothing is changed")


@router.post("/projects/{project_id}/whatif")
def what_if(project_id: str, body: WhatIfIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Instant estimate, estimates and planning score for a what-if (crowd, speed, closed exits)."""
    venue = scale_people(st.projects.venue(project_id, body.version), body.people_scale)
    events = [ScenarioEventIn(type="block_exit", exit_id=e, at_s=0) for e in body.blocked_exits]
    if body.speed_factor < 0.999:
        events.append(ScenarioEventIn(type="slowdown", factor=body.speed_factor, at_s=0))
    _check_events(st, venue, events)
    t1 = st.runs.estimate(venue, None, None, events)
    closed = set(body.blocked_exits)
    est_venue = venue.model_copy(deep=True)
    for f in est_venue.floors:
        for e in f.exits:
            e.blocked = e.blocked or e.id in closed
    s = st.settings
    est = compute_estimates(est_venue, st.registry, s, s.unit_costs or None)
    metrics, basis = t1.metrics, "Instant estimate (formula)"
    unchanged = body.people_scale == 1.0 and body.speed_factor >= 0.999 and not closed
    if body.run_id and unchanged:
        row = st.runs.get(body.run_id)
        if row is not None and row.result and row.status in ("ok", "partial"):
            metrics = RunResult.model_validate(row.result).metrics
            basis = f"Confirmed by simulation (run {body.run_id[-6:]})"
    checks = validate_venue(venue).checks
    target = s.target_evac_indoor_s if venue.mode == "indoor" else s.target_evac_outdoor_s
    score = planning_score(
        metrics,
        target_evac_s=target,
        warn_ppm2=s.density_warn_ppm2,
        danger_ppm2=s.density_danger_ppm2,
        errors=sum(c.severity == "error" for c in checks),
        warnings=sum(c.severity == "warning" for c in checks),
        basis=basis,
        **score_inputs(est),
    )
    return {
        "metrics": metrics.model_dump(mode="json"),
        "hotspots": [h.model_dump(mode="json") for h in t1.hotspots[:5]],
        "capacity": est.capacity.model_dump(mode="json"),
        "lines": [ln.model_dump(mode="json") for ln in est.lines],
        "budget_total": est.budget_total,
        "currency": est.currency,
        "score": score.model_dump(mode="json"),
        "basis": basis,
        "people": venue.total_people(),
    }


@router.post("/projects/{project_id}/countdown")
async def countdown(
    project_id: str, body: CountdownIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Latest safe time to start evacuating, with every input traceable."""
    venue = st.projects.venue(project_id)
    s = st.settings
    rset, rset_source = body.rset_s, "entered by you" if body.rset_s else ""
    if rset is None and body.run_id:
        row = st.runs.get(body.run_id)
        if row is not None and row.result:
            res = RunResult.model_validate(row.result)
            rset = res.metrics.evac_time_p95_s or res.metrics.extra.get("rset_extrapolated_s")
            label = (
                "Confirmed by simulation"
                if res.tier == 3
                else ("Ranking run (partial)" if res.tier == 2 else "Instant estimate")
            )
            rset_source = f"{label} (run {res.run_id})"
    if rset is None:
        est = st.runs.estimate(venue, body.attack)
        rset = est.metrics.evac_time_p95_s
        rset_source = "Instant estimate (formula)"
    manual: dict[str, float] = {}
    for k in ("gust_ms", "storm_gust_ms", "hazard_time_s"):
        val = getattr(body, k)
        if val is not None:
            manual[k] = float(val)

    async def forecast(lat: float, lon: float, day: str, tz: str) -> dict[str, Any]:
        from datetime import date

        return await st.weather.hourly_gusts(lat, lon, tz, date.fromisoformat(day))

    ctx = HazardContext(
        venue=venue,
        attack=body.attack,
        manual=manual,
        get_forecast=forecast,
        settings=s.public_dict(),
    )
    hazards: list[HazardResult] = []
    errors: list[str] = []
    for src in st.registry.all("HazardSource"):
        if venue.mode not in src.modes:
            continue
        try:
            res_h = await src.evaluate(ctx)
        except WeatherUnavailable as exc:
            errors.append(str(exc))
            continue
        except Exception as exc:
            st.host.mark_unhealthy(src.id, str(exc))
            errors.append(f"{src.label}: {exc}")
            continue
        if res_h is not None:
            hazards.append(res_h)
    timed = [h for h in hazards if h.t_hazard_s is not None]
    chosen = (
        min(timed, key=lambda h: h.t_hazard_s or 0.0)
        if timed
        else (hazards[0] if hazards else None)
    )
    cd = compute_countdown(
        chosen,
        rset,
        s.pre_movement_s,
        s.safety_factor,
        rset_source,
        venue.location.event_start if venue.location else None,
    )
    return {
        "countdown": cd.model_dump(),
        "hazards": [h.model_dump() for h in hazards],
        "errors": errors,
        "manual_input_needed": bool(errors) and not timed,
        "timezone": venue.location.timezone if venue.location else "UTC",
    }
