"""New venues from a description or from the map (OpenStreetMap)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from api.adapters.llm import BudgetExceeded, LLMError
from api.adapters.osm import OsmUnavailable
from api.agents.base import AgentUnavailable
from api.app.errors import ApiException, llm_unavailable
from api.app.routes_core import get_state
from api.app.state import AppState
from api.core.building_gen import infer_use, map_levels
from api.models import EventKind
from api.models.venue_spec import MAX_LEVELS
from api.orchestrator import copilot, venue_sources

router = APIRouter(prefix="/api/v1")


class DesignIn(BaseModel):
    """A plain-language description of the venue."""

    text: str = Field(min_length=10, max_length=2000)
    # a change to an earlier preview, in words, and that preview's layout
    # (venue.extensions.generated.spec): the designer revises it instead of starting over
    request: str = Field(default="", max_length=1000)
    previous: dict[str, Any] | None = None


class FromMapIn(BaseModel):
    """A selected building or area: outline as [[lat, lon], ...]."""

    outline: list[list[float]] = Field(min_length=4, max_length=2000)
    mode: Literal["indoor", "outdoor"] = "outdoor"
    name: str = Field(default="", max_length=120)
    people: int | None = Field(default=None, ge=0, le=100_000)
    selected_id: str | None = Field(default=None, max_length=40)
    # buildings: storeys (default: the map's building:levels, else 1), what the building is
    # (default: from its map tags), rooms off a corridor or open floors, storey height
    levels: int | None = Field(default=None, ge=1, le=MAX_LEVELS)
    use: EventKind | None = None
    interior: Literal["open", "rooms", "dining"] | None = None
    floor_height_m: float = Field(default=3.5, ge=2.4, le=8.0)
    # open areas: what happens there (a rally, a festival, ...)
    event_kind: EventKind | None = None


def _osm_error(exc: OsmUnavailable) -> ApiException:
    return ApiException(
        503, "map_unavailable", str(exc), "Or use “Draw an area”: it works without map details."
    )


@router.post("/venues/design")
async def design_venue(body: DesignIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Designer agent + solver: description → venue preview with checks."""
    try:
        return await venue_sources.design(
            st, body.text, request=body.request, previous=body.previous
        )
    except ValidationError as exc:
        raise ApiException(
            422, "bad_layout", "The earlier layout could not be read.", "Describe it again."
        ) from exc
    except BudgetExceeded as exc:
        raise ApiException(429, "budget", str(exc), "Raise the token budget in Settings.") from exc
    except (LLMError, AgentUnavailable) as exc:
        raise llm_unavailable(st.llm, "The language model isn't answering.") from exc


@router.get("/places/search")
async def search_places(
    q: str = Query(min_length=2, max_length=200), st: AppState = Depends(get_state)
) -> list[dict[str, Any]]:
    """Places matching a name or address (OpenStreetMap Nominatim)."""
    try:
        return await st.osm.search(q)
    except OsmUnavailable as exc:
        raise _osm_error(exc) from exc


@router.get("/places/features")
async def place_features(
    south: float = Query(ge=-90, le=90),
    west: float = Query(ge=-180, le=180),
    north: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    st: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Buildings, open areas, paths, fences and entrances in a box (OpenStreetMap Overpass)."""
    if north <= south or east <= west:
        raise ApiException(422, "bad_box", "The box is empty.", "Drag the map and try again.")
    try:
        return await st.osm.features(south, west, north, east)
    except OsmUnavailable as exc:
        raise _osm_error(exc) from exc


@router.get("/places/at")
async def place_at(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    st: AppState = Depends(get_state),
) -> dict[str, Any]:
    """The building or open area under a clicked point (and the features around it).

    A building also says how many storeys the map lists and what it is used for, so the
    import form can start from them.
    """
    try:
        out = await st.osm.at_point(lat, lon)
    except OsmUnavailable as exc:
        raise _osm_error(exc) from exc
    sel = out.get("selection")
    if isinstance(sel, dict) and sel.get("kind") == "building":
        tags = sel.get("tags") or {}
        sel["levels"] = map_levels(tags)
        sel["use"] = infer_use(tags)
    return out


@router.post("/venues/from-map")
async def venue_from_map(body: FromMapIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Selected building (indoor) or area (open-air) → venue preview with checks."""
    try:
        return await venue_sources.from_map(
            st,
            body.outline,
            mode=body.mode,
            name=body.name.strip() or "Venue from map",
            people=body.people,
            selected_id=body.selected_id,
            levels=body.levels,
            use=body.use,
            interior=body.interior,
            floor_height_m=body.floor_height_m,
            event_kind=body.event_kind,
        )
    except OsmUnavailable as exc:
        raise _osm_error(exc) from exc
    except ValueError as exc:
        raise ApiException(
            422, "bad_selection", str(exc), "Pick another building or area."
        ) from exc


class CopilotIn(BaseModel):
    """One sentence: what, where, when, how many."""

    text: str = Field(min_length=8, max_length=1500)


@router.post("/copilot/plan")
async def copilot_plan(body: CopilotIn, st: AppState = Depends(get_state)) -> StreamingResponse:
    """Event Copilot as a stream of JSON lines (one progress update per line)."""

    async def lines() -> AsyncIterator[bytes]:
        try:
            async for step in copilot.plan_event(st, body.text):
                yield (json.dumps(step) + "\n").encode()
        except BudgetExceeded as exc:
            yield (
                json.dumps({"step": "error", "status": "failed", "title": str(exc)}) + "\n"
            ).encode()
        except (LLMError, AgentUnavailable):
            msg = "The language model isn't answering. Check the provider badge (top right)."
            yield (json.dumps({"step": "error", "status": "failed", "title": msg}) + "\n").encode()

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.get("/copilot/graph")
def copilot_graph() -> dict[str, Any]:
    """The Copilot's LangGraph structure (nodes and edges) for the UI to draw."""
    from api.orchestrator.copilot_graph import graph_shape

    return graph_shape()


@router.get("/projects/{project_id}/review")
def project_review(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """The safety officer's actions for this project (empty if none yet)."""
    from api.orchestrator.copilot_graph import load_review

    return load_review(st, project_id) or {"summary": "", "actions": []}


@router.post("/projects/{project_id}/review")
async def run_review(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Ask the safety officer to review the current plan now."""
    from api.orchestrator.copilot_graph import review_project

    return await review_project(st, project_id)
