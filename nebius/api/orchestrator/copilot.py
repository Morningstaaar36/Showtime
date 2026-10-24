"""Event Copilot: one sentence → real site (or designed venue) → event layout → estimates →
project → stress test. Yields progress steps so the UI can show the work as it happens."""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import AsyncIterator
from typing import Any

from api.adapters.osm import OsmUnavailable
from api.models.venue_spec import EventBrief
from api.orchestrator import venue_sources

log = logging.getLogger("showtime.copilot")


MAX_INDOOR_M2 = 15_000  # a single hall larger than 1.5 ha is not a building but a campus or park


def _area_m2(outline: list[list[float]]) -> float:
    """Approximate area of a [lat, lon] ring in m² (equirectangular)."""
    lat0 = sum(c[0] for c in outline) / len(outline)
    kx, ky = 111_320.0 * math.cos(math.radians(lat0)), 110_540.0
    pts = [(c[1] * kx, c[0] * ky) for c in outline]
    return (
        abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True))) / 2
    )


def _step(key: str, status: str, title: str, detail: str = "", **extra: Any) -> dict[str, Any]:
    return {"step": key, "status": status, "title": title, "detail": detail, **extra}


async def _site_from_place(st: Any, brief: EventBrief) -> tuple[dict[str, Any] | None, str]:
    """Find the named place and import it; (draft, description of what was found)."""
    assert brief.place
    try:
        hits = await st.osm.search(brief.place, limit=3)
    except OsmUnavailable as exc:
        return None, f"Place search failed: {exc}"
    if not hits:
        return None, f"“{brief.place}” was not found on the map."
    hit = hits[0]
    outline, sel_id, name = hit.get("outline"), None, hit["name"]
    mode = brief.setting
    if not outline or len(outline) < 4:
        try:
            got = (await st.osm.at_point(hit["lat"], hit["lon"]))["selection"]
        except OsmUnavailable:
            got = None
        if got:
            outline, sel_id = got["coords"], got["id"]
            name = got["name"] or name
            if got["kind"] == "building":
                mode = "indoor"
    if not outline or len(outline) < 4:
        return None, f"“{hit['name']}” is a point on the map, not an outline."
    if mode == "indoor" and _area_m2(outline) > MAX_INDOOR_M2:
        return None, (
            f"“{name}” is a site of {_area_m2(outline) / 10_000:.1f} ha, not one building, so an "
            "indoor hall was designed there. Pick the exact building on the map for its real "
            "footprint."
        )
    try:
        draft = await venue_sources.from_map(
            st, outline, mode=mode, name=name, people=brief.attendees, selected_id=sel_id
        )
    except (ValueError, OsmUnavailable) as exc:
        return None, f"The site could not be imported: {exc}"
    return draft, f"{hit['display_name'].split(',')[0]} · {mode}"


async def plan_event(st: Any, text: str) -> AsyncIterator[dict[str, Any]]:
    """Run the Copilot graph; each yielded dict is a progress update (the last has project_id)."""
    from api.orchestrator.copilot_graph import GRAPH  # the graph imports helpers from here

    thread = f"copilot-{uuid.uuid4().hex[:10]}"
    config = {"configurable": {"st": st, "thread_id": thread}}
    final: dict[str, Any] = {}
    try:
        async for mode, chunk in GRAPH.astream(
            {"text": text}, config, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield chunk
            else:
                final = chunk
    finally:
        try:
            GRAPH.checkpointer.delete_thread(thread)
        except Exception:  # checkpoints are only a cache here
            log.debug("could not drop checkpoints of %s", thread)
    if final.get("project_id"):
        yield {
            "step": "finished",
            "status": "done",
            "project_id": final["project_id"],
            "notes": final.get("notes", [])[:10],
            "review": final.get("review"),
        }
