"""New venues from a description (designer agent + solver) or from OpenStreetMap."""

from __future__ import annotations

import logging
from typing import Any, Literal

from api.adapters.osm import OsmUnavailable
from api.agents.base import AgentEnv
from api.agents.venue_designer import design_venue
from api.core.geometry import validate_venue
from api.core.osm_venue import venue_from_osm
from api.models import Location, Venue

log = logging.getLogger("showtime.venue_sources")
_PAD_DEG = 0.0012  # load ~130 m around the outline: crossing paths and the neighbourhood


def _checks(venue: Venue) -> list[dict[str, Any]]:
    return [c.model_dump() for c in validate_venue(venue).checks if c.severity != "info"]


async def _locate(st: Any, venue: Venue, place: str | None) -> tuple[Venue, list[str]]:
    """Fill in coordinates (from a place name) and the local time zone."""
    notes: list[str] = []
    loc = venue.location
    if loc is None and place:
        try:
            hits = await st.osm.search(place, limit=1)
        except OsmUnavailable:
            hits = []
        if hits:
            loc = Location(lat=round(hits[0]["lat"], 6), lon=round(hits[0]["lon"], 6))
            notes.append(
                f"Placed in {hits[0]['display_name'].split(',')[0]} for weather and local time."
            )
    if loc is None:
        return venue, notes
    tz = await st.weather.timezone_for(loc.lat, loc.lon)
    return venue.model_copy(update={"location": loc.model_copy(update={"timezone": tz})}), notes


async def design(st: Any, text: str) -> dict[str, Any]:
    """Description → venue preview (not saved; the UI creates the project)."""
    env = AgentEnv(llm=st.llm, project_id=None, on_usage=st.usage.add)
    out = await design_venue(env, text)
    if out.venue is None:
        return {"status": "failed", "problems": out.problems, "notes": [], "assumptions": []}
    venue, notes = await _locate(st, out.venue, out.spec.location if out.spec else None)
    return {
        "status": out.status,
        "venue": venue.model_dump(mode="json"),
        "notes": out.notes + notes,
        "assumptions": out.assumptions,
        "problems": out.problems,
        "checks": _checks(venue),
        "model": out.call.model if out.call else "",
    }


async def from_map(
    st: Any,
    outline: list[list[float]],
    *,
    mode: Literal["indoor", "outdoor"],
    name: str,
    people: int | None,
    selected_id: str | None,
) -> dict[str, Any]:
    """Selected building or area (lat/lon outline) → venue preview."""
    lats = [c[0] for c in outline]
    lons = [c[1] for c in outline]
    degraded: list[str] = []
    try:
        feats = await st.osm.features(
            min(lats) - _PAD_DEG, min(lons) - _PAD_DEG, max(lats) + _PAD_DEG, max(lons) + _PAD_DEG
        )
    except OsmUnavailable as exc:  # still build from the outline alone
        log.warning("map details unavailable: %s", exc)
        feats = {"features": [], "attribution": "© OpenStreetMap contributors (ODbL)"}
        degraded.append(
            "Map details (buildings, paths, entrances) could not be loaded, so only the outline "
            "was used. Rebuild later for a fuller model, or add exits and obstacles by hand."
        )
    imp = venue_from_osm(
        feats["features"], outline, mode=mode, name=name, people=people, selected_id=selected_id
    )
    venue, notes = await _locate(st, imp.venue, None)
    return {
        "status": "built",
        "venue": venue.model_dump(mode="json"),
        "notes": degraded + imp.notes + notes,
        "assumptions": [],
        "problems": [],
        "checks": _checks(venue),
        "attribution": feats.get("attribution", ""),
    }
