"""Venue JSON -> JuPedSim building blocks (geometry, exits, agent placement).

Runs inside the sandbox image; works on plain dicts (no API imports).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, unary_union


def to_poly(points: list[list[float]] | list[tuple[float, float]]) -> Polygon:
    """Valid polygon from a point list (repairs bow-ties)."""
    p = Polygon(points)
    if not p.is_valid:
        fixed = shapely.make_valid(p)
        parts = [g for g in getattr(fixed, "geoms", [fixed]) if isinstance(g, Polygon)]
        p = max(parts, key=lambda g: g.area)
    return p


PASSAGE_DEPTH_M = 0.6
WALL_TOLERANCE_M = 0.6


def exit_passage(
    walk: Polygon, exit_poly: Polygon, width: float, depth: float = PASSAGE_DEPTH_M
) -> tuple[Polygon, Polygon] | None:
    """A door as a short corridor through the outer wall, and the exit area at its far end.

    Returns None when the exit is not on the outline (it is then used as an area exit).
    """
    c = exit_poly.centroid
    if exit_poly.distance(walk.exterior) > WALL_TOLERANCE_M:
        return None
    coords = list(walk.exterior.coords)
    best: tuple[float, tuple[float, float], tuple[float, float]] | None = None
    for a, b in itertools.pairwise(coords):
        d = LineString([a, b]).distance(c)
        if best is None or d < best[0]:
            best = (d, (a[0], a[1]), (b[0], b[1]))
    assert best is not None
    (ax, ay), (bx, by) = best[1], best[2]
    length = math.hypot(bx - ax, by - ay)
    if length < 1e-6:
        return None
    ux, uy = (bx - ax) / length, (by - ay) / length
    nx, ny = -uy, ux
    t = (c.x - ax) * ux + (c.y - ay) * uy
    t = min(max(t, width / 2), length - width / 2) if length > width else length / 2
    px, py = ax + ux * t, ay + uy * t
    if walk.contains(Point(px + nx * 0.05, py + ny * 0.05)):
        nx, ny = -nx, -ny
    half = min(width, length) / 2

    def pt(s_: float, n_: float) -> tuple[float, float]:
        return (px + ux * s_ + nx * n_, py + uy * s_ + ny * n_)

    passage = Polygon([pt(-half, -0.05), pt(half, -0.05), pt(half, depth), pt(-half, depth)])
    # exit area right in the doorway, between the jambs: no side entry, no corridor jam
    stage = Polygon(
        [
            pt(-half + 0.02, 0.05),
            pt(half - 0.02, 0.05),
            pt(half - 0.02, depth - 0.05),
            pt(-half + 0.02, depth - 0.05),
        ]
    )
    return passage, stage


def _clean(geom: object, floor_id: str) -> Polygon | MultiPolygon:
    geom = shapely.make_valid(geom)
    polys: list[Polygon] = []
    for g in getattr(geom, "geoms", [geom]):
        if isinstance(g, Polygon) and g.area > 0.25:
            polys.append(g)
        elif isinstance(g, MultiPolygon):
            polys.extend(x for x in g.geoms if x.area > 0.25)
    if not polys:
        raise ValueError(f"floor {floor_id} has no walkable area")
    polys = [p.simplify(0.01, preserve_topology=True) for p in polys]
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


@dataclass
class FloorGeometry:
    """Walkable space for the simulator plus where each exit removes people."""

    free: Polygon | MultiPolygon
    exit_stages: dict[str, Polygon]
    passages: dict[str, Polygon]


def floor_geometry(floor: dict[str, Any]) -> FloorGeometry:
    """Walkable + door passages - obstacles, and the exit stage polygon of every exit."""
    walk = to_poly(floor["walkable"])
    passages: dict[str, Polygon] = {}
    stages: dict[str, Polygon] = {}
    for e in floor.get("exits", []):
        res = exit_passage(walk, to_poly(e["polygon"]), float(e["width_m"]))
        if res is not None:
            passages[e["id"]], stages[e["id"]] = res
    area = unary_union([walk, *passages.values()]) if passages else walk
    obstacles = [to_poly(o["polygon"]) for o in floor.get("obstacles", [])]
    if obstacles:
        area = area.difference(unary_union(obstacles))
    free = _clean(area, floor["floor_id"])
    for e in floor.get("exits", []):
        if e["id"] not in stages:
            stages[e["id"]] = inside(free, to_poly(e["polygon"]))
    return FloorGeometry(free=free, exit_stages=stages, passages=passages)


def floor_run_order(venue: dict[str, Any]) -> list[dict[str, Any]]:
    """Floors in simulation order: each before the floors its stairs lead to.

    People arriving by stair are injected into the floor they reach, so that floor runs after
    every floor that sends people to it: top down above street level, and a basement (whose
    stairs go up) before the street level. Stairs drawn in a loop fall back to height order.
    """
    floors = sorted(venue["floors"], key=lambda f: -float(f.get("elevation_m", 0)))
    feeds: dict[str, set[str]] = {f["floor_id"]: set() for f in floors}
    for s in venue.get("stairs", []):
        a, b = s["from_floor"], s["to_floor"]
        if a in feeds and b in feeds and a != b:
            feeds[b].add(a)
    done: set[str] = set()
    out: list[dict[str, Any]] = []
    while len(out) < len(floors):
        left = [f for f in floors if f["floor_id"] not in done]
        nxt = next((f for f in left if feeds[f["floor_id"]] <= done), left[0])
        out.append(nxt)
        done.add(nxt["floor_id"])
    return out


def free_space(floor: dict[str, Any]) -> Polygon | MultiPolygon:
    """Walkable space including door passages, minus obstacles."""
    return floor_geometry(floor).free


def main_component(geom: Polygon | MultiPolygon, near: Polygon | None = None) -> Polygon:
    """The component touching `near`, else the largest one."""
    if isinstance(geom, Polygon):
        return geom
    parts = list(geom.geoms)
    if near is not None:
        touching = [p for p in parts if p.intersects(near)]
        if touching:
            return max(touching, key=lambda g: g.intersection(near).area)
    return max(parts, key=lambda g: g.area)


def inside(geom: Polygon | MultiPolygon, poly: Polygon, nudge: float = 0.05) -> Polygon:
    """Clip a polygon to the free space, shrinking it slightly so it is strictly inside."""
    clipped = poly.intersection(geom.buffer(-nudge))
    if clipped.is_empty:
        clipped = poly.intersection(geom)
    if clipped.is_empty:
        raise ValueError("area lies outside the walkable space")
    if isinstance(clipped, Polygon):
        return clipped
    parts = [g for g in getattr(clipped, "geoms", []) if isinstance(g, Polygon)]
    if not parts:
        raise ValueError("area lies outside the walkable space")
    return max(parts, key=lambda g: g.area)


@dataclass
class ExitInfo:
    """An exit (or stair top) as a JuPedSim exit stage with its journey."""

    id: str
    polygon: Polygon
    width_m: float
    kind: str  # "exit" | "stair"
    stage_id: int = -1
    journey_id: int = -1
    open: bool = True
    capacity_pps: float = 1.0

    @property
    def center(self) -> tuple[float, float]:
        c = self.polygon.centroid
        return (c.x, c.y)


@dataclass
class AgentInfo:
    """Bookkeeping for one simulated person."""

    gid: int
    group: str
    target: str
    speed: float
    spawn_t: float
    kind: str = "normal"  # normal | counterflow | stair
    held_until: float | None = None
    speed_factor: float = 1.0


@dataclass
class Placement:
    """Positions generated for a group, with any shortfall."""

    points: list[tuple[float, float]] = field(default_factory=list)
    shortfall: int = 0


def _lattice(
    area: Polygon, n: int, gap: float, rng: np.random.Generator
) -> list[tuple[float, float]]:
    """Jittered hexagonal lattice: shrinks the spacing until n people fit (or spacing = gap)."""
    spacing = max(gap + 0.02, math.sqrt(2.0 * area.area / (math.sqrt(3.0) * max(n, 1))))
    minx, miny, maxx, maxy = area.bounds
    best = np.zeros((0, 2))
    while True:
        ox, oy = rng.uniform(0, spacing, size=2)
        xs = np.arange(minx + ox, maxx + 1e-9, spacing)
        rows = np.arange(miny + oy, maxy + 1e-9, spacing * math.sqrt(3.0) / 2)
        pts = [(x + (spacing / 2 if r % 2 else 0.0), y) for r, y in enumerate(rows) for x in xs]
        arr = np.asarray(pts, dtype=float).reshape(-1, 2)
        jitter = max(0.0, (spacing - gap) / 2 - 0.01)
        arr = arr + rng.uniform(-jitter, jitter, size=arr.shape)
        arr = arr[shapely.contains_xy(area, arr[:, 0], arr[:, 1])]
        if len(arr) > len(best):
            best = arr
        if len(best) >= n or spacing <= gap + 0.005:
            break
        spacing = max(gap, spacing * 0.97)
    rng.shuffle(best)
    return [(float(x), float(y)) for x, y in best[:n]]


def place_people(
    jps: Any, area: Polygon | MultiPolygon, n: int, seed: int, radius: float = 0.22
) -> Placement:
    """Non-overlapping positions inside `area`, at least `radius` + 5 cm from any wall."""
    if n <= 0:
        return Placement()
    gap = 2 * radius + 0.02
    clearance = radius + 0.05
    parts = [area] if isinstance(area, Polygon) else list(area.geoms)
    parts = [p for p in parts if p.area > 0.5]
    total = sum(p.area for p in parts) or 1.0
    rng = np.random.default_rng(seed)
    out: list[tuple[float, float]] = []
    shortfall = 0
    remaining = n
    for i, part in enumerate(parts):
        k = remaining if i == len(parts) - 1 else min(remaining, round(n * part.area / total))
        remaining -= k
        if k <= 0:
            continue
        got: list[tuple[float, float]] = []
        if k / part.area < 2.2:  # sparse enough for random sequential placement
            try:
                got = jps.distribute_by_number(
                    polygon=part,
                    number_of_agents=k,
                    distance_to_agents=gap,
                    distance_to_polygon=clearance,
                    seed=seed + i,
                    max_iterations=20_000,
                )
            except Exception:  # AgentNumberError: fall back to the lattice
                got = []
        if not got:
            inner = part.buffer(-clearance)
            inner_poly = (
                inner
                if isinstance(inner, Polygon)
                else max(getattr(inner, "geoms", [Polygon()]), key=lambda g: g.area)
            )
            got = _lattice(inner_poly, k, gap, rng) if not inner_poly.is_empty else []
        shortfall += k - len(got)
        out.extend((float(x), float(y)) for x, y in got)
    return Placement(points=out, shortfall=shortfall)


def assign_targets(
    points: list[tuple[float, float]], quotas: dict[str, int], exits: dict[str, ExitInfo]
) -> list[str]:
    """Split positions across exits honouring quotas; people nearer an exit get it first."""
    ids = [e for e in quotas if e in exits and exits[e].open and quotas[e] > 0]
    if not ids:
        return []
    n = len(points)
    total_q = sum(quotas[e] for e in ids)
    # scale quotas to exactly n people
    raw = {e: quotas[e] * n / total_q for e in ids}
    q = {e: int(math.floor(v)) for e, v in raw.items()}
    for e in sorted(ids, key=lambda e: raw[e] - q[e], reverse=True)[: n - sum(q.values())]:
        q[e] += 1
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    centers = np.asarray([exits[e].center for e in ids])
    d = np.linalg.norm(pts[:, None, :] - centers[None, :, :], axis=2)
    regret = d - d.min(axis=1, keepdims=True)
    order = np.argsort(regret, axis=None, kind="stable")
    out: list[str | None] = [None] * n
    left = dict(q)
    assigned = 0
    for flat in order:
        a, j = divmod(int(flat), len(ids))
        if out[a] is not None or left[ids[j]] <= 0:
            continue
        out[a] = ids[j]
        left[ids[j]] -= 1
        assigned += 1
        if assigned == n:
            break
    fallback = ids[int(np.argmax([q[e] for e in ids]))]
    return [t if t is not None else fallback for t in out]


def nearest_free_point(geom: Polygon | MultiPolygon, x: float, y: float) -> tuple[float, float]:
    """Closest point strictly inside the free space."""
    p = Point(x, y)
    inner = geom.buffer(-0.25)
    target = inner if not inner.is_empty else geom
    if target.contains(p):
        return (x, y)
    q = nearest_points(target, p)[0]
    return (float(q.x), float(q.y))
