"""Health, features, plugins, settings, templates, weather, stage check and validation."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from api.adapters.weather import WeatherUnavailable
from api.app.errors import ApiException
from api.app.state import AppState
from api.core.event_profiles import event_kinds
from api.core.templates import list_templates
from api.core.validation import load_validation
from api.models import StageParams
from api.models.validation import SimulatorValidation

router = APIRouter(prefix="/api/v1")


def get_state(request: Request) -> AppState:
    """Dependency: the application container."""
    return request.app.state.showtime  # type: ignore[no-any-return]


@router.get("/health")
async def health(st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Status of every provider and plugin."""
    llm, sandbox, search = await asyncio.gather(
        st.llm.health(), st.runner.health(), st.search.health()
    )
    weather = {
        "ok": not st.settings.offline,
        "detail": "Open-Meteo (cached)"
        if not st.settings.offline
        else "Offline: manual gust input only",
    }
    plugins = [
        {
            "id": p.id,
            "name": p.name,
            "version": p.version,
            "enabled": p.enabled,
            "healthy": p.healthy,
            "error": p.error,
            "provides": p.provides,
            "registered": p.registered,
            "source": p.source,
        }
        for p in st.host.statuses.values()
    ]
    ok = llm["ok"] and sandbox["ok"]
    return {
        "ok": ok,
        "providers": {
            "llm": {
                **llm,
                "provider": st.settings.llm_provider,
                "label": st.settings.llm_label,
                "models": {
                    r: st.settings.model_for(r)  # type: ignore[arg-type]
                    for r in ("fast", "long", "main", "judge")
                },
            },
            "sandbox": {**sandbox, "provider": st.settings.sandbox_provider},
            "search": search,
            "weather": weather,
        },
        "plugins": plugins,
        "version": "0.1.0",
    }


@router.get("/features")
def features(st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Enabled plugins and extension keys (the UI shows only what is enabled)."""
    reg = st.registry
    return {
        "plugins": {p.id: p.enabled and p.healthy for p in st.host.statuses.values()},
        "patch_ops": reg.keys("PatchOp"),
        "events": [
            {
                "type": e.type,
                "label": e.label,
                "description": e.description,
                "schema": e.params_model.model_json_schema(),
            }
            for e in reg.all("ScenarioEvent")
        ],
        "hazards": reg.keys("HazardSource"),
        "exporters": [
            {"id": e.id, "label": e.label, "media_type": e.media_type, "file_ext": e.file_ext}
            for e in reg.all("Exporter")
        ],
        "importers": [
            {"id": i.id, "label": i.label, "file_extensions": i.file_extensions}
            for i in reg.all("VenueImporter")
        ],
        "rules": reg.keys("RulesPack"),
        "incidents": [
            {"id": s.id, "label": s.label, "count": s.count()} for s in reg.all("IncidentSource")
        ],
        "search_live": st.search.live,
        "provider": st.settings.llm_provider,
    }


@router.get("/plugins")
def plugins(st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """Discovered plugins with status (also used by `make plugins`)."""
    return [p.__dict__ for p in st.host.statuses.values()]


@router.get("/settings")
def get_settings_route(st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Settings safe for the browser (no keys) plus UI preferences."""
    return {
        "effective": st.settings.public_dict(),
        "ui": st.ui,
        "defaults": st.base_settings.public_dict(),
    }


class SettingsIn(BaseModel):
    """Partial settings update from the Settings screen."""

    values: dict[str, Any]


@router.put("/settings")
def put_settings(body: SettingsIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Validate and store settings."""
    try:
        saved = st.save_overrides(body.values)
    except ValueError as exc:
        raise ApiException(
            422, "invalid_settings", str(exc).splitlines()[0], "Check the highlighted value."
        ) from exc
    return {"saved": saved, "effective": st.settings.public_dict(), "ui": st.ui}


@router.get("/event-kinds")
def event_kind_list() -> list[dict[str, Any]]:
    """Kinds of event or building: copy, usual people mix, usual interior."""
    return event_kinds()


@router.get("/templates")
def templates() -> list[dict[str, Any]]:
    """Template venues (summary + full venue)."""
    out = []
    for t in list_templates():
        out.append(
            {
                "id": t.venue_id,
                "name": t.name,
                "description": t.description,
                "mode": t.mode,
                "people": t.total_people(),
                "floors": len(t.floors),
                "exits": sum(len(f.exits) for f in t.floors),
                "venue": t.model_dump(),
            }
        )
    return out


@router.get("/weather")
async def weather(
    project_id: str, day: str | None = None, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Hourly gust forecast for the venue location and event date."""
    venue = st.projects.venue(project_id)
    snap = (venue.extensions or {}).get("weather_snapshot")
    if snap and not day:
        return dict(snap, snapshot=True)
    if venue.location is None:
        raise ApiException(
            400,
            "no_location",
            "This venue has no location.",
            "Set a location in the venue settings.",
        )
    start = (
        date.fromisoformat(day)
        if day
        else (
            datetime.fromisoformat(venue.location.event_start).date()
            if venue.location.event_start
            else date.today()
        )
    )
    try:
        return await st.weather.hourly_gusts(
            venue.location.lat, venue.location.lon, venue.location.timezone, start
        )
    except WeatherUnavailable as exc:
        raise ApiException(
            503, "weather_unavailable", str(exc), "Enter the expected gust speed by hand."
        ) from exc


class StageCheckIn(BaseModel):
    """Either a project (uses its stage) or explicit stage parameters."""

    project_id: str | None = None
    stage: StageParams | None = None


@router.post("/stage-check")
def stage_check(body: StageCheckIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Screening wind limit of a ballasted stage roof (Pynite)."""
    stage = body.stage
    if stage is None and body.project_id:
        stage = st.projects.venue(body.project_id).stage
    if stage is None:
        raise ApiException(
            400,
            "no_stage",
            "This venue has no stage structure.",
            "Stage checks apply to open-air venues with a stage.",
        )
    if not st.registry.has("HazardSource", "hazard_wind"):
        raise ApiException(
            503,
            "feature_off",
            "The wind hazard plugin is turned off.",
            "Enable it in Settings › Plugins.",
        )
    src = st.registry.get("HazardSource", "hazard_wind")
    return src.stage_check(stage).model_dump()  # type: ignore[no-any-return]


@router.get("/glossary")
def glossary(q: str | None = Query(default=None)) -> list[dict[str, str]]:
    """Terms used in the UI (Help screen)."""
    from api.core.glossary import GLOSSARY

    items = GLOSSARY
    if q:
        ql = q.lower()
        items = [g for g in items if ql in g["term"].lower() or ql in g["definition"].lower()]
    return items


@router.get("/validation", response_model=SimulatorValidation)
def validation() -> SimulatorValidation:
    """Simulator vs a real bottleneck experiment (api/data/validation.json, `make validate`)."""
    data = load_validation()
    if data is None:
        raise ApiException(
            404,
            "not_found",
            "The simulator validation has not been generated.",
            "Run: make get-data && make validate",
        )
    return data
