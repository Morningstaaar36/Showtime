"""A multi-storey building from one imported ground floor.

A building picked on the map arrives as one floor: its footprint, courtyards and exits at the
mapped entrances. This module stacks the storeys the map (or the organizer) gives, joins them
with two stair cores, and optionally lays out a corridor with rooms on both sides, the common
plan of hospitals, schools, offices and housing, or a dining fit-out (restaurants and cafés: a
kitchen, tables in rows, toilets, a lift and an enclosed stairwell on every floor). Headcounts
come from occupant load factors (floor area per person by use, docs/ASSUMPTIONS.md); everything
is an editable starting point, not a survey of the real interior. Sizes live in
api/data/fitouts.json.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, get_args

from shapely.affinity import rotate, translate
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.models import Floor, Obstacle, PeopleGroup, Stair, Venue, Zone
from api.models.venue import EventKind
from api.models.venue_spec import MAX_LEVELS

Interior = Literal["open", "rooms", "dining"]
FITOUTS_FILE = Path(__file__).resolve().parents[1] / "data" / "fitouts.json"

AUTO_PEOPLE_MAX = 10_000
WALL_T = 0.2  # interior wall thickness, metres
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


@lru_cache(maxsize=1)
def fitouts() -> dict[str, Any]:
    """How storeys are fitted out, by interior (api/data/fitouts.json)."""
    data: dict[str, Any] = json.loads(FITOUTS_FILE.read_text())
    return data


def _by_use(table: dict[str, float], use: str | None) -> float:
    return float(table.get(use or "", table["default"]))


def room_width(use: str | None) -> float:
    """The usual width of one room along the corridor, by use."""
    return _by_use(fitouts()["rooms"]["room_w_m"], use)


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
    "school": ("school", "kindergarten"),
    "campus": ("university", "college"),
    "airport": ("aerodrome", "terminal", "airport"),
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


def stair_going(storey_m: float) -> float:
    """Plan length of one straight flight a storey high: (risers - 1) treads (fitouts.json)."""
    st = fitouts()["stair"]
    risers = max(2, math.ceil(storey_m / float(st["riser_max_m"]) - 1e-9))
    return round((risers - 1) * float(st["tread_m"]), 2)


def landing_depth(width_m: float) -> float:
    """A landing is at least as deep as its flight is wide."""
    return max(float(fitouts()["stair"]["landing_min_m"]), width_m)


@dataclass
class Core:
    """One stair core, in plan: `a` the half nearer the target, `b` the other half.

    A core of two lanes (a scissor core, `scissor`) holds one straight flight per storey: the
    flights take turns between the lanes, and on each level they land at one end of the core,
    the `b` end on even levels (street level among them) and the `a` end on odd ones, so the
    flight from above arrives beside the flight on down. A core one lane wide (an older or a
    hand-drawn one) has a landing in each half and stacks its flights from `a` down to `b`.

    A core with a `span` joins only the levels from span[0] to span[1] (an exit stair from a
    basement or an upper floor to a street door); without one it joins every level.
    """

    a: Polygon
    b: Polygon
    width_m: float  # flight width
    span: tuple[int, int] | None = None

    def joins(self, lower: int, upper: int) -> bool:
        """Whether this core links level `lower` with level `upper`."""
        return self.span is None or (self.span[0] <= lower and upper <= self.span[1])

    @property
    def shaft(self) -> Polygon:
        """The whole core: both landings and the flights between them."""
        rect = unary_union([self.a, self.b]).minimum_rotated_rectangle
        return rect if isinstance(rect, Polygon) else unary_union([self.a, self.b]).envelope

    def _axes(self) -> tuple[Point, tuple[float, float], tuple[float, float], float, float]:
        """Origin (the `a` end, on the axis), unit vectors along and across, length, width."""
        ca, cb = self.a.centroid, self.b.centroid
        d = math.hypot(cb.x - ca.x, cb.y - ca.y) or 1.0
        u = ((cb.x - ca.x) / d, (cb.y - ca.y) / d)
        n = (-u[1], u[0])
        pts = list(self.shaft.exterior.coords)[:-1]
        along = [(x - ca.x) * u[0] + (y - ca.y) * u[1] for x, y in pts]
        across = [(x - ca.x) * n[0] + (y - ca.y) * n[1] for x, y in pts]
        p0, q0, q1 = min(along), min(across), max(across)
        mid = (q0 + q1) / 2
        origin = Point(ca.x + u[0] * p0 + n[0] * mid, ca.y + u[1] * p0 + n[1] * mid)
        return origin, u, n, max(along) - p0, q1 - q0

    @property
    def scissor(self) -> bool:
        """Two lanes wide: one flight per storey, the flights taking turns between the lanes."""
        gap = float(fitouts()["stair"]["lane_gap_m"])
        return self._axes()[4] >= 2 * self.width_m + gap - 0.05

    def _box(self, p0: float, p1: float, q0: float, q1: float) -> Polygon:
        o, u, n, _, _ = self._axes()
        corners = [(p0, q0), (p1, q0), (p1, q1), (p0, q1)]
        return orient(
            Polygon([(o.x + u[0] * p + n[0] * q, o.y + u[1] * p + n[1] * q) for p, q in corners]),
            1.0,
        )

    def landing(self, level: int, lane: int | None = None) -> Polygon:
        """Where this core's flights meet `level`: the end landing used there (one lane of it,
        or the whole width with `lane` None). A one-lane core: its `a` half on every level."""
        if not self.scissor:
            return self.a
        _, _, _, length, width = self._axes()
        depth = min(landing_depth(self.width_m), length / 2)
        p0, p1 = (length - depth, length) if level % 2 == 0 else (0.0, depth)
        if lane is None:
            return self._box(p0, p1, -width / 2, width / 2)
        gap = float(fitouts()["stair"]["lane_gap_m"])
        q0, q1 = (-width / 2, -gap / 2) if lane % 2 == 0 else (gap / 2, width / 2)
        return self._box(p0, p1, q0, q1)

    def flight(self, frm: int, to: int) -> tuple[Polygon, Polygon]:
        """The landings (on level `frm`, on level `to`) of the flight joining two levels next to
        each other: people go from the first to the second."""
        if not self.scissor:
            return self.a, self.b
        lane = min(frm, to) % 2
        return self.landing(frm, lane), self.landing(to, lane)

    def length_m(self, storey_m: float) -> float:
        """Walking length of one storey's flight: its slope and a landing."""
        if not self.scissor:
            return round(math.hypot(2 * STAIR_RUN + 1, storey_m), 2)
        return round(math.hypot(stair_going(storey_m), storey_m) + landing_depth(self.width_m), 2)


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


def _core_shapes(
    s: float, t: float, sign: int, width_m: float, storey_m: float, compact: bool
) -> tuple[Polygon, Polygon]:
    """A core's two halves in a building's local frame, starting at `s` and running along the
    long axis in direction `sign`, centred at `t` across it. Two lanes wide unless `compact`."""
    if compact:  # one lane: two landings STAIR_RUN long, 0.5 m apart
        half = (width_m + 0.4) / 2
        a = box(min(s, s + sign * STAIR_RUN), t - half, max(s, s + sign * STAIR_RUN), t + half)
        s2 = s + sign * (STAIR_RUN + 0.5)
        b = box(min(s2, s2 + sign * STAIR_RUN), t - half, max(s2, s2 + sign * STAIR_RUN), t + half)
        return a, b
    half = (2 * width_m + float(fitouts()["stair"]["lane_gap_m"])) / 2
    length = 2 * landing_depth(width_m) + stair_going(storey_m)
    m = s + sign * length / 2
    e = s + sign * length
    return (
        box(min(s, m), t - half, max(s, m), t + half),
        box(min(m, e), t - half, max(m, e), t + half),
    )


def place_core(
    foot: Polygon,
    target: tuple[float, float],
    width_m: float,
    avoid: Any = None,
    *,
    corridor: bool = False,
    storey_m: float = 3.5,
) -> Core | None:
    """A stair core as close to `target` (x, y) as fits inside `foot` and clear of `avoid`.

    The core runs along the building's long axis, pointing away from the nearer end; with
    `corridor` it stays on the long axis, where the corridor of a room layout runs. Half `a` is
    the one nearer the target. Two lanes (one flight per storey, see `Core`) where they fit,
    else one lane.
    """
    fr = _Frame(foot)
    inside = foot.buffer(-0.3)
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
    for compact in (False, True):
        for s, t in cands:
            a, b = _core_shapes(s, t, sign, width_m, storey_m, compact)
            aw, bw = fr.to_world(a), fr.to_world(b)
            both = aw.union(bw)
            if not inside.contains(both):
                continue
            if avoid is not None and not avoid.is_empty and avoid.intersects(both):
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
        # the long axis; for a square (equal sides) the one nearest east-west, so the rooms
        # line the north and south walls, as the builder's door placement expects
        (ax, ay), (bx, by) = max(
            edges, key=lambda e: (round(math.dist(*e), 6), abs(e[1][0] - e[0][0]))
        )
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


def _cores(fr: _Frame, foot: Any, flight_m: float, storey_m: float) -> list[Core]:
    """Up to two stair cores, one near each end of the building.

    Each core is searched from its end toward the middle, on the long axis first and then
    sideways, until it fits inside the floor (an L-shape or a courtyard moves it): two lanes
    wide where that fits anywhere, else one lane.
    """
    inside = foot.buffer(-0.3)
    offsets = [0.0]
    for k in range(1, int(fr.depth // 2) + 1):
        offsets += [float(k), -float(k)]
    out: list[Core] = []
    for sign, start in ((1, fr.s0 + 1.0), (-1, fr.s1 - 1.0)):
        found = None
        for compact in (False, True):
            for i in range(int(fr.length * 0.45)):
                s = start + sign * i
                for t in offsets:
                    a, b = _core_shapes(s, t, sign, flight_m, storey_m, compact)
                    aw, bw = fr.to_world(a), fr.to_world(b)
                    if inside.contains(aw.union(bw)):
                        found = Core(aw, bw, flight_m)
                        break
                if found:
                    break
            if found:
                break
        if found and not any(found.shaft.distance(o.shaft) < 4 for o in out):
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


FITOUT_LIFT = "Lift (not used in a fire)"


@dataclass
class _Fitout:
    """One floor's dining fit-out: the obstacles, and the area people do not stand in (tables
    excluded: people sit between them, and the simulator places them only where it is free)."""

    obstacles: list[Obstacle]
    taken: Any


def enclose_stair(
    c: Core, foot: Polygon, centre: Point, exits: list[Any] | None = None, level: int = 0
) -> tuple[Any, Polygon]:
    """Walls enclosing a stair core, with a door as wide as the flight on the long side facing
    the floor, beside the landing the flights use on `level` (the middle of a one-lane core),
    and a gap at any street door beside it; and the outline."""
    sw = fitouts()["stairwell"]
    shell = c.shaft.buffer(sw["gap_m"], join_style=2)
    pts = list(shell.exterior.coords)[:4]
    edges = sorted(((pts[i], pts[(i + 1) % 4]) for i in range(4)), key=lambda e: -math.dist(*e))
    (ax, ay), (bx, by) = min(
        edges[:2],
        key=lambda e: centre.distance(Point((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2)),
    )
    side = LineString([(ax, ay), (bx, by)])
    at = c.landing(level).centroid if c.scissor else Point((ax + bx) / 2, (ay + by) / 2)
    door = side.interpolate(side.project(at)).buffer(
        (c.width_m + sw["door_extra_m"]) / 2, cap_style=3
    )
    ring = shell.exterior.buffer(sw["wall_m"] / 2, cap_style=2, join_style=2).intersection(foot)
    gaps = [door, *(geo.to_polygon(e.polygon).buffer(0.6) for e in exits or [])]
    return ring.difference(unary_union(gaps)), shell


def stairwell_walls(fid: str, walls: list[Any], height: float, first: int = 1) -> list[Obstacle]:
    out: list[Obstacle] = []
    for w in walls:
        for p in sorted(_parts(w), key=lambda p: (p.centroid.x, p.centroid.y)):
            if p.area >= 0.05:
                out.append(
                    Obstacle(
                        id=f"{fid.lower()}_stairwell_{first + len(out)}",
                        kind="wall",
                        polygon=geo.to_points(orient(Polygon(p.exterior), 1.0)),
                        height_m=height,
                        label="Stairwell wall",
                    )
                )
    return out


def _stairwells_only(
    foot: Polygon, cores: list[Core], exits: list[Any], fid: str, floor_height_m: float, level: int
) -> _Fitout:
    """An open floor's stairs, each in an enclosed stairwell with a door facing the floor."""
    walls, shells = [], []
    for c in cores:
        ring, shell = enclose_stair(c, foot, foot.centroid, exits, level)
        walls.append(ring)
        shells.append(shell)
    obstacles = stairwell_walls(fid, walls, round(floor_height_m - 0.3, 2))
    return _Fitout(obstacles, unary_union(shells) if shells else None)


def _clear_box(
    fr: _Frame, cands: list[tuple[float, float, float, float]], inside: Any, keep_clear: Any
) -> Polygon | None:
    """The first candidate box (local s0, t0, s1, t1) that fits inside the floor, clear of
    `keep_clear`; else the largest box left of one once its overlap is cut off across the
    building (a kitchen shortened to keep a street door free), never a curved leftover."""
    best: tuple[float, Polygon] | None = None
    for s0, t0, s1, t1 in cands:
        for q0, q1 in _free_spans(fr, (s0, s1), (t0, t1), keep_clear):
            cand = fr.to_world(box(s0, q0, s1, q1)).intersection(inside)
            if not isinstance(cand, Polygon) or cand.is_empty:
                continue
            if keep_clear is not None and cand.intersection(keep_clear).area > 0.05:
                continue
            if (q0, q1) == (t0, t1):
                return cand
            if best is None or cand.area > best[0]:
                best = (cand.area, cand)
    return best[1] if best is not None else None


def _free_spans(
    fr: _Frame, s_rng: tuple[float, float], t_rng: tuple[float, float], keep_clear: Any
) -> list[tuple[float, float]]:
    """The whole span `t_rng` when the box is clear, else the parts of it, across the building,
    that no part of `keep_clear` inside the box's length reaches."""
    t0, t1 = t_rng
    if keep_clear is None or keep_clear.is_empty:
        return [t_rng]
    hit = fr.to_local(keep_clear).intersection(box(s_rng[0], t0, s_rng[1], t1))
    if hit.is_empty or hit.area < 0.05:
        return [t_rng]
    spans = []
    for p in _parts(hit) or [hit]:
        _, y0, _, y1 = p.bounds
        spans.append((y0, y1))
    spans.sort()
    free, at = [], t0
    for y0, y1 in spans:
        if y0 > at:
            free.append((at, y0))
        at = max(at, y1)
    if at < t1:
        free.append((at, t1))
    return sorted(free, key=lambda q: -(q[1] - q[0]))


def _dining_fitout(
    fr: _Frame,
    foot: Polygon,
    cores: list[Core],
    exits: list[Any],
    fid: str,
    floor_height_m: float,
    level: int,
) -> _Fitout:
    """A restaurant floor: each stair in an enclosed stairwell with a door, a lift beside it,
    a kitchen and toilets at the end away from the stairs (kept off the street doors), and
    tables in rows with a main aisle kept clear."""
    fit = fitouts()["dining"]
    lift_m, table_m, pitch = fit["lift_m"], fit["table_m"], fit["table_pitch_m"]
    tall = round(floor_height_m - 0.3, 2)
    obstacles: list[Obstacle] = []
    inside = foot.buffer(-0.3)
    centre = foot.centroid
    walls: list[Any] = []
    shells: list[Polygon] = []
    for c in cores:
        ring, shell = enclose_stair(c, foot, centre, exits, level)
        walls.append(ring)
        shells.append(shell)
    # the way into each stairwell and out of each street door stays clear (square, not round,
    # so what is fitted round it keeps straight walls)
    doors = [geo.to_polygon(e.polygon).buffer(fit["exit_clear_m"], join_style=2) for e in exits]
    blocked = unary_union([*shells, *doors])

    def add(kind: str, label: str, poly: Polygon, height: float) -> None:
        obstacles.append(
            Obstacle(
                id=f"{fid.lower()}_{label.split()[0].lower()}_{len(obstacles) + 1}",
                kind=kind,
                polygon=geo.to_points(orient(poly, 1.0)),
                height_m=height,
                label=label,
            )
        )

    # a lift beside the first stairwell, along the building's long axis
    lift: Polygon | None = None
    if shells:
        sh = fr.to_local(shells[0])
        x0, y0, x1, y1 = sh.bounds
        for lx in (x1 + 0.3, x0 - 0.3 - lift_m):
            for ly in (y0, y1 - lift_m):
                cand = fr.to_world(box(lx, ly, lx + lift_m, ly + lift_m))
                if inside.contains(cand) and not cand.intersects(blocked):
                    lift = cand
                    break
            if lift is not None:
                break
    if lift is not None:
        add("other", FITOUT_LIFT, lift, tall)
        blocked = blocked.union(lift)

    # kitchen and toilets at the end of the long axis farther from the stairwells (the other
    # end when that one is taken); a street door there shortens them across, never cuts a curve
    core_s = fr.to_local(unary_union(shells)).centroid.x if shells else fr.s1
    lo, hi = fit["kitchen_m"]
    depth = min(max(fr.length * fit["kitchen_share"], lo), hi)
    tw, td = fit["toilets_m"]
    keep_clear = blocked.buffer(fit["clear_of_rooms_m"], join_style=2)
    ends = sorted((fr.s0, fr.s1), key=lambda e: -abs(core_s - e))
    kitchen = toilets = None
    for end in ends:
        sign = 1 if end == fr.s0 else -1
        k_s = (min(end, end + sign * depth), max(end, end + sign * depth))
        kitchen = _clear_box(fr, [(k_s[0], fr.t0, k_s[1], fr.t1)], inside, keep_clear)
        if kitchen is None or kitchen.area < 4:
            continue
        ks = fr.to_local(kitchen).bounds
        inner = ks[2] if sign > 0 else ks[0]  # the kitchen's side facing the dining room
        t_s = (min(inner, inner + sign * tw), max(inner, inner + sign * tw))
        taken = keep_clear.union(kitchen.buffer(0.01))
        toilets = _clear_box(
            fr,
            [(t_s[0], fr.t1 - td, t_s[1], fr.t1), (t_s[0], fr.t0, t_s[1], fr.t0 + td)],
            inside,
            taken,
        )
        break
    taken_parts: list[Any] = [*shells, *([lift] if lift is not None else [])]
    rooms: list[Polygon] = []
    for kind, label, poly in (("other", "Kitchen", kitchen), ("booth", "Toilets", toilets)):
        if poly is not None and poly.area >= 4:
            add(kind, label, poly, tall)
            taken_parts.append(poly)
            rooms.append(poly)
    blocked = unary_union([blocked, *rooms])

    # tables in rows, clear of walls, doors, stairs and the main aisle
    edge = fit["clear_of_walls_m"]
    room = foot.buffer(-edge).difference(blocked.buffer(fit["clear_of_rooms_m"]))
    tables = 0
    half = table_m / 2
    s = fr.s0 + edge + half
    while s < fr.s1 - edge and tables < fit["max_tables"]:
        t = fr.t0 + edge + half
        while t < fr.t1 - edge and tables < fit["max_tables"]:
            if abs(t) > fit["main_aisle_m"] / 2 + half:
                cand = fr.to_world(box(s - half, t - half, s + half, t + half))
                if room.contains(cand):
                    add("seating", "Table", cand, fit["table_height_m"])
                    tables += 1
            t += pitch
        s += pitch
    obstacles += stairwell_walls(fid, walls, tall, len(obstacles) + 1)
    return _Fitout(obstacles, unary_union(taken_parts) if taken_parts else None)


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
    rooms_fit = fitouts()["rooms"]
    corridor_w = _by_use(rooms_fit["corridor_m"], use)
    solid_free = foot.difference(solid.buffer(0.5)) if solid is not None else foot
    basements = plan.basements
    order = level_order(levels, basements)
    multi = len(order) > 1
    if plan.cores is not None:
        cores = list(plan.cores) if multi else []
    else:
        flight = round(min(STAIR_W, corridor_w - 0.2) - 0.4, 2)
        cores = _cores(fr, solid_free, flight, floor_height_m) if multi else []
    for lower in sorted(order)[:-1]:
        if not any(c.joins(lower, lower + 1) for c in cores):
            raise ValueError("No room for a stair inside this building outline.")
    if levels > 1 and len(cores) == 1 and plan.cores is None:
        notes.append("Only one stair fitted inside the outline; add a second one in the editor.")

    def cores_at(k: int) -> list[Core]:
        return [c for c in cores if c.span is None or c.span[0] <= k <= c.span[1]]

    def core_area(k: int) -> Any:
        shapes = [c.shaft for c in cores_at(k)]
        return unary_union(shapes).buffer(0.4) if shapes else None

    walls: Any = None
    band: Polygon | None = None
    # rooms the organizer counted are zones of their own (up to a dozen a floor; more are
    # grouped into areas like a map import, so a hotel floor is not 30 two-person zones)
    explicit_rooms = plan.rooms_per_floor is not None and plan.rooms_per_floor <= MAX_OWN_ROOMS
    if interior == "rooms":
        if fr.depth < corridor_w + 2 * rooms_fit["min_room_depth_m"] or fr.length < 12:
            notes.append(
                f"The building is {fr.depth:.0f} m deep: too shallow for rooms on both sides of "
                "a corridor, so its floors were left open. Add rooms and walls in the editor."
            )
            interior = "open"
        else:
            room_w = room_width(use)
            if plan.rooms_per_floor is not None:
                per_side = math.ceil(plan.rooms_per_floor / 2)
                room_w = fr.length / per_side
                if plan.rooms_per_floor % 2:
                    notes.append(
                        f"Laid out {2 * per_side} rooms per floor ({per_side} on each side of "
                        "the corridor); merge two in the editor if one fewer is right."
                    )
            door_w = _by_use(rooms_fit["door_w_m"], use)
            walls, band = _room_walls(fr, foot, corridor_w, room_w, door_w)

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
        fit: _Fitout | None = None
        if interior == "dining":
            fit = _dining_fitout(fr, foot, cores_at(k), exits_k, fid, floor_height_m, k)
        elif multi and interior in fitouts()["stairwell"]["interiors"] and cores_at(k):
            fit = _stairwells_only(foot, cores_at(k), exits_k, fid, floor_height_m, k)
        if fit is not None:
            # the layout already places its own lifts here: the fit-out does not add another
            words = tuple(fitouts()["dining"].get("lift_words", ()))
            own = any(any(w in (o.label or "").lower() for w in words) for o in [*solids, *extra])
            obstacles += [
                o for o in fit.obstacles if not (own and o.label == FITOUT_LIFT and words)
            ]
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
        if fit is not None and fit.taken is not None:
            free = free.difference(fit.taken.buffer(0.3))
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
        word = "Dining area" if interior == "dining" else "Floor area"
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
    for idx, c in enumerate(cores):
        letter = chr(ord("a") + idx)
        links = [(i, i - 1, str(i)) for i in range(1, levels) if c.joins(i - 1, i)]
        links += [(k, k + 1, f"b{-k}") for k in range(-basements, 0) if c.joins(k, k + 1)]
        for frm, to, tag in links:
            top, bottom = c.flight(frm, to)
            stairs.append(
                Stair(
                    id=f"stair_{letter}_{tag}",
                    from_floor=floor_id(frm),
                    to_floor=floor_id(to),
                    top_polygon=geo.to_points(orient(top, 1.0)),
                    bottom_polygon=geo.to_points(orient(bottom, 1.0)),
                    width_m=c.width_m,
                    length_m=c.length_m(floor_height_m),
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
            if layout == "dining":
                why.append(
                    "Each floor was fitted out as a typical restaurant (kitchen, toilets, tables, "
                    "a lift and an enclosed stairwell), not the real interior: check it on site."
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
