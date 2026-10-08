"""Geometry helpers shared by core and plugins (plugin SDK). Built on Shapely 2."""

from __future__ import annotations

from typing import Any, Literal

import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from api.models.venue import Floor

Wall = Literal["north", "south", "east", "west"]
EXIT_DEPTH_M = 0.4
WALL_INSET_M = 0.02


def to_polygon(points: list[tuple[float, float]]) -> Polygon:
    """Convert a point list to a valid Shapely polygon (repairs self-intersections)."""
    poly = Polygon(points)
    if not poly.is_valid:
        fixed = shapely.make_valid(poly)
        if isinstance(fixed, Polygon):
            return fixed
        polys = [g for g in getattr(fixed, "geoms", []) if isinstance(g, Polygon)]
        if polys:
            return max(polys, key=lambda g: g.area)
    return poly


def to_points(poly: Polygon) -> list[tuple[float, float]]:
    """Exterior ring of a polygon as a point list without the closing point."""
    coords = list(poly.exterior.coords)[:-1]
    return [(round(x, 4), round(y, 4)) for x, y in coords]


def free_space(floor: Floor) -> Polygon | MultiPolygon:
    """Walkable area minus obstacles (what pedestrians can actually use)."""
    walk = to_polygon(floor.walkable)
    if not floor.obstacles:
        return walk
    obs = unary_union([to_polygon(o.polygon) for o in floor.obstacles])
    result = walk.difference(obs)
    if isinstance(result, Polygon | MultiPolygon):
        return result
    return shapely.make_valid(result)


def largest_part(geom: Polygon | MultiPolygon) -> Polygon:
    """Largest polygon of a (multi)polygon."""
    if isinstance(geom, Polygon):
        return geom
    return max(geom.geoms, key=lambda g: g.area)


def exit_on_wall(
    walkable: list[tuple[float, float]], wall: Wall, center: float | None, width_m: float
) -> list[tuple[float, float]]:
    """Exit rectangle just inside the walkable boundary on a named wall.

    `center` is measured along the wall: x for north/south walls, y for east/west walls;
    None means the middle of that side. Raises ValueError (with the valid range) if the wall
    line does not exist at that position.
    """
    poly = to_polygon(walkable)
    minx, miny, maxx, maxy = poly.bounds
    half = width_m / 2.0
    lo, hi, axis = (miny, maxy, "y") if wall in ("east", "west") else (minx, maxx, "x")
    if center is None:
        center = (lo + hi) / 2.0
    if not lo + half <= center <= hi - half:
        raise ValueError(
            f"the {wall} side runs from {axis} = {lo:.1f} to {hi:.1f} m, so a {width_m:g} m exit "
            f"needs a center between {lo + half:.1f} and {hi - half:.1f} (got {center:.1f})"
        )
    if wall in ("east", "west"):
        probe = LineString([(minx - 1, center), (maxx + 1, center)])
    else:
        probe = LineString([(center, miny - 1), (center, maxy + 1)])
    inter = poly.intersection(probe)
    if inter.is_empty:
        raise ValueError(f"no {wall} wall at {axis} = {center:.1f} m")
    xs = [c[0] for c in _coords(inter)]
    ys = [c[1] for c in _coords(inter)]
    if wall == "east":
        edge = max(xs) - WALL_INSET_M
        rect = Polygon(
            [
                (edge - EXIT_DEPTH_M, center - half),
                (edge, center - half),
                (edge, center + half),
                (edge - EXIT_DEPTH_M, center + half),
            ]
        )
    elif wall == "west":
        edge = min(xs) + WALL_INSET_M
        rect = Polygon(
            [
                (edge, center - half),
                (edge + EXIT_DEPTH_M, center - half),
                (edge + EXIT_DEPTH_M, center + half),
                (edge, center + half),
            ]
        )
    elif wall == "north":
        edge = max(ys) - WALL_INSET_M
        rect = Polygon(
            [
                (center - half, edge - EXIT_DEPTH_M),
                (center + half, edge - EXIT_DEPTH_M),
                (center + half, edge),
                (center - half, edge),
            ]
        )
    else:
        edge = min(ys) + WALL_INSET_M
        rect = Polygon(
            [
                (center - half, edge),
                (center + half, edge),
                (center + half, edge + EXIT_DEPTH_M),
                (center - half, edge + EXIT_DEPTH_M),
            ]
        )
    clipped = rect.intersection(poly)
    if clipped.is_empty or clipped.area < 0.5 * rect.area:
        raise ValueError(f"exit does not fit on the {wall} wall at {center:.1f} m")
    return to_points(largest_part(clipped))


def _coords(geom: object) -> list[tuple[float, float]]:
    if hasattr(geom, "geoms"):
        out: list[tuple[float, float]] = []
        for g in geom.geoms:
            out.extend(_coords(g))
        return out
    return [(float(c[0]), float(c[1])) for c in geom.coords]  # type: ignore[attr-defined]


def barrier_polygon(
    line: list[tuple[float, float]], thickness_m: float = 0.3
) -> list[tuple[float, float]]:
    """Thin polygon around a polyline (crowd barrier or fence)."""
    geom = LineString(line).buffer(thickness_m / 2.0, cap_style="flat", join_style="mitre")
    return to_points(largest_part(geom))


def translate(points: list[tuple[float, float]], dx: float, dy: float) -> list[tuple[float, float]]:
    """Shift a polygon."""
    return [(round(x + dx, 4), round(y + dy, 4)) for x, y in points]


def resize(
    points: list[tuple[float, float]], width_m: float | None, depth_m: float | None
) -> list[tuple[float, float]]:
    """Scale a polygon about its centroid so its bounding box matches the new size."""
    poly = to_polygon(points)
    minx, miny, maxx, maxy = poly.bounds
    cx, cy = poly.centroid.x, poly.centroid.y
    sx = (width_m / (maxx - minx)) if width_m and maxx > minx else 1.0
    sy = (depth_m / (maxy - miny)) if depth_m and maxy > miny else 1.0
    return [(round(cx + (x - cx) * sx, 4), round(cy + (y - cy) * sy, 4)) for x, y in points]


def rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    """Axis-aligned rectangle from two corners."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Centroid of a polygon."""
    c = to_polygon(points).centroid
    return (round(c.x, 3), round(c.y, 3))


def distance_to(points: list[tuple[float, float]], x: float, y: float) -> float:
    """Distance from a point to a polygon (0 inside)."""
    return float(to_polygon(points).distance(Point(x, y)))


def display_names(*venues: Any) -> dict[str, str]:
    """Readable names for exits, zones and objects across venues (labels first).

    Unlabelled exits (for example one a fix added) are named by their side ("new east exit"),
    unlabelled objects by their kind ("barrier").
    """
    names: dict[str, str] = {}
    for v in venues:
        if v is None:
            continue
        for f in v.floors:
            xs = [p[0] for p in f.walkable]
            ys = [p[1] for p in f.walkable]
            for e in f.exits:
                if e.label:
                    names[e.id] = e.label
                elif e.id not in names:
                    cx = sum(p[0] for p in e.polygon) / len(e.polygon)
                    cy = sum(p[1] for p in e.polygon) / len(e.polygon)
                    side = min(
                        (cx - min(xs), "west"),
                        (max(xs) - cx, "east"),
                        (cy - min(ys), "south"),
                        (max(ys) - cy, "north"),
                    )[1]
                    names[e.id] = f"new {side} exit"
            for z in f.zones:
                if z.label:
                    names[z.id] = z.label
            for o in f.obstacles:
                label = getattr(o, "label", None)
                names.setdefault(o.id, label or str(o.kind).replace("_", " "))
                if label:
                    names[o.id] = label
    return names
