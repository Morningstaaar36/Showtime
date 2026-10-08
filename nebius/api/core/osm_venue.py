"""OpenStreetMap features + a selected outline → Venue.

A building becomes an indoor venue (its footprint, with exits at mapped entrances). An open
area (park, square, campus, or a drawn box) becomes an open-air venue: buildings inside are
obstacles, fences are barriers, and exits sit where paths and gates cross the edge.
Coordinates are projected to metres around the outline's south-west corner; north stays up.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from api.core.extensions import geometry as geo
from api.models import Exit, Floor, Location, Obstacle, Venue, Zone

MAX_AREA_M2 = 400_000  # 40 ha, about 630 m × 630 m
MAX_SIDE_M = 1000
DEFAULT_DENSITY_PPM2 = {"indoor": 1.0, "outdoor": 1.5}
_PATH_WIDTH_M = {
    "footway": 3,
    "path": 3,
    "steps": 2,
    "cycleway": 3,
    "pedestrian": 6,
    "service": 4,
    "residential": 6,
    "living_street": 5,
    "unclassified": 6,
    "tertiary": 8,
    "secondary": 8,
    "primary": 8,
    "track": 3,
    "corridor": 2,
}
MAX_EXITS = 12
CONTEXT_M = 150.0  # neighbouring buildings drawn around the venue
MAX_CONTEXT = 400
GAP_CLOSE_M = 0.6  # half of the narrowest passage kept between buildings


@dataclass
class OsmImport:
    """Imported venue plus what was assumed or left out."""

    venue: Venue
    notes: list[str] = field(default_factory=list)


class Projector:
    """lat/lon ↔ local metres (equirectangular around an origin; fine below a few km)."""

    def __init__(self, lat0: float, lon0: float) -> None:
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111_320.0 * math.cos(math.radians(lat0))
        self.ky = 110_540.0

    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        """Metres east and north of the origin."""
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def latlon(self, x: float, y: float) -> tuple[float, float]:
        """Inverse of `xy`."""
        return (self.lat0 + y / self.ky, self.lon0 + x / self.kx)


def _poly(coords: list[list[float]], pr: Projector) -> Polygon:
    p = geo.to_polygon([pr.xy(c[0], c[1]) for c in coords])
    return orient(p.buffer(0) if not p.is_valid else p, 1.0)


def _height(tags: dict[str, Any], per_level: float = 3.0, default: float = 6.0) -> float:
    """Building height from `building:levels` or `height` (metres); default if unknown."""
    lv = re.match(r"\d+", str(tags.get("building:levels", "")))
    if lv and int(lv.group(0)) > 0:
        return min(per_level * int(lv.group(0)), 80.0)
    h = re.match(r"\s*([\d.]+)", str(tags.get("height", "")))
    if h:
        try:
            v = float(h.group(1))
        except ValueError:
            v = 0.0
        if v >= 2:
            return min(v, 80.0)
    return default


def _width(tags: dict[str, Any], default: float) -> float:
    m = re.match(r"^\s*([\d.]+)", str(tags.get("width", "")))
    if m:
        try:
            return max(0.8, min(float(m.group(1)), 20.0))
        except ValueError:
            pass
    return default


def exit_at(
    walk: Polygon, pt: Point, width: float
) -> tuple[list[tuple[float, float]], float] | None:
    """Exit rectangle on the boundary segment nearest `pt`, just inside the outline."""
    ring = list(walk.exterior.coords)
    best: tuple[float, int] = (math.inf, 0)
    for i in range(len(ring) - 1):
        d = LineString([ring[i], ring[i + 1]]).distance(pt)
        if d < best[0]:
            best = (d, i)
    (ax, ay), (bx, by) = ring[best[1]], ring[best[1] + 1]
    seg = math.hypot(bx - ax, by - ay)
    width = min(width, seg - 0.2)
    if width < 0.8:
        return None
    tx, ty = (bx - ax) / seg, (by - ay) / seg
    nx, ny = -ty, tx  # inward for a counter-clockwise ring
    s = (pt.x - ax) * tx + (pt.y - ay) * ty
    s = min(max(s, width / 2 + 0.1), seg - width / 2 - 0.1)
    cx, cy = ax + tx * s, ay + ty * s
    h = width / 2
    pts = [
        (cx - tx * h + nx * 0.02, cy - ty * h + ny * 0.02),
        (cx + tx * h + nx * 0.02, cy + ty * h + ny * 0.02),
        (cx + tx * h + nx * 0.42, cy + ty * h + ny * 0.42),
        (cx - tx * h + nx * 0.42, cy - ty * h + ny * 0.42),
    ]
    rect = Polygon(pts)
    if not walk.buffer(1e-6).contains(rect):
        return None
    return [(round(x, 3), round(y, 3)) for x, y in pts], round(width, 2)


def _auto_exits(walk: Polygon, width: float) -> list[Point]:
    """Two exits on long edges, as far apart as possible (used when the map shows none)."""
    ring = list(walk.exterior.coords)
    edges = sorted(
        (LineString([ring[i], ring[i + 1]]) for i in range(len(ring) - 1)),
        key=lambda e: e.length,
        reverse=True,
    )
    usable = [e for e in edges if e.length >= width + 0.5] or edges[:1]
    first = usable[0].interpolate(0.5, normalized=True)
    second = max(
        usable[1:6] or usable, key=lambda e: e.interpolate(0.5, normalized=True).distance(first)
    )
    pts = [first]
    other = second.interpolate(0.5, normalized=True)
    if other.distance(first) > width:
        pts.append(other)
    return pts


def _place_exits(
    walk: Polygon,
    candidates: list[tuple[Point, float, str]],
    prefix: str,
    notes: list[str],
    blocked: Any = None,
) -> list[Exit]:
    """Exits from (point, width, label) candidates: widest first, no overlaps, at most 12."""
    exits: list[Exit] = []
    taken: list[Polygon] = []
    for pt, width, label in sorted(candidates, key=lambda c: -c[1]):
        if len(exits) >= MAX_EXITS:
            notes.append(f"Kept the {MAX_EXITS} widest openings; add more by hand if needed.")
            break
        got = exit_at(walk, pt, width)
        if got is None:
            continue
        pts, w = got
        poly = Polygon(pts)
        if blocked is not None and poly.buffer(0.3).intersects(blocked):
            continue  # the opening is behind a building or fence
        if any(poly.buffer(1.0).intersects(t) for t in taken):
            continue
        taken.append(poly)
        n = len(exits) + 1
        name = label or f"Exit {n}"
        same = sum(1 for e in exits if (e.label or "").split(" (")[0] == name)
        if same:
            name = f"{name} ({same + 1})"
        exits.append(Exit(id=f"{prefix}_{n}", polygon=pts, width_m=w, label=name))
    return exits


def _context(
    features: list[dict[str, Any]], walk: Polygon, pr: Projector, selected_id: str | None
) -> list[dict[str, Any]]:
    """Buildings around the venue (not part of it): footprint and height, for the 3D view."""
    out: list[tuple[float, dict[str, Any]]] = []
    for f in features:
        if f["kind"] != "building" or not f["closed"] or f["id"] == selected_id:
            continue
        b = _poly(f["coords"], pr)
        if b.is_empty or b.intersection(walk).area > 0.5 * b.area:
            continue  # inside the venue: it is an obstacle there
        d = b.distance(walk)
        if d > CONTEXT_M:
            continue
        h = _height(f["tags"], per_level=3.2)
        pts = geo.to_points(orient(b.simplify(0.4), 1.0))
        out.append((d, {"polygon": pts, "height_m": min(h, 80.0), "name": f["name"]}))
    out.sort(key=lambda t: t[0])
    return [c for _, c in out[:MAX_CONTEXT]]


def _parts(geom: Any) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def venue_from_osm(
    features: list[dict[str, Any]],
    outline: list[list[float]],
    *,
    mode: Literal["indoor", "outdoor"],
    name: str,
    people: int | None = None,
    selected_id: str | None = None,
    levels_note: bool = True,
) -> OsmImport:
    """Build a venue from an outline ([[lat, lon], ...]) and the features around it."""
    notes: list[str] = []
    lat0 = min(c[0] for c in outline)
    lon0 = min(c[1] for c in outline)
    pr = Projector(lat0, lon0)
    walk = _poly(outline, pr).simplify(0.3, preserve_topology=True)
    walk = orient(geo.largest_part(walk) if not isinstance(walk, Polygon) else walk, 1.0)
    minx, miny, maxx, maxy = walk.bounds
    if walk.area < 30:
        raise ValueError("That outline is smaller than 30 m². Pick a larger building or area.")
    side = max(maxx - minx, maxy - miny)
    if walk.area > MAX_AREA_M2:
        raise ValueError(
            f"That area is {walk.area / 10_000:.1f} ha; the limit is {MAX_AREA_M2 / 10_000:.0f} ha "
            "(about 630 m × 630 m). Draw a smaller box around the part you need."
        )
    if side > MAX_SIDE_M:
        raise ValueError(
            f"That area is {side:.0f} m long; the limit is {MAX_SIDE_M} m. "
            "Draw a smaller box around the part you need."
        )
    if len(walk.exterior.coords) > 400:
        walk = orient(walk.simplify(1.0, preserve_topology=True), 1.0)
    obstacles: list[Obstacle] = []
    for i, hole in enumerate(walk.interiors, start=1):  # courtyards and light wells
        obstacles.append(
            Obstacle(
                id=f"courtyard_{i}",
                kind="wall",
                polygon=geo.to_points(Polygon(hole)),
                label=f"Courtyard {i}",
                height_m=3.0,
            )
        )
    walk = Polygon(walk.exterior)

    selected = next((f for f in features if f["id"] == selected_id), None)
    candidates: list[tuple[Point, float, str]] = []
    if mode == "indoor":
        for f in features:
            if f["kind"] != "entrance":
                continue
            pt = Point(pr.xy(*f["coords"][0]))
            if pt.distance(walk.exterior) <= 3.0:
                main = f["tags"].get("entrance") == "main"
                label = f["name"] or ("Main entrance" if main else "Entrance")
                candidates.append((pt, _width(f["tags"], 3.0 if main else 2.0), label))
        prefix = "door"
        if selected and levels_note:
            levels = selected["tags"].get("building:levels")
            if levels and levels not in ("1", "0"):
                notes.append(
                    f"The map lists {levels} floors; the ground floor was imported. "
                    "Add the crowd of the upper floors to the ground floor or as a zone."
                )
    else:
        solids: list[tuple[Polygon, str, float, str]] = []  # shape, name, height, kind
        for f in features:
            if f["id"] == selected_id or (f["kind"] == "building" and not f["closed"]):
                continue
            if f["kind"] == "building":
                b = _poly(f["coords"], pr)
                if b.intersects(walk):
                    solids.append((b, f["name"], _height(f["tags"]), "building"))
            elif f["kind"] == "water" and f["closed"]:
                w = _poly(f["coords"], pr)
                if w.intersects(walk):
                    solids.append((w, f["name"] or "Water", 0.2, "water"))
            elif f["kind"] == "barrier" and f["tags"].get("barrier") != "hedge":
                line = LineString([pr.xy(c[0], c[1]) for c in f["coords"]])
                if line.intersects(walk) and line.length >= 3:
                    solids.append((line.buffer(0.15, cap_style="flat"), f["name"], 1.5, "fence"))
        # Close gaps narrower than ~1.2 m (between buildings, fences and the edge of the area):
        # nobody walks through them, but the simulator would route people in and they get stuck.
        edge_band = walk.exterior.buffer(GAP_CLOSE_M)
        solid = (
            unary_union([g.buffer(GAP_CLOSE_M) for g, *_ in solids] + [edge_band])
            .buffer(-GAP_CLOSE_M)
            .intersection(walk)
        )
        for p in _parts(solid):
            if p.area < 2:
                continue
            inside = [(nm, h, k) for g, nm, h, k in solids if g.intersects(p)]
            if not inside:
                continue  # leftover of the edge band
            names = [nm for nm, _, _ in inside if nm]
            fence_only = all(k == "fence" for _, _, k in inside)
            if all(k == "water" for _, _, k in inside):
                n = len(obstacles) + 1
                obstacles.append(
                    Obstacle(
                        id=f"water_{n}",
                        kind="other",
                        label=inside[0][0],
                        height_m=0.2,
                        polygon=geo.to_points(orient(p.simplify(0.3), 1.0)),
                    )
                )
                continue
            n = len(obstacles) + 1
            if fence_only:
                label = names[0] if names else "Fence"
            elif len(inside) == 1:
                label = names[0] if names else f"Building {n}"
            else:
                label = f"{names[0]} and {len(inside) - 1} more" if names else "Buildings"
            obstacles.append(
                Obstacle(
                    id=f"{'fence' if fence_only else 'building'}_{n}",
                    kind="fence" if fence_only else "other",
                    label=label,
                    polygon=geo.to_points(orient(p.simplify(0.2), 1.0)),
                    height_m=min(max((h for _, h, _ in inside), default=6.0), 60.0),
                )
            )
        for f in features:
            if f["kind"] == "path":
                hw = f["tags"].get("highway", "")
                if f["tags"].get("access") in ("no", "private"):
                    continue
                line = LineString([pr.xy(c[0], c[1]) for c in f["coords"]])
                cross = line.intersection(walk.exterior)
                pts = [g for g in getattr(cross, "geoms", [cross]) if isinstance(g, Point)]
                label = f["name"] or ""
                for pt in pts:
                    candidates.append((pt, _width(f["tags"], _PATH_WIDTH_M.get(hw, 4)), label))
            elif f["kind"] == "entrance":
                pt = Point(pr.xy(*f["coords"][0]))
                if pt.distance(walk.exterior) <= 3.0:
                    candidates.append((pt, _width(f["tags"], 4.0), f["name"] or "Gate"))
        prefix = "gate"
    solid_all = unary_union([geo.to_polygon(o.polygon) for o in obstacles]) if obstacles else None
    exits = _place_exits(walk, candidates, prefix, notes, solid_all)
    if not exits:
        width = 2.0 if mode == "indoor" else 4.0
        for pt in _auto_exits(walk, width):
            got = exit_at(walk, pt, width)
            if got is not None and not (
                solid_all is not None and Polygon(got[0]).buffer(0.3).intersects(solid_all)
            ):
                n = len(exits) + 1
                exits.append(
                    Exit(
                        id=f"{prefix}_{n}",
                        polygon=got[0],
                        width_m=got[1],
                        label=f"Exit {n} (assumed)",
                    )
                )
        notes.append(
            "The map shows no entrances here, so two exits were assumed on the "
            "longest walls. Move them to the real doors."
        )

    if solid_all is not None and exits:
        doors = unary_union([Polygon(e.polygon).buffer(0.6) for e in exits])
        for p in _parts(walk.difference(solid_all)):
            if not p.intersects(doors) and p.area >= 1:
                n = len(obstacles) + 1
                obstacles.append(
                    Obstacle(
                        id=f"enclosed_{n}",
                        kind="other",
                        label="Enclosed area",
                        polygon=geo.to_points(orient(p, 1.0)),
                        height_m=1.0,
                    )
                )
                if p.area > 50:
                    notes.append(f"Closed off an enclosed area of {p.area:.0f} m² with no way out.")
    blocked = (
        unary_union([geo.to_polygon(o.polygon).buffer(1.0) for o in obstacles])
        if obstacles
        else None
    )
    free = walk.buffer(-1.5)
    if blocked is not None:
        free = free.difference(blocked)
    parts = sorted((p for p in _parts(free) if p.area > 20), key=lambda p: -p.area)[:4]
    if not parts:
        raise ValueError("No open floor space left after buildings and fences. Pick another area.")
    total_area = sum(p.area for p in parts)
    if people is None:
        people = int(total_area * DEFAULT_DENSITY_PPM2[mode] / 10) * 10
        notes.append(
            f"Assumed {people:,} people ({DEFAULT_DENSITY_PPM2[mode]:g} per m² of open "
            "floor). Change the headcount in the zone inspector."
        )
    zones: list[Zone] = []
    left = people
    for i, p in enumerate(parts):
        share = left if i == len(parts) - 1 else round(people * p.area / total_area)
        left -= share
        label = "Crowd area" if len(parts) == 1 else f"Crowd area {i + 1}"
        zones.append(
            Zone(
                id=f"zone_{i + 1}",
                polygon=geo.to_points(orient(p.simplify(0.3), 1.0)),
                people=share,
                label=label,
            )
        )

    context = _context(features, walk, pr, selected_id)
    c = walk.centroid
    clat, clon = pr.latlon(c.x, c.y)
    venue = Venue(
        venue_id="draft",
        name=name,
        description="Imported from OpenStreetMap; check doors, gates and headcounts on site.",
        mode=mode,
        floors=[
            Floor(
                floor_id="F0",
                name="Ground",
                walkable=geo.to_points(walk),
                obstacles=obstacles,
                exits=exits,
                zones=zones,
            )
        ],
        location=Location(lat=round(clat, 6), lon=round(clon, 6)),
        extensions={
            "osm": {
                "origin": [lat0, lon0],
                "scale": [round(pr.kx, 3), round(pr.ky, 3)],  # metres per degree lon, lat
                "selected": selected_id,
                "context": context,  # neighbouring buildings, drawn in 3D only
            },
            "sources": [
                {
                    "label": "Map data © OpenStreetMap contributors (ODbL)",
                    "url": "https://www.openstreetmap.org/copyright",
                }
            ],
        },
    )
    return OsmImport(venue=venue, notes=notes)
