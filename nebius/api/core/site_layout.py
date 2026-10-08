"""Furnish a real site for an event: stage, crowd barrier, front-of-house, toilets, bars, zones.

Deterministic search over a grid of candidate spots on the open ground, following common
event-layout practice: the stage stands as far from the entrances as the ground allows and
faces the open space, a barrier runs in front of it, front-of-house sits on the stage axis,
toilets and bars go along the edges away from the stage and clear of exits, and the crowd is
split into bands by distance from the stage. Counts come from the estimates (toilets) or stated
rules (bars, front-of-house). Nothing here comes from a language model.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.models import Obstacle, StageParams, Venue, Zone
from api.models.venue import ObstacleKind

TOILET_BLOCK_UNITS = 10  # units per block
TOILET_BLOCK_M = (12.5, 2.6)  # length, depth
BAR_M = (10.0, 4.0)
FOH_M = (6.0, 4.0)
EXIT_CLEAR_M = 6.0
PEOPLE_PER_BAR = 1500  # stated planning rule (assumption), at most 4 bars
GRID_M = 4.0
MAX_CANDIDATES = 6000

Vec = tuple[float, float]


@dataclass
class LayoutResult:
    """The furnished venue and what was placed or left out."""

    venue: Venue
    placed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _rect(c: Vec, t: Vec, n: Vec, along: float, depth: float) -> Polygon:
    """Rectangle centred at c, `along` long in direction t and `depth` deep in direction n."""
    (cx, cy), (tx, ty), (nx, ny) = c, t, n
    a, d = along / 2, depth / 2
    return Polygon(
        [
            (cx - tx * a - nx * d, cy - ty * a - ny * d),
            (cx + tx * a - nx * d, cy + ty * a - ny * d),
            (cx + tx * a + nx * d, cy + ty * a + ny * d),
            (cx - tx * a + nx * d, cy - ty * a + ny * d),
        ]
    )


def _pts(p: Polygon) -> list[tuple[float, float]]:
    return [(round(x, 3), round(y, 3)) for x, y in list(p.exterior.coords)[:-1]]


def _unit(dx: float, dy: float) -> Vec:
    n = math.hypot(dx, dy) or 1.0
    return (dx / n, dy / n)


def _stage_size(attendees: int, indoor: bool) -> tuple[float, float]:
    if attendees <= 500:
        return (8.0, 5.0)
    if attendees <= 2000:
        return (12.0, 6.0 if indoor else 8.0)
    if attendees <= 6000:
        return (16.0, 10.0)
    return (22.0, 12.0)


def _grid(poly: Polygon) -> list[Point]:
    minx, miny, maxx, maxy = poly.bounds
    step = max(GRID_M, math.sqrt((maxx - minx) * (maxy - miny) / MAX_CANDIDATES))
    out: list[Point] = []
    y = miny + step / 2
    while y < maxy:
        x = minx + step / 2
        while x < maxx:
            p = Point(x, y)
            if poly.contains(p):
                out.append(p)
            x += step
        y += step
    return out


def furnish(
    venue: Venue,
    *,
    attendees: int,
    stage: bool = True,
    toilets: int = 0,
    alcohol: bool = False,
) -> LayoutResult:
    """Place event infrastructure on the ground floor and re-split the crowd zones."""
    v = venue.model_copy(deep=True)
    f = v.floors[0]
    notes: list[str] = []
    placed: list[str] = []
    indoor = v.mode == "indoor"
    ground = geo.largest_part(geo.free_space(f))
    shrunk = ground.buffer(-0.5)
    if shrunk.is_empty or shrunk.area < 200:
        return LayoutResult(v, notes=["The open ground is too small to lay out an event."])
    free = shrunk if isinstance(shrunk, Polygon) else geo.largest_part(shrunk)
    exits = [geo.to_polygon(e.polygon) for e in f.exits]
    ex_c = unary_union(exits).centroid if exits else free.centroid
    exit_zone = unary_union([e.buffer(EXIT_CLEAR_M) for e in exits]) if exits else Polygon()
    cells = _grid(free)
    centre = free.centroid
    edge = free.exterior

    blocked: list[Polygon] = [geo.to_polygon(o.polygon).buffer(1.0) for o in f.obstacles]
    new_obs: list[Obstacle] = []
    taken = {o.id for o in f.obstacles}

    def add(
        oid: str,
        kind: ObstacleKind,
        label: str,
        poly: Polygon,
        h: float,
        line: list[tuple[float, float]] | None = None,
        keep_clear: bool = True,
    ) -> None:
        k, i = oid, 2
        while k in taken:
            k, i = f"{oid}_{i}", i + 1
        taken.add(k)
        new_obs.append(
            Obstacle(id=k, kind=kind, label=label, polygon=_pts(poly), height_m=h, line=line)
        )
        if keep_clear:
            blocked.append(poly.buffer(1.0))
        placed.append(label)

    def fits(poly: Polygon) -> bool:
        if not free.contains(poly) or poly.intersects(exit_zone):
            return False
        return not any(poly.intersects(b) for b in blocked)

    def best(
        size: tuple[float, float],
        score: Callable[[Point], float],
        orient: Callable[[Point], tuple[Vec, Vec]],
    ) -> tuple[Polygon, Point, Vec, Vec] | None:
        for c in sorted(cells, key=score, reverse=True):
            t, n = orient(c)
            poly = _rect((c.x, c.y), t, n, *size)
            if fits(poly):
                return poly, c, t, n
        return None

    def face(c: Point) -> tuple[Vec, Vec]:  # turned towards the middle of the ground
        n = _unit(centre.x - c.x, centre.y - c.y)
        return (-n[1], n[0]), n

    stage_c: Point | None = None
    t_st, n_st = (1.0, 0.0), (0.0, 1.0)
    sw = sd = 0.0
    if stage and any(o.kind == "stage" for o in f.obstacles):
        stage = False
        notes.append("The venue already has a stage; it was kept where it is.")
    if stage:
        sw, sd = _stage_size(attendees, indoor)

        def stage_score(c: Point) -> float:  # far from entrances, with open space in front
            t, n = face(c)
            ahead = _rect((c.x + n[0] * 22, c.y + n[1] * 22), t, n, sw + 10, 30)
            room = ahead.intersection(free).area / ahead.area
            return float(c.distance(ex_c) * (0.25 + room))

        got = best((sw, sd), stage_score, face)
        if got is None:
            notes.append("No clear spot for a stage away from the exits; add it by hand.")
        else:
            poly, stage_c, t_st, n_st = got
            add("stage", "stage", "Stage", poly, 1.2 if indoor else 12.0)
            if not indoor:
                v.stage = StageParams(
                    width_m=round(sw, 1),
                    depth_m=round(sd, 1),
                    roof_height_m=12.0,
                    roof_area_m2=round(sw * sd, 1),
                    legs=6 if sw >= 12 else 4,
                    ballast_kg_per_leg=2000,
                    friction_coeff=0.5,
                    force_coeff=1.3,
                    banner_area_m2=60,
                )

    front = (
        Point(stage_c.x + n_st[0] * sd / 2, stage_c.y + n_st[1] * sd / 2)
        if stage_c is not None
        else None
    )
    if front is not None and (not indoor or attendees >= 1000):
        half = sw / 2 + 3.0
        fx, fy = front.x + n_st[0] * 2.0, front.y + n_st[1] * 2.0
        line = LineString(
            [(fx - t_st[0] * half, fy - t_st[1] * half), (fx + t_st[0] * half, fy + t_st[1] * half)]
        ).intersection(free)
        if isinstance(line, LineString) and line.length > 4:
            pts = [(round(x, 3), round(y, 3)) for x, y in line.coords]
            barrier = geo.to_polygon(geo.barrier_polygon(pts, 0.3))
            add("front_barrier", "barrier", "Front-of-stage barrier", barrier, 1.1, pts, False)
        if attendees >= 1000:
            reach = max(Point(p).distance(front) for p in free.exterior.coords)
            dist = min(35.0, 0.55 * reach)
            for k in range(0, 8):
                c = (front.x + n_st[0] * (dist - 3 * k), front.y + n_st[1] * (dist - 3 * k))
                poly = _rect(c, t_st, n_st, *FOH_M)
                if fits(poly):
                    add("foh", "booth", "Front-of-house (sound desk)", poly, 3.0)
                    break

    def along_edge(c: Point) -> tuple[Vec, Vec]:  # long side parallel to the nearest edge
        d = edge.project(c)
        a, b = edge.interpolate(max(0.0, d - 2)), edge.interpolate(min(edge.length, d + 2))
        t = _unit(b.x - a.x, b.y - a.y)
        return t, (-t[1], t[0])

    anchor = stage_c or ex_c
    if not indoor and toilets > 0:
        blocks = min(8, math.ceil(toilets / TOILET_BLOCK_UNITS))
        done = 0
        for _ in range(blocks):
            got = best(
                TOILET_BLOCK_M,
                lambda c: -3 * edge.distance(c) + 0.3 * c.distance(anchor),
                along_edge,
            )
            if got is None:
                break
            add("toilets", "booth", f"Toilets ({TOILET_BLOCK_UNITS} units)", got[0], 2.5)
            done += 1
        if done < blocks:
            notes.append(
                f"Placed {done} of {blocks} toilet blocks; find room for the rest on site."
            )

    if not indoor and alcohol:
        bars = min(4, max(1, math.ceil(attendees / PEOPLE_PER_BAR)))
        far = max((c.distance(anchor) for c in cells), default=1.0)
        done = 0
        for _ in range(bars):
            got = best(
                BAR_M,
                lambda c: -2 * edge.distance(c) - abs(c.distance(anchor) - 0.5 * far),
                along_edge,
            )
            if got is None:
                break
            add("bar", "bar", f"Bar {done + 1}", got[0], 3.0)
            done += 1
        if done < bars:
            notes.append(f"Placed {done} of {bars} bars (1 per {PEOPLE_PER_BAR:,} people).")

    f.obstacles = [*f.obstacles, *new_obs]

    # crowd zones: bands by distance from the stage front (the old areas stay without a stage)
    if front is not None:
        occupied = unary_union([geo.to_polygon(o.polygon).buffer(0.6) for o in f.obstacles])
        crowd = ground.buffer(-1.0).difference(occupied)
        start = 3.0
        reach = max(Point(p).distance(front) for p in ground.exterior.coords)
        bands = [
            ("Front of stage", 0.0, 0.3, 0.35),
            ("Middle", 0.3, 0.7, 0.40),
            ("Back", 0.7, 1.0, 0.25),
        ]
        if indoor or attendees < 1500:
            bands = [("Audience front", 0.0, 0.5, 0.55), ("Audience back", 0.5, 1.0, 0.45)]
        span = max(reach - start, 6.0)
        zones: list[Zone] = []
        left = attendees
        for i, (label, a, b, share) in enumerate(bands):
            ring_out = front.buffer(start + span * b, quad_segs=24)
            ring_in = front.buffer(start + span * a, quad_segs=24) if a > 0 else Polygon()
            band = ring_out.difference(ring_in).intersection(crowd)
            parts = [g for g in getattr(band, "geoms", [band]) if isinstance(g, Polygon)]
            parts = [g for g in parts if g.area > 20]
            if not parts:
                continue
            part = max(parts, key=lambda g: g.area).simplify(0.3)
            people = left if i == len(bands) - 1 else round(attendees * share)
            left -= people
            zones.append(
                Zone(id=f"zone_{i + 1}", polygon=_pts(part), people=max(0, people), label=label)
            )
        if zones:
            zones[-1].people += max(0, left)
            f.zones = zones
        else:
            notes.append("Kept the original crowd area: the open ground could not be split.")

    if not validate_venue(v).ok:  # never hand back a plan the simulator would refuse
        return LayoutResult(
            venue, notes=["The event layout did not fit this site; kept the plain site."]
        )
    return LayoutResult(v, placed=placed, notes=notes)
