"""A multi-storey building from one imported ground floor.

A building picked on the map arrives as one floor: its footprint, courtyards and exits at the
mapped entrances. This module stacks the storeys the map (or the organizer) gives, joins them
with two stair cores, and optionally lays out a corridor with rooms on both sides, the common
plan of hospitals, schools, offices and housing. Headcounts come from occupant load factors
(floor area per person by use, docs/ASSUMPTIONS.md); everything is an editable starting point,
not a survey of the real interior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from shapely.affinity import rotate, translate
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.models import Floor, Obstacle, PeopleGroup, Stair, Venue, Zone
from api.models.venue import EventKind

Interior = Literal["open", "rooms"]

MAX_LEVELS = 40
AUTO_PEOPLE_MAX = 10_000
WALL_T = 0.2  # interior wall thickness, metres
MIN_ROOM_DEPTH = 4.0  # rooms shallower than this are not laid out
STAIR_W = 1.6  # stair core width across the corridor (flight width ~1.2 m + handrails)
STAIR_RUN = 2.5  # length of one landing footprint along the corridor

# Floor area per person (m²) by use: IBC 2021 Table 1004.5 occupant load factors
# (gross unless noted). Assembly without fixed seats, unconcentrated: 15 ft² net = 1.4 m².
LOAD_M2: dict[str, float] = {
    "hospital": 22.3,  # inpatient treatment areas, 240 ft² gross
    "school": 1.9,  # classrooms, 20 ft² net
    "office": 13.9,  # business areas, 150 ft² gross
    "residential": 18.6,  # residential, 200 ft² gross
    "mall": 5.6,  # mercantile, 60 ft² gross
    "transit": 9.3,  # concourse waiting ~100 ft² gross (assumption)
}
DEFAULT_LOAD_M2 = 1.4

# Corridor width (m) by use: hospital corridors must pass beds (IBC 407.2: 8 ft = 2.44 m);
# schools 6 ft (1.83 m) and others 44 in (1.12 m) minimum, widened here for two-way flow.
CORRIDOR_M: dict[str, float] = {"hospital": 2.4, "school": 2.0, "office": 1.8}
DEFAULT_CORRIDOR_M = 1.8
ROOM_W: dict[str, float] = {"hospital": 7.0, "school": 8.0, "office": 6.0, "residential": 7.0}
DEFAULT_ROOM_W = 6.0
DOOR_W: dict[str, float] = {"hospital": 1.4}  # bed doors; others 1.0 m
ROOMS_BY_DEFAULT = {"hospital", "school", "office", "residential"}
# Rooms are grouped into a few areas per floor (each side of the corridor in up to this many
# runs of neighbouring rooms) so a long wing gives "Ward A" to "Ward F", not 40 one-person rooms.
AREAS_PER_SIDE = 3
MAX_OWN_ROOMS = 12
AREA_WORD: dict[str, str] = {
    "hospital": "Ward",
    "school": "Classrooms",
    "office": "Offices",
    "residential": "Flats",
}
# one room each, when the organizer gave the number of rooms ("8 classrooms per floor")
ROOM_WORD: dict[str, str] = {
    "hospital": "Ward",
    "school": "Classroom",
    "office": "Office",
    "residential": "Flat",
    "transit": "Room",
}

# Who is inside, by use (shares of each room's headcount). The simulator gives each group its
# own walking speed (docs/ASSUMPTIONS.md); the rest are general adults.
DEFAULT_GROUPS: dict[str, list[tuple[str, float]]] = {
    "hospital": [("bed", 0.25), ("wheelchair", 0.1), ("elderly", 0.15), ("staff", 0.2)],
    "school": [("child", 0.9), ("staff", 0.1)],
    "residential": [("elderly", 0.15), ("child", 0.15)],
}

_USE_TAGS: dict[str, tuple[str, ...]] = {
    "hospital": ("hospital", "clinic", "doctors", "nursing_home"),
    "school": ("school", "university", "college", "kindergarten"),
    "office": ("office", "commercial", "government", "civic"),
    "mall": ("retail", "mall", "supermarket", "marketplace", "shop"),
    "residential": ("apartments", "residential", "house", "hotel", "dormitory", "terrace"),
    "sports": ("stadium", "sports_centre", "sports_hall"),
    "religious": ("place_of_worship", "mosque", "church", "temple", "cathedral", "chapel"),
    "transit": ("train_station", "transportation", "bus_station", "station"),
    "conference": ("conference_centre", "events_venue", "exhibition_centre"),
    "concert": ("theatre", "concert_hall", "arts_centre", "cinema"),
}


def infer_use(tags: dict[str, Any]) -> EventKind | None:
    """Event kind from OSM tags (building, amenity, shop, leisure); None if unclear."""
    values = {str(tags.get(k, "")).lower() for k in ("amenity", "building", "leisure", "shop")}
    for use, words in _USE_TAGS.items():
        if values & set(words):
            return use  # type: ignore[return-value]
    if tags.get("shop"):
        return "mall"
    return None


def map_levels(tags: dict[str, Any]) -> int | None:
    """Storeys above ground from `building:levels` (None when absent or unreadable)."""
    raw = str(tags.get("building:levels", "")).strip()
    try:
        n = math.floor(float(raw.replace(",", ".")))
    except ValueError:
        return None
    return max(1, min(n, MAX_LEVELS)) if n >= 1 else None


def default_interior(use: str | None) -> Interior:
    """Rooms off a corridor for buildings that are usually laid out that way."""
    return "rooms" if use in ROOMS_BY_DEFAULT else "open"


def floor_name(i: int) -> str:
    """Ground, 1st floor, 2nd floor, ...; Basement, Basement 2, ... below street level."""
    if i < 0:
        return "Basement" if i == -1 else f"Basement {-i}"
    if i == 0:
        return "Ground"
    suffix = "th" if 10 <= i % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
    return f"{i}{suffix} floor"


def floor_id(level: int) -> str:
    """F0 (street level), F1, F2, ... upward; B1, B2, ... downward."""
    return f"F{level}" if level >= 0 else f"B{-level}"


def level_order(levels: int, basements: int = 0) -> list[int]:
    """Levels in venue order: street level first, then upward, then the basements."""
    return [*range(levels), *range(-1, -basements - 1, -1)]


@dataclass
class Core:
    """One stair core: two landings in plan; the flight runs between `a` and `b`.

    Above street level people come down from `a` to `b`; from a basement they go up from `a`
    to `b`. A core with a `span` joins only the levels from span[0] to span[1] (an exit stair
    from a basement or an upper floor to a street door); without one it joins every level.
    """

    a: Polygon
    b: Polygon
    width_m: float  # flight width
    span: tuple[int, int] | None = None

    def joins(self, lower: int, upper: int) -> bool:
        """Whether this core links level `lower` with level `upper`."""
        return self.span is None or (self.span[0] <= lower and upper <= self.span[1])


@dataclass
class StoreyPlan:
    """Choices for a designed building (a map import leaves them at their defaults)."""

    basements: int = 0
    floor_people: list[int] | None = None  # one per level, lowest first; overrides `people`
    cores: list[Core] | None = None  # None: up to two cores found near the ends
    rooms_per_floor: int | None = None
    level_obstacles: dict[int, list[Obstacle]] = field(default_factory=dict)
    zone_word: str | None = None  # what to call the rooms or areas ("Guest rooms")
    floor_names: dict[int, str] = field(default_factory=dict)  # "Lobby", "Platform"


def place_core(
    foot: Polygon,
    target: tuple[float, float],
    width_m: float,
    avoid: Any = None,
    *,
    corridor: bool = False,
) -> Core | None:
    """A stair core as close to `target` (x, y) as fits inside `foot` and clear of `avoid`.

    The flight runs along the building's long axis, pointing away from the nearer end; with
    `corridor` it stays on the long axis, where the corridor of a room layout runs. Landing
    `a` is the one nearer the target.
    """
    fr = _Frame(foot)
    inside = foot.buffer(-0.3)
    half = (width_m + 0.4) / 2
    loc = fr.to_local(Point(target))
    tx, ty = loc.x, 0.0 if corridor else loc.y
    sign = 1 if tx <= (fr.s0 + fr.s1) / 2 else -1
    step = max(0.5, max(fr.length, fr.depth) / 100)
    ss = [fr.s0 + i * step for i in range(int(fr.length / step) + 1)]
    ts = (
        [0.0, 0.5, -0.5, 1.0, -1.0]
        if corridor
        else [fr.t0 + i * step for i in range(int(fr.depth / step) + 1)]
    )
    cands = sorted(((s, t) for s in ss for t in ts), key=lambda c: math.dist(c, (tx, ty)))
    for s, t in cands:
        a = box(min(s, s + sign * STAIR_RUN), t - half, max(s, s + sign * STAIR_RUN), t + half)
        s2 = s + sign * (STAIR_RUN + 0.5)
        b = box(min(s2, s2 + sign * STAIR_RUN), t - half, max(s2, s2 + sign * STAIR_RUN), t + half)
        aw, bw = fr.to_world(a), fr.to_world(b)
        if not (inside.contains(aw) and inside.contains(bw)):
            continue
        if avoid is not None and not avoid.is_empty and avoid.intersects(aw.union(bw)):
            continue
        return Core(aw, bw, round(width_m, 2))
    return None


# --- local frame along the building's long axis ----------------------------------------------


class _Frame:
    """Coordinates (s along the long axis, t across it) of the footprint's oriented box."""

    def __init__(self, foot: Polygon) -> None:
        rect = foot.minimum_rotated_rectangle
        pts = list(rect.exterior.coords)[:4]
        edges = [(pts[i], pts[(i + 1) % 4]) for i in range(2)]
        (ax, ay), (bx, by) = max(edges, key=lambda e: math.dist(*e))
        self.angle = math.degrees(math.atan2(by - ay, bx - ax))
        c = rect.centroid
        self.cx, self.cy = c.x, c.y
        local = self.to_local(foot)
        self.s0, self.t0, self.s1, self.t1 = local.bounds

    def to_local(self, g: Any) -> Any:
        return rotate(translate(g, -self.cx, -self.cy), -self.angle, origin=(0, 0))

    def to_world(self, g: Any) -> Any:
        return translate(rotate(g, self.angle, origin=(0, 0)), self.cx, self.cy)

    @property
    def length(self) -> float:
        return float(self.s1 - self.s0)

    @property
    def depth(self) -> float:
        return float(self.t1 - self.t0)


def _parts(g: Any) -> list[Polygon]:
    if isinstance(g, Polygon):
        return [g] if not g.is_empty else []
    if isinstance(g, MultiPolygon):
        return [p for p in g.geoms if not p.is_empty]
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon) and not p.is_empty]


def _cores(fr: _Frame, foot: Any, corridor_w: float) -> list[tuple[Polygon, Polygon]]:
    """Up to two stair cores (top landing, bottom landing), one near each end of the building.

    Each core is searched from its end toward the middle, on the long axis first and then
    sideways, until both landings fit inside the floor (an L-shape or a courtyard moves them).
    """
    half = min(STAIR_W, corridor_w - 0.2) / 2
    inside = foot.buffer(-0.3)
    offsets = [0.0]
    for k in range(1, int(fr.depth // 2) + 1):
        offsets += [float(k), -float(k)]
    out: list[tuple[Polygon, Polygon]] = []
    for sign, start in ((1, fr.s0 + 1.0), (-1, fr.s1 - 1.0)):
        found = None
        steps = int(fr.length * 0.45)
        for i in range(steps):
            s = start + sign * i
            for t in offsets:
                top = box(
                    min(s, s + sign * STAIR_RUN), t - half, max(s, s + sign * STAIR_RUN), t + half
                )
                s2 = s + sign * (STAIR_RUN + 0.5)
                bottom = box(
                    min(s2, s2 + sign * STAIR_RUN),
                    t - half,
                    max(s2, s2 + sign * STAIR_RUN),
                    t + half,
                )
                top_w, bottom_w = fr.to_world(top), fr.to_world(bottom)
                if inside.contains(top_w) and inside.contains(bottom_w):
                    found = (top_w, bottom_w)
                    break
            if found:
                break
        if found and not any(found[0].distance(o[0]) < 8 for o in out):
            out.append(found)
    return out


def _room_walls(
    fr: _Frame, foot: Polygon, corridor_w: float, room_w: float, door_w: float
) -> tuple[Any, Polygon]:
    """Wall geometry (world) for a double-loaded corridor, and the corridor band (world)."""
    half = corridor_w / 2
    lines: list[LineString] = []
    doors: list[Polygon] = []
    n = max(1, round(fr.length / room_w))
    step = fr.length / n
    for side in (1, -1):
        edge = side * half
        far = fr.t1 + 1 if side > 0 else fr.t0 - 1
        lines.append(LineString([(fr.s0 - 1, edge), (fr.s1 + 1, edge)]))
        for k in range(1, n):
            s = fr.s0 + k * step
            lines.append(LineString([(s, edge), (s, far)]))
        for k in range(n):
            mid = fr.s0 + (k + 0.5) * step
            doors.append(box(mid - door_w / 2, edge - 0.5, mid + door_w / 2, edge + 0.5))
    walls = unary_union([ln.buffer(WALL_T / 2, cap_style="flat") for ln in lines])
    walls = walls.difference(unary_union(doors))
    band = box(fr.s0 - 1, -half, fr.s1 + 1, half)
    return fr.to_world(walls).intersection(foot), fr.to_world(band).intersection(foot)


def _group_rooms(fr: _Frame, rooms: list[Polygon], allowed: Any) -> list[Polygon]:
    """Neighbouring rooms on each side of the corridor merged into a few areas.

    An area's outline spans its rooms and the walls between them; the simulator places people
    only where the floor is walkable, so nobody stands inside a wall.
    """
    out: list[Polygon] = []
    for side in (1, -1):
        mine = [p for p in rooms if (fr.to_local(p.centroid).y > 0) == (side > 0)]
        mine.sort(key=lambda p: fr.to_local(p.centroid).x)
        if not mine:
            continue
        n = min(AREAS_PER_SIDE, len(mine))
        size = math.ceil(len(mine) / n)
        for k in range(0, len(mine), size):
            run = mine[k : k + size]
            hull = unary_union(run).convex_hull.intersection(allowed)
            parts = sorted(_parts(hull), key=lambda p: -p.area)
            if parts:
                out.append(parts[0])
    return out


def _wall_obstacles(floor_id: str, walls: Any, height: float) -> list[Obstacle]:
    out: list[Obstacle] = []
    for p in sorted(_parts(walls), key=lambda p: (p.centroid.x, p.centroid.y)):
        if p.area < 0.05:
            continue
        p = orient(Polygon(p.exterior), 1.0)  # walls never enclose: door gaps break every loop
        out.append(
            Obstacle(
                id=f"{floor_id.lower()}_wall_{len(out) + 1}",
                kind="wall",
                polygon=geo.to_points(p),
                height_m=round(height, 2),
                label="Wall",
            )
        )
    return out


def _groups(use: str | None) -> list[PeopleGroup]:
    return [PeopleGroup(kind=k, share=s) for k, s in DEFAULT_GROUPS.get(use or "", [])]


def split_holes(p: Polygon) -> list[Polygon]:
    """Split a polygon with holes (a floor around an atrium) into parts without holes.

    Zones are outlines without holes, so a ring-shaped floor area becomes two halves.
    """
    if not p.interiors:
        return [p]
    hole = Polygon(p.interiors[0]).centroid
    x0, y0, x1, y1 = p.bounds
    halves = (box(x0 - 1, y0 - 1, hole.x, y1 + 1), box(hole.x, y0 - 1, x1 + 1, y1 + 1))
    out: list[Polygon] = []
    for h in halves:
        for part in _parts(p.intersection(h)):
            out += split_holes(part)
    return out


def _split(total: int, weights: list[float]) -> list[int]:
    """`total` split in proportion to `weights`, adding up exactly (largest remainder)."""
    if not weights:
        return []
    if sum(weights) <= 0:
        weights = [1.0] * len(weights)
    s = sum(weights)
    raw = [total * w / s for w in weights]
    out = [math.floor(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: -(raw[i] - out[i]))
    for i in order[: total - sum(out)]:
        out[i] += 1
    return out


def _storeys(
    ground: Floor,
    levels: int,
    use: str | None,
    interior: Interior,
    floor_height_m: float,
    people: int | None,
    plan: StoreyPlan,
) -> tuple[list[Floor], list[Stair], list[str], Interior]:
    notes: list[str] = []
    foot = orient(geo.to_polygon(ground.walkable), 1.0)
    solids = [o for o in ground.obstacles]  # courtyards and light wells, on every floor
    solid = unary_union([geo.to_polygon(o.polygon) for o in solids]) if solids else None
    fr = _Frame(foot)
    corridor_w = CORRIDOR_M.get(use or "", DEFAULT_CORRIDOR_M)
    solid_free = foot.difference(solid.buffer(0.5)) if solid is not None else foot
    basements = plan.basements
    order = level_order(levels, basements)
    multi = len(order) > 1
    if plan.cores is not None:
        cores = list(plan.cores) if multi else []
    else:
        found = _cores(fr, solid_free, corridor_w) if multi else []
        flight = round(min(STAIR_W, corridor_w - 0.2) - 0.4, 2)
        cores = [Core(a, b, flight) for a, b in found]
    for lower in sorted(order)[:-1]:
        if not any(c.joins(lower, lower + 1) for c in cores):
            raise ValueError("No room for a stair inside this building outline.")
    if levels > 1 and len(cores) == 1 and plan.cores is None:
        notes.append("Only one stair fitted inside the outline; add a second one in the editor.")

    def cores_at(k: int) -> list[Core]:
        return [c for c in cores if c.span is None or c.span[0] <= k <= c.span[1]]

    def core_area(k: int) -> Any:
        shapes = [g for c in cores_at(k) for g in (c.a, c.b)]
        return unary_union(shapes).buffer(0.4) if shapes else None

    walls: Any = None
    band: Polygon | None = None
    # rooms the organizer counted are zones of their own (up to a dozen a floor; more are
    # grouped into areas like a map import, so a hotel floor is not 30 two-person zones)
    explicit_rooms = plan.rooms_per_floor is not None and plan.rooms_per_floor <= MAX_OWN_ROOMS
    if interior == "rooms":
        if fr.depth < corridor_w + 2 * MIN_ROOM_DEPTH or fr.length < 12:
            notes.append(
                f"The building is {fr.depth:.0f} m deep: too shallow for rooms on both sides of "
                "a corridor, so its floors were left open. Add rooms and walls in the editor."
            )
            interior = "open"
        else:
            room_w = ROOM_W.get(use or "", DEFAULT_ROOM_W)
            if plan.rooms_per_floor is not None:
                per_side = math.ceil(plan.rooms_per_floor / 2)
                room_w = fr.length / per_side
                if plan.rooms_per_floor % 2:
                    notes.append(
                        f"Laid out {2 * per_side} rooms per floor ({per_side} on each side of "
                        "the corridor); merge two in the editor if one fewer is right."
                    )
            walls, band = _room_walls(fr, foot, corridor_w, room_w, DOOR_W.get(use or "", 1.0))

    load = LOAD_M2.get(use or "", DEFAULT_LOAD_M2)
    floors: dict[int, Floor] = {}
    zone_shapes: list[tuple[int, Polygon]] = []
    for k in order:
        fid = floor_id(k)
        exits_k = ground.exits if k == 0 else []
        extra = plan.level_obstacles.get(k, [])
        extra_area = (
            unary_union([geo.to_polygon(o.polygon) for o in extra]).buffer(0.5) if extra else None
        )
        cores_k = core_area(k)
        floor_walls = walls
        if floor_walls is not None:
            if cores_k is not None:
                floor_walls = floor_walls.difference(cores_k)
            if exits_k:  # keep the doors clear
                floor_walls = floor_walls.difference(
                    unary_union([geo.to_polygon(e.polygon).buffer(1.2) for e in exits_k])
                )
            if extra_area is not None:
                floor_walls = floor_walls.difference(extra_area)
        obstacles = [
            o.model_copy(update={"id": o.id if k == 0 else f"{o.id}_{fid.lower()}"}) for o in solids
        ]
        obstacles += extra
        if floor_walls is not None:
            obstacles += _wall_obstacles(fid, floor_walls, floor_height_m - 0.3)
        free = foot
        if solid is not None:
            free = free.difference(solid.buffer(0.5))
        if floor_walls is not None:
            free = free.difference(floor_walls.buffer(0.4))
        # corridors are for moving, not for standing crowds
        free = free.difference(band.buffer(0.3)) if band is not None else free.buffer(-1.0)
        if cores_k is not None:
            free = free.difference(cores_k)
        if extra_area is not None:
            free = free.difference(extra_area)
        rooms = [p for p in _parts(free) if p.area >= 6]
        if band is not None and not explicit_rooms:  # the floor without corridor and stairs
            allowed = foot.buffer(-0.4).difference(band.buffer(0.3))
            if solid is not None:
                allowed = allowed.difference(solid.buffer(0.5))
            if cores_k is not None:
                allowed = allowed.difference(cores_k)
            if extra_area is not None:
                allowed = allowed.difference(extra_area)
            rooms = _group_rooms(fr, rooms, allowed)
        elif band is not None:  # each room its own zone, in order along the corridor
            rooms.sort(key=lambda p: (fr.to_local(p.centroid).y < 0, fr.to_local(p.centroid).x))
        rooms = [q for p in rooms for q in split_holes(p) if q.area >= 2]
        zone_shapes += [(k, orient(p.simplify(0.2), 1.0)) for p in rooms]
        floors[k] = Floor(
            floor_id=fid,
            name=plan.floor_names.get(k, floor_name(k)),
            elevation_m=round(k * floor_height_m, 2),
            walkable=ground.walkable,
            obstacles=obstacles,
            exits=exits_k,
            zones=[],
        )

    shares = _shares(zone_shapes, order, people, plan, load, use, notes, explicit_rooms)
    groups = _groups(use)
    if band is not None and explicit_rooms:
        word = ROOM_WORD.get(use or "", "Room")
    elif band is not None:
        word = AREA_WORD.get(use or "", "Rooms")
    else:
        word = "Floor area"
    word = plan.zone_word or word
    kept = [
        (fi, p, share)
        for (fi, p), share in zip(zone_shapes, shares, strict=True)
        if share > 0 or plan.floor_people is None  # a level left empty (a street entrance)
    ]
    on_floor = {fi: sum(1 for f, _, _ in kept if f == fi) for fi, _, _ in kept}
    per_floor: dict[int, int] = {}
    for fi, p, share in kept:
        n = per_floor[fi] = per_floor.get(fi, 0) + 1
        tag = str(n) if explicit_rooms and band is not None else (chr(64 + n) if n <= 26 else n)
        label = word if on_floor[fi] == 1 else f"{word} {tag}"
        if fi != 0 or fi in plan.floor_names:
            label += f" · {plan.floor_names.get(fi, floor_name(fi))}"
        floors[fi].zones.append(
            Zone(
                id=f"{floor_id(fi).lower()}_zone_{n}",
                polygon=geo.to_points(p),
                people=share,
                label=label,
                groups=groups,
            )
        )

    stairs: list[Stair] = []
    length = round(math.hypot(2 * STAIR_RUN + 1, floor_height_m), 2)
    for idx, c in enumerate(cores):
        letter = chr(ord("a") + idx)
        links = [(f"F{i}", f"F{i - 1}", str(i)) for i in range(1, levels) if c.joins(i - 1, i)]
        links += [
            (floor_id(k), floor_id(k + 1), f"b{-k}")
            for k in range(-basements, 0)
            if c.joins(k, k + 1)
        ]
        for frm, to, tag in links:
            stairs.append(
                Stair(
                    id=f"stair_{letter}_{tag}",
                    from_floor=frm,
                    to_floor=to,
                    top_polygon=geo.to_points(orient(c.a, 1.0)),
                    bottom_polygon=geo.to_points(orient(c.b, 1.0)),
                    width_m=c.width_m,
                    length_m=length,
                )
            )
    return [floors[k] for k in order], stairs, notes, interior


def _shares(
    zone_shapes: list[tuple[int, Polygon]],
    order: list[int],
    people: int | None,
    plan: StoreyPlan,
    load: float,
    use: str | None,
    notes: list[str],
    equal_rooms: bool,
) -> list[int]:
    """Headcount per zone shape: per level as given (exact), or a total split by area."""
    area = sum(p.area for _, p in zone_shapes)
    if plan.floor_people is not None:
        lowest_first = sorted(order)
        if len(plan.floor_people) != len(lowest_first):
            raise ValueError(f"{len(plan.floor_people)} headcounts for {len(lowest_first)} levels.")
        out = [0] * len(zone_shapes)
        for k, want in zip(lowest_first, plan.floor_people, strict=True):
            idx = [i for i, (fi, _) in enumerate(zone_shapes) if fi == k]
            if want > 0 and not idx:
                raise ValueError(f"No room for people on the {floor_name(k).lower()}.")
            weights = [1.0 if equal_rooms else zone_shapes[i][1].area for i in idx]
            for i, n in zip(idx, _split(want, weights), strict=True):
                out[i] = n
        return out
    if not zone_shapes or area <= 0:
        raise ValueError("No room for people inside this building outline.")
    levels = len(order)
    if people is None:
        estimate = max(10, int(area / load))
        people = min(estimate, AUTO_PEOPLE_MAX)
        what = f"{load:g} m² per person for a {use} building" if use else f"{load:g} m² per person"
        notes.append(
            f"Assumed {people:,} people on {levels} floor{'s' if levels > 1 else ''} "
            f"({what}). Set your real headcount."
            + (f" The floors could hold about {estimate:,}." if people < estimate else "")
        )
    left = people
    out = []
    for k, (_, p) in enumerate(zone_shapes):
        share = left if k == len(zone_shapes) - 1 else round(people * p.area / area)
        share = max(0, min(share, left))
        left -= share
        out.append(share)
    return out


def build_storeys(
    venue: Venue,
    *,
    levels: int = 1,
    use: EventKind | None = None,
    interior: Interior | None = None,
    floor_height_m: float = 3.5,
    people: int | None = None,
    plan: StoreyPlan | None = None,
) -> tuple[Venue, list[str]]:
    """Stack `levels` storeys on the venue's one imported floor (rooms or open plan).

    `plan` adds basements, exact headcounts per level, stair cores placed by the caller,
    obstacles and exits on given levels (the designer uses it; a map import does not).
    Falls back to open floors, then to the single imported floor, when a layout does not
    validate (an odd outline), and says so in the notes. With a `plan` the first layout that
    could be built is returned even when it does not validate, so its checks can be fixed.
    """
    designed = plan is not None
    if use is not None and use not in get_args(EventKind):
        raise ValueError(f"Unknown building use '{use}'.")
    plan = plan or StoreyPlan()
    levels = max(1, min(int(levels), MAX_LEVELS))
    interior = interior or default_interior(use)
    ground = venue.floors[0]
    notes: list[str] = []
    record = {
        "use": use,
        "levels": levels,
        "basements": plan.basements,
        "interior": interior,
        "floor_height_m": floor_height_m,
    }
    first: Venue | None = None
    for layout in dict.fromkeys([interior, "open"]):
        try:
            floors, stairs, why, layout = _storeys(
                ground, levels, use, layout, floor_height_m, people, plan
            )
        except ValueError as exc:
            notes.append(str(exc))
            continue
        out = venue.model_copy(
            update={
                "floors": floors,
                "stairs": stairs,
                "event_kind": use or venue.event_kind,
                "extensions": {
                    **venue.extensions,
                    "building": {**record, "interior": layout},
                },
            }
        )
        out = Venue.model_validate(out.model_dump())
        first = first or out
        problems = [c.message for c in validate_venue(out).checks if c.severity == "error"]
        if not problems:
            if levels > 1 and plan.cores is None:
                why.append(
                    f"{levels} floors joined by two stair cores near the ends of the building. "
                    "Move the stairs to the real stairwells in the editor."
                )
            if layout == "rooms":
                why.append(
                    "Rooms and a corridor were laid out as a typical plan, not the real "
                    "interior: check walls and doors on site."
                )
            return out, notes + why
        notes.append(
            f"The {layout} layout did not fit this outline ({problems[0]})"
            + ("; trying open floors." if layout == "rooms" else ".")
        )
    if designed and first is not None:
        return first, notes  # the checks on it say what to change
    notes.append("Kept the imported ground floor only.")
    return venue, notes
