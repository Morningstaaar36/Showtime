"""A new stairwell through every floor of a building: the structural fix for "one way down".

`add_stairwell` places a stair core where it fits (near the wall or corner asked for, clear of
walls, kitchens, lifts and the other stairs), joins every pair of floors with it, encloses it
in walls with a door on each floor, clears furniture out of its way, and gives it a street door
of its own when no exit is near its foot. One op, so an agent can propose it in one fix and the
editor can undo it in one step.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, Literal

from pydantic import Field
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points, unary_union

from api.core.building_gen import Core, enclose_stair, place_core, stairwell_walls
from api.core.extensions import geometry as geo
from api.models import Exit, Obstacle, PatchOpIn, Stair, Venue
from plugins.ops_core.common import _P, _op

Place = Literal[
    "north", "south", "east", "west", "centre",
    "north_east", "north_west", "south_east", "south_west",
]  # fmt: skip
FURNITURE = ("seating", "booth", "bar", "other")  # moved out of the stairwell's way
# a fire stair leads straight outside: its own street door unless an exit is this close already
DOOR_AT_FOOT_M = 2.0
WALL_STEP_M = 1.0  # spacing of the spots along the outer wall tried for a new stairwell
MAX_TRIES = 40


def _floors_up(venue: Venue) -> list[Any]:
    return sorted(venue.floors, key=lambda f: f.elevation_m)


def _footprint(venue: Venue) -> Polygon:
    shapes = [geo.to_polygon(f.walkable) for f in venue.floors]
    foot = shapes[0]
    for s in shapes[1:]:
        foot = foot.intersection(s)
    return foot if isinstance(foot, Polygon) else max(foot.geoms, key=lambda g: g.area)


def _target(foot: Polygon, place: Place | None, venue: Venue) -> tuple[float, float]:
    x0, y0, x1, y1 = foot.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    spots = {
        "north": (cx, y1), "south": (cx, y0), "east": (x1, cy), "west": (x0, cy),
        "centre": (cx, cy), "north_east": (x1, y1), "north_west": (x0, y1),
        "south_east": (x1, y0), "south_west": (x0, y0),
    }  # fmt: skip
    if place is not None:
        return spots[place]
    # unsaid: the corner farthest from the stairs there are, so the two ways down are apart
    stairs = [geo.to_polygon(s.top_polygon).centroid for s in venue.stairs]
    corners = [spots[k] for k in ("north_east", "north_west", "south_east", "south_west")]
    if not stairs:
        return corners[0]
    return max(corners, key=lambda c: min(Point(c).distance(p) for p in stairs))


def _street_floor(venue: Venue) -> Any:
    """The floor people leave the building from: the one with open exits nearest street level."""
    with_exits = [f for f in venue.floors if any(not e.blocked for e in f.exits)]
    pool = with_exits or venue.floors
    return min(pool, key=lambda f: abs(f.elevation_m))


def _door_on_wall(foot: Polygon, near: Point, width: float) -> list[tuple[float, float]]:
    """A door polygon just inside the outer wall, at the wall point nearest `near`."""
    ring = foot.exterior
    p = nearest_points(ring, near)[0]
    d = ring.project(p)
    a, b = ring.interpolate(max(0.0, d - 0.5)), ring.interpolate(min(ring.length, d + 0.5))
    ux, uy = b.x - a.x, b.y - a.y
    n = math.hypot(ux, uy) or 1.0
    ux, uy = ux / n, uy / n
    nx, ny = -uy, ux
    if not foot.contains(Point(p.x + nx * 0.2, p.y + ny * 0.2)):
        nx, ny = -nx, -ny
    h = width / 2
    pts = [
        (p.x - ux * h, p.y - uy * h),
        (p.x + ux * h, p.y + uy * h),
        (p.x + ux * h + nx * 0.3, p.y + uy * h + ny * 0.3),
        (p.x - ux * h + nx * 0.3, p.y - uy * h + ny * 0.3),
    ]
    return [(round(x, 3), round(y, 3)) for x, y in pts]


class AddStairwellParams(_P):
    op: Literal["add_stairwell"] = "add_stairwell"
    place: Place | None = None  # unsaid: the corner farthest from the existing stairs
    width_m: float = Field(default=1.2, ge=0.8, le=4.0)
    street_door: bool = True  # a door to the street at its foot when no exit is near
    door_width_m: float = Field(default=1.2, ge=0.8, le=6.0)
    restore: dict[str, Any] | None = None  # used by undo: the venue's parts before


def _storey_m(venue: Venue) -> float:
    """The tallest storey: the core's flights are sized for it."""
    ups = sorted(f.elevation_m for f in venue.floors)
    return max((b - a for a, b in itertools.pairwise(ups)), default=3.5)


def _plan(venue: Venue, p: AddStairwellParams) -> tuple[Core, Polygon] | str:
    if len(venue.floors) < 2:
        return "A stairwell joins floors, and this venue has one floor: add a floor first."
    foot = _footprint(venue)
    avoid: list[Any] = []
    for f in venue.floors:
        for o in f.obstacles:
            if o.kind not in FURNITURE or (o.height_m or 0) > 1.5:  # walls, kitchens, lifts
                avoid.append(geo.to_polygon(o.polygon).buffer(0.3))
        for e in f.exits:
            avoid.append(geo.to_polygon(e.polygon).buffer(3.0))  # apart from the doors there are
    for s in venue.stairs:
        for poly in (s.top_polygon, s.bottom_polygon):
            avoid.append(geo.to_polygon(poly).buffer(1.5))
    blocked = unary_union(avoid) if avoid else None
    core = _against_wall(venue, foot, p, blocked)
    if core is None:  # nowhere against the outer wall: wherever it fits
        core = place_core(
            foot, _target(foot, p.place, venue), p.width_m, blocked, storey_m=_storey_m(venue)
        )
    if core is None:
        where = p.place.replace("_", "-") if p.place else "any corner"
        return (
            f"No room for a {p.width_m:g} m stairwell near {where}: every spot there is taken by "
            "walls, kitchens, lifts or other stairs. Try another place or a narrower stair."
        )
    return core, foot


def _against_wall(venue: Venue, foot: Polygon, p: AddStairwellParams, blocked: Any) -> Core | None:
    """A core against the outer wall (so it can open straight onto the street), away from the
    doors there are, near the place asked for, else as far from the other stairs as fits."""
    ring = foot.exterior
    stairs = [geo.to_polygon(s.top_polygon).centroid for s in venue.stairs]
    exits = [geo.to_polygon(e.polygon) for f in venue.floors for e in f.exits]
    target = Point(_target(foot, p.place, venue)) if p.place else None
    spots = [ring.interpolate(d) for d in _steps(ring.length, WALL_STEP_M)]
    spots = [q for q in spots if all(q.distance(e) > 3.0 for e in exits)]
    if target is not None:
        spots.sort(key=lambda q: q.distance(target))
    elif stairs:
        spots.sort(key=lambda q: -min(q.distance(c) for c in stairs))
    for q in spots[:MAX_TRIES]:
        core = place_core(foot, (q.x, q.y), p.width_m, blocked, storey_m=_storey_m(venue))
        if core is not None and core.shaft.distance(ring) < 1.0:
            return core
    return None


def _steps(length: float, step: float) -> list[float]:
    return [i * step for i in range(int(length / step) + 1)]


class AddStairwellOp:
    name = "add_stairwell"
    description = (
        "Add a new enclosed stairwell running through every floor of a building (a second way "
        "down), near a wall or corner (place: north, south, east, west, centre or a corner like "
        "north_east; leave it out for the corner farthest from the existing stairs). Furniture "
        "in its way is moved, and it gets its own street door when no exit is near its foot."
    )
    example = '{"op": "add_stairwell", "place": "south_west", "width_m": 1.5}'
    params_model = AddStairwellParams

    def validate(self, venue: Venue, params: AddStairwellParams) -> list[str]:
        if params.restore is not None:
            return []
        planned = _plan(venue, params)
        return [planned] if isinstance(planned, str) else []

    def apply(self, venue: Venue, params: AddStairwellParams) -> Venue:
        v = venue.model_copy(deep=True)
        if params.restore is not None:  # undo: put the parts back as they were
            v.stairs = [Stair.model_validate(s) for s in params.restore["stairs"]]
            for f in v.floors:
                saved = params.restore["floors"].get(f.floor_id)
                if saved is not None:
                    f.obstacles = [Obstacle.model_validate(o) for o in saved["obstacles"]]
                    f.exits = [Exit.model_validate(e) for e in saved["exits"]]
            return v
        planned = _plan(v, params)
        if isinstance(planned, str):
            raise ValueError(planned)
        core, foot = planned
        taken = v.all_ids()
        n = 1
        while f"stairwell_{n}_1" in taken or f"stairwell_{n}_door" in taken:
            n += 1
        prefix = f"stairwell_{n}"
        floors = _floors_up(v)
        street = _street_floor(v)
        # levels counted from the street floor (0), as the generator's cores: the flights land
        # at the core's street-side end there
        level = {f.floor_id: i - floors.index(street) for i, f in enumerate(floors)}
        for i in range(1, len(floors)):
            upper, lower = floors[i], floors[i - 1]
            rise = upper.elevation_m - lower.elevation_m
            # people walk away from the street floor's level: down from above, up from below
            frm, to = (upper, lower) if level[lower.floor_id] >= 0 else (lower, upper)
            top, bottom = core.flight(level[frm.floor_id], level[to.floor_id])
            v.stairs.append(
                Stair(
                    id=f"{prefix}_{i}",
                    from_floor=frm.floor_id,
                    to_floor=to.floor_id,
                    top_polygon=geo.to_points(top),
                    bottom_polygon=geo.to_points(bottom),
                    width_m=core.width_m,
                    length_m=core.length_m(rise),
                )
            )
        foot_landing = core.landing(0)
        exits_near = [
            e for e in street.exits
            if geo.to_polygon(e.polygon).distance(foot_landing) < DOOR_AT_FOOT_M and not e.blocked
        ]  # fmt: skip
        if params.street_door and not exits_near:
            door = _door_on_wall(
                foot, foot_landing.centroid, min(params.door_width_m, core.width_m + 0.3)
            )
            street.exits.append(
                Exit(id=f"{prefix}_door", polygon=door, width_m=params.door_width_m,
                     label="Stairwell street door")
            )  # fmt: skip
        for f in v.floors:
            height = max(2.4, round(_storey(v, f) - 0.3, 2))
            ring, shell = enclose_stair(core, foot, foot.centroid, f.exits, level[f.floor_id])
            clear = shell.buffer(1.0)
            f.obstacles = [
                o for o in f.obstacles
                if not (o.kind in FURNITURE and (o.height_m or 0) <= 1.5
                        and geo.to_polygon(o.polygon).intersects(clear))
            ]  # fmt: skip
            walls = stairwell_walls(f.floor_id, [ring], height)
            for k, w in enumerate(walls, start=1):
                wid = f"{prefix}_{f.floor_id.lower()}_wall_{k}"
                f.obstacles.append(w.model_copy(update={"id": wid}))
        return v

    def invert(self, before: Venue, params: AddStairwellParams) -> list[PatchOpIn]:
        restore = {
            "stairs": [s.model_dump(mode="json") for s in before.stairs],
            "floors": {
                f.floor_id: {
                    "obstacles": [o.model_dump(mode="json") for o in f.obstacles],
                    "exits": [e.model_dump(mode="json") for e in f.exits],
                }
                for f in before.floors
            },
        }
        return [_op("add_stairwell", restore=restore)]


def _storey(v: Venue, f: Any) -> float:
    """The height from this floor to the one above (or below, for the top floor)."""
    ups = sorted(x.elevation_m for x in v.floors)
    i = ups.index(f.elevation_m)
    if i + 1 < len(ups):
        return ups[i + 1] - ups[i]
    return ups[i] - ups[i - 1] if i > 0 else 3.5


STAIRWELL_OPS = [AddStairwellOp()]
