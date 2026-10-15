"""Shapely geometry for walls, doors, rooms and stairs (used by the structure ops).

Everything is rounded to the centimetre and snapped so the free space the simulator sees
has no hairline cracks or slivers: a wall end close to the floor outline or to another
wall is moved onto it and buried half a wall thickness past it, and door gaps never
leave wall stubs shorter than `MIN_PIECE_M`.
"""

from __future__ import annotations

import itertools
import math
from typing import Literal

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring

from api.core.extensions import geometry as geo
from api.models import Obstacle

Pt = tuple[float, float]
Side = Literal["north", "south", "east", "west"]

SNAP_M = 0.3  # wall ends this close to the outline or another wall are moved onto it
MIN_PIECE_M = 0.1  # shorter wall stubs left by a door are dropped (the gap runs to the end)
LANDING_MAX_M = 1.5  # depth of a stair landing (where people step on or off)

UNIT: dict[str, Pt] = {
    "north": (0.0, 1.0),
    "south": (0.0, -1.0),
    "east": (1.0, 0.0),
    "west": (-1.0, 0.0),
}


def rnd(p: tuple[float, float]) -> Pt:
    """Round a point to the centimetre."""
    return (round(float(p[0]), 2), round(float(p[1]), 2))


def line_points(line: LineString) -> list[Pt]:
    out: list[Pt] = []
    for c in line.coords:
        p = rnd((c[0], c[1]))
        if not out or out[-1] != p:
            out.append(p)
    return out


def wall_polygon(line: list[Pt], thickness_m: float) -> list[Pt]:
    """The wall's footprint: the centre line buffered with square ends and mitred corners."""
    return geo.barrier_polygon(line, thickness_m)


def wall_line(o: Obstacle) -> tuple[list[Pt], float]:
    """(centre line, thickness) of a wall; derived from the outline when it has no line."""
    poly = geo.to_polygon(o.polygon)
    if o.line and len(o.line) >= 2:
        length = LineString(o.line).length
        thickness = poly.area / length if length > 0 else 0.2
        return [rnd(p) for p in o.line], round(min(max(thickness, 0.05), 2.0), 3)
    rect = poly.minimum_rotated_rectangle
    if not isinstance(rect, Polygon):
        raise ValueError(f"wall '{o.id}' has no usable shape")
    c = list(rect.exterior.coords)[:4]
    edges = [(c[i], c[(i + 1) % 4]) for i in range(4)]
    lengths = [math.dist(a, b) for a, b in edges]
    short = 0 if lengths[0] <= lengths[1] else 1
    a0, a1 = edges[short]
    b0, b1 = edges[short + 2]
    mid_a = ((a0[0] + a1[0]) / 2, (a0[1] + a1[1]) / 2)
    mid_b = ((b0[0] + b1[0]) / 2, (b0[1] + b1[1]) / 2)
    return [rnd(mid_a), rnd(mid_b)], round(lengths[short], 3)


def snap_wall(
    points: list[Pt], walkable: list[Pt], other_lines: list[list[Pt]], thickness_m: float
) -> list[Pt]:
    """Snap both ends onto the outline or another wall (within SNAP_M) and bury them.

    A snapped end is pushed half a thickness further along its segment, so the wall's square
    end overlaps what it meets and no crack is left that the validator would count as a
    passage.
    """
    pts = [rnd(p) for p in points]
    outline = geo.to_polygon(walkable).exterior
    others = [LineString(line) for line in other_lines if len(line) >= 2]
    for end in (0, -1):
        p = Point(pts[end])
        targets = [outline, *others]
        best: tuple[float, Point] | None = None
        for t in targets:
            d = t.distance(p)
            if d <= SNAP_M and (best is None or d < best[0]):
                best = (d, t.interpolate(t.project(p)))
        if best is None:
            continue
        snapped = rnd((best[1].x, best[1].y))
        inner = pts[1] if end == 0 else pts[-2]
        dx, dy = snapped[0] - inner[0], snapped[1] - inner[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        ext = thickness_m / 2
        pts[end] = rnd((snapped[0] + dx / length * ext, snapped[1] + dy / length * ext))
    return pts


def check_wall_line(points: list[Pt]) -> str | None:
    """Why a polyline cannot be a wall (None if it can)."""
    line = LineString(points)
    if line.length < 0.3:
        return "it is shorter than 0.3 m"
    if any(math.dist(a, b) < 0.01 for a, b in itertools.pairwise(points)):
        return "two points are at the same place"
    if math.dist(points[0], points[-1]) < 0.05 or not line.is_simple:
        return (
            "it closes on itself or crosses itself; draw a room with add_room, or leave a gap "
            "for a door"
        )
    return None


def cut_door(line: list[Pt], x: float, y: float, width_m: float) -> list[list[Pt]]:
    """Wall pieces left after cutting a door gap centred on the point of the line nearest (x, y).

    The gap is moved along the wall so it fits; a stub shorter than MIN_PIECE_M is dropped
    (the gap then runs to the wall's end). Raises ValueError if the wall is too short.
    """
    ls = LineString(line)
    total = ls.length
    if total < width_m + 1e-6:
        raise ValueError(f"the wall is {total:.1f} m long, shorter than a {width_m:g} m door")
    s = ls.project(Point(x, y))
    a, b = s - width_m / 2, s + width_m / 2
    if a < 0:
        a, b = 0.0, width_m
    if b > total:
        a, b = total - width_m, total
    pieces: list[list[Pt]] = []
    if a >= MIN_PIECE_M:
        piece = substring(ls, 0.0, a)
        if isinstance(piece, LineString):
            pieces.append(line_points(piece))
    if total - b >= MIN_PIECE_M:
        piece = substring(ls, b, total)
        if isinstance(piece, LineString):
            pieces.append(line_points(piece))
    return [p for p in pieces if len(p) >= 2]


def snap_rect(
    x: float, y: float, w: float, d: float, walkable: list[Pt]
) -> tuple[float, float, float, float]:
    """Room rectangle (x0, y0, x1, y1) with edges close to the outline's bounds moved onto them."""
    minx, miny, maxx, maxy = geo.to_polygon(walkable).bounds
    x0, y0, x1, y1 = x, y, x + w, y + d
    if abs(x0 - minx) <= SNAP_M:
        x0 = minx
    if abs(y0 - miny) <= SNAP_M:
        y0 = miny
    if abs(x1 - maxx) <= SNAP_M:
        x1 = maxx
    if abs(y1 - maxy) <= SNAP_M:
        y1 = maxy
    return round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)


def room_ring(
    x0: float, y0: float, x1: float, y1: float, door_side: Side, door_width_m: float
) -> list[Pt]:
    """The room's walls as one open polyline: around the rectangle from one door jamb to the other."""
    corners: list[Pt] = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # SW, SE, NE, NW (anticlockwise)
    k = {"south": 0, "east": 1, "north": 2, "west": 3}[door_side]
    a, b = corners[k], corners[(k + 1) % 4]
    side = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / side, (b[1] - a[1]) / side
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    half = door_width_m / 2
    jamb_after = rnd((mx + ux * half, my + uy * half))
    jamb_before = rnd((mx - ux * half, my - uy * half))
    ring = [jamb_after, *(corners[(k + i) % 4] for i in range(1, 5)), jamb_before]
    return [rnd(p) for p in ring]


def side_on_outline(
    x0: float, y0: float, x1: float, y1: float, side: Side, walkable: list[Pt]
) -> bool:
    """Whether a side of the rectangle runs along the floor outline (a door there leads outside)."""
    seg = {
        "south": LineString([(x0, y0), (x1, y0)]),
        "north": LineString([(x0, y1), (x1, y1)]),
        "west": LineString([(x0, y0), (x0, y1)]),
        "east": LineString([(x1, y0), (x1, y1)]),
    }[side]
    mid = seg.interpolate(0.5, normalized=True)
    return bool(geo.to_polygon(walkable).exterior.distance(mid) < 0.05)


def stair_shapes(
    x: float, y: float, width_m: float, run_m: float, direction: Side
) -> tuple[list[Pt], list[Pt], list[Pt]]:
    """(footprint, top landing, bottom landing) of a straight stair centred at (x, y).

    `direction` is the way people face walking down: the top landing (on the upper floor) is
    at the back end of the footprint, the bottom landing (on the lower floor) at the front end.
    """
    ux, uy = UNIT[direction]
    nx, ny = -uy, ux
    landing = min(LANDING_MAX_M, run_m / 3)
    half_w = width_m / 2

    def band(s0: float, s1: float) -> list[Pt]:
        pts = [
            (x + ux * s0 - nx * half_w, y + uy * s0 - ny * half_w),
            (x + ux * s1 - nx * half_w, y + uy * s1 - ny * half_w),
            (x + ux * s1 + nx * half_w, y + uy * s1 + ny * half_w),
            (x + ux * s0 + nx * half_w, y + uy * s0 + ny * half_w),
        ]
        poly = Polygon(pts)
        if not poly.exterior.is_ccw:
            pts.reverse()
        return [rnd(p) for p in pts]

    half_run = run_m / 2
    return (
        band(-half_run, half_run),
        band(-half_run, -half_run + landing),
        band(half_run - landing, half_run),
    )
