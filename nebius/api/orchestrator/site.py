"""The real site of a building, from the map: its outline, size and storeys, and its neighbours.

A real case or a description names a place (coordinates, or a name to look up). The building
under that point is fetched from OpenStreetMap; it is accepted only when its size fits what the
description says (a point a few metres off must not swap in the building next door), and
everything found or not found is said in the notes. The designer then draws the building at its
real size, and the neighbours stand around it in the 3D view.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from api.adapters.osm import OsmUnavailable
from api.core.building_gen import map_levels
from api.core.extensions import geometry as geo
from api.core.osm_venue import Projector

log = logging.getLogger("showtime.site")

AREA_FIT = (
    0.4,
    2.5,
)  # a building whose area is outside these shares of the described one is not it
CONTEXT_M = 120.0  # neighbours kept within this distance
MAX_CONTEXT = 120


@dataclass
class Site:
    """What the map says about the building at a place."""

    lat: float
    lon: float
    source: str  # where the outline came from, said to the organizer
    width_m: float | None = None  # along east-west once lined up
    depth_m: float | None = None
    turned_deg: float = 0.0  # the building was turned by this much to line up with the axes
    levels: int | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    neighbours: list[dict[str, Any]] = field(default_factory=list)  # around (0,0)-(W,D)
    notes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.width_m is not None

    def brief(self) -> str:
        """The site in a sentence for the designer."""
        if not self.found:
            return ""
        levels = f", {self.levels} storeys tagged" if self.levels else ""
        return (
            f"The real building ({self.source}) measures about {self.width_m:.1f} m east-west by "
            f"{self.depth_m:.1f} m north-south{levels}: use these as width_m and depth_m."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "source": self.source,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "turned_deg": round(self.turned_deg, 1),
            "levels": self.levels,
            "notes": self.notes,
        }


def _lined_up(p: Polygon) -> float:
    """The turn (degrees, within ±45) that lines the building's long side up with an axis."""
    rect = p.minimum_rotated_rectangle
    pts = list(rect.exterior.coords)[:4]
    (ax, ay), (bx, by) = max(
        ((pts[i], pts[(i + 1) % 4]) for i in range(2)), key=lambda e: math.dist(*e)
    )
    ang = math.degrees(math.atan2(by - ay, bx - ax))
    while ang > 45:
        ang -= 90
    while ang <= -45:
        ang += 90
    return -ang


async def find_site(
    st: Any,
    *,
    lat: float | None = None,
    lon: float | None = None,
    place: str | None = None,
    described_m2: float | None = None,
) -> Site | None:
    """The building at a point (or at a place name), or None when there is no place at all."""
    notes: list[str] = []
    if lat is None or lon is None:
        if not place:
            return None
        try:
            hits = await st.osm.search(place, limit=1)
        except OsmUnavailable as exc:
            log.info("place search unavailable: %s", exc)
            hits = []
        if not hits:
            return None
        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        notes.append(f"Found “{hits[0]['display_name'].split(',')[0]}” on the map.")
    site = Site(lat=lat, lon=lon, source="no building outline", notes=notes)
    try:
        picked = await st.osm.at_point(lat, lon)
    except OsmUnavailable:
        site.notes.append("The map servers were busy, so the described size was used.")
        return site
    sel = picked.get("selection")
    if not sel or sel.get("kind") != "building":
        site.notes.append(
            "OpenStreetMap has no building outline at this point; the described size was used."
        )
        return site
    pr = Projector(lat, lon)
    outline = orient(geo.to_polygon([pr.xy(c[0], c[1]) for c in sel["coords"]]).buffer(0), 1.0)
    if described_m2 and not (AREA_FIT[0] <= outline.area / described_m2 <= AREA_FIT[1]):
        site.notes.append(
            f"The building OpenStreetMap has at this point covers {outline.area:.0f} m², far from "
            f"the described {described_m2:.0f} m², so it is probably a neighbour; the described "
            "size was used."
        )
        return site
    turn = _lined_up(outline)
    c = outline.centroid
    lined = rotate(outline, turn, origin=c)
    x0, y0, x1, y1 = lined.bounds
    site.width_m, site.depth_m = round(x1 - x0, 1), round(y1 - y0, 1)
    site.turned_deg = turn
    site.tags = dict(sel.get("tags") or {})
    site.levels = map_levels(site.tags)
    site.source = f"OpenStreetMap way {sel['id']}" if sel.get("id") else "OpenStreetMap"
    if abs(turn) > 1:
        site.notes.append(
            f"The building was turned {abs(turn):.0f}° to line up with the drawing; north is "
            "that much off in the plan."
        )
    site.neighbours = await _neighbours(st, pr, outline, c, turn, (x0, y0), sel.get("id"))
    return site


async def _neighbours(
    st: Any,
    pr: Projector,
    outline: Polygon,
    c: Any,
    turn: float,
    origin: tuple[float, float],
    own_id: Any,
) -> list[dict[str, Any]]:
    """Buildings around it, in the venue's frame (the building's box starts at 0,0)."""
    pad = CONTEXT_M / 111_000
    lat0, lon0 = pr.latlon(*outline.bounds[:2])
    lat1, lon1 = pr.latlon(*outline.bounds[2:])
    try:
        data = await st.osm.features(lat0 - pad, lon0 - pad * 1.2, lat1 + pad, lon1 + pad * 1.2)
    except OsmUnavailable:
        return []
    out: list[tuple[float, dict[str, Any]]] = []
    for f in data.get("features", []):
        if f.get("kind") != "building" or not f.get("closed") or f.get("id") == own_id:
            continue
        b = orient(geo.to_polygon([pr.xy(p[0], p[1]) for p in f["coords"]]).buffer(0), 1.0)
        if b.is_empty or b.intersection(outline).area > 0.5 * b.area:
            continue
        d = b.distance(outline)
        if d > CONTEXT_M:
            continue
        local = translate(rotate(b, turn, origin=c), -origin[0], -origin[1])
        if not isinstance(local, Polygon):
            continue
        tags = f.get("tags") or {}
        levels = map_levels(tags)
        height = float(tags["height"]) if _num(tags.get("height")) else (levels or 2) * 3.2
        out.append(
            (d, {"polygon": geo.to_points(local.simplify(0.4)), "height_m": min(height, 80.0),
                 "name": f.get("name") or ""})
        )  # fmt: skip
    out.sort(key=lambda t: t[0])
    return [n for _, n in out[:MAX_CONTEXT]]


def _num(v: Any) -> bool:
    try:
        float(str(v).split()[0])
    except (ValueError, IndexError):
        return False
    return True
