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
from typing import Any, Literal, get_args

from shapely.affinity import rotate, translate
from shapely.geometry import LineString, MultiPolygon, Polygon, box
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
    """Ground, 1st floor, 2nd floor, ..."""
    if i == 0:
        return "Ground"
    suffix = "th" if 10 <= i % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(i % 10, "th")
    return f"{i}{suffix} floor"


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


def _storeys(
    ground: Floor,
    levels: int,
    use: str | None,
    interior: Interior,
    floor_height_m: float,
    people: int | None,
) -> tuple[list[Floor], list[Stair], list[str], Interior]:
    notes: list[str] = []
    foot = orient(geo.to_polygon(ground.walkable), 1.0)
    solids = [o for o in ground.obstacles]  # courtyards and light wells, on every floor
    solid = unary_union([geo.to_polygon(o.polygon) for o in solids]) if solids else None
    fr = _Frame(foot)
    corridor_w = CORRIDOR_M.get(use or "", DEFAULT_CORRIDOR_M)
    solid_free = foot.difference(solid.buffer(0.5)) if solid is not None else foot
    cores = _cores(fr, solid_free, corridor_w) if levels > 1 else []
    if levels > 1 and not cores:
        raise ValueError("No room for a stair inside this building outline.")
    if levels > 1 and len(cores) == 1:
        notes.append("Only one stair fitted inside the outline; add a second one in the editor.")
    core_area = unary_union([g for c in cores for g in c]).buffer(0.4) if cores else None
    exits_area = unary_union([geo.to_polygon(e.polygon).buffer(1.2) for e in ground.exits])

    walls: Any = None
    band: Polygon | None = None
    if interior == "rooms":
        if fr.depth < corridor_w + 2 * MIN_ROOM_DEPTH or fr.length < 12:
            notes.append(
                f"The building is {fr.depth:.0f} m deep: too shallow for rooms on both sides of "
                "a corridor, so its floors were left open. Add rooms and walls in the editor."
            )
            interior = "open"
        else:
            walls, band = _room_walls(
                fr,
                foot,
                corridor_w,
                ROOM_W.get(use or "", DEFAULT_ROOM_W),
                DOOR_W.get(use or "", 1.0),
            )
            if core_area is not None:
                walls = walls.difference(core_area)

    load = LOAD_M2.get(use or "", DEFAULT_LOAD_M2)
    floors: list[Floor] = []
    zone_shapes: list[tuple[int, Polygon]] = []
    for i in range(levels):
        fid = f"F{i}"
        floor_walls = walls
        if i == 0 and floor_walls is not None:  # keep the mapped doors clear
            floor_walls = floor_walls.difference(exits_area)
        obstacles = [
            o.model_copy(update={"id": o.id if i == 0 else f"{o.id}_{fid.lower()}"}) for o in solids
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
        if core_area is not None:
            free = free.difference(core_area)
        for p in _parts(free):
            if p.area >= 6:
                zone_shapes.append((i, orient(p.simplify(0.2), 1.0)))
        floors.append(
            Floor(
                floor_id=fid,
                name=floor_name(i),
                elevation_m=round(i * floor_height_m, 2),
                walkable=ground.walkable,
                obstacles=obstacles,
                exits=ground.exits if i == 0 else [],
                zones=[],
            )
        )

    area = sum(p.area for _, p in zone_shapes)
    if not zone_shapes or area <= 0:
        raise ValueError("No room for people inside this building outline.")
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
    groups = _groups(use)
    rooms_per_floor: dict[int, int] = {}
    for k, (fi, p) in enumerate(zone_shapes):
        share = left if k == len(zone_shapes) - 1 else round(people * p.area / area)
        share = max(0, min(share, left))
        left -= share
        n = rooms_per_floor[fi] = rooms_per_floor.get(fi, 0) + 1
        label = ("Room" if band is not None else "Floor area") + f" {n}"
        if fi > 0:
            label += f" ({floor_name(fi)})"
        floors[fi].zones.append(
            Zone(
                id=f"f{fi}_zone_{n}",
                polygon=geo.to_points(p),
                people=share,
                label=label,
                groups=groups,
            )
        )

    stairs: list[Stair] = []
    for i in range(1, levels):
        for k, (top, bottom) in enumerate(cores):
            stairs.append(
                Stair(
                    id=f"stair_{'ab'[k]}_{i}",  # a and b: the two cores
                    from_floor=f"F{i}",
                    to_floor=f"F{i - 1}",
                    top_polygon=geo.to_points(orient(top, 1.0)),
                    bottom_polygon=geo.to_points(orient(bottom, 1.0)),
                    width_m=round(min(STAIR_W, corridor_w - 0.2) - 0.4, 2),
                    length_m=round(math.hypot(2 * STAIR_RUN + 1, floor_height_m), 2),
                )
            )
    return floors, stairs, notes, interior


def build_storeys(
    venue: Venue,
    *,
    levels: int = 1,
    use: EventKind | None = None,
    interior: Interior | None = None,
    floor_height_m: float = 3.5,
    people: int | None = None,
) -> tuple[Venue, list[str]]:
    """Stack `levels` storeys on the venue's one imported floor (rooms or open plan).

    Falls back to open floors, then to the single imported floor, when a layout does not
    validate (an odd outline), and says so in the notes.
    """
    if use is not None and use not in get_args(EventKind):
        raise ValueError(f"Unknown building use '{use}'.")
    levels = max(1, min(int(levels), MAX_LEVELS))
    interior = interior or default_interior(use)
    ground = venue.floors[0]
    notes: list[str] = []
    record = {
        "use": use,
        "levels": levels,
        "interior": interior,
        "floor_height_m": floor_height_m,
    }
    for layout in dict.fromkeys([interior, "open"]):
        try:
            floors, stairs, why, layout = _storeys(
                ground, levels, use, layout, floor_height_m, people
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
        problems = [c.message for c in validate_venue(out).checks if c.severity == "error"]
        if not problems:
            if levels > 1:
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
    notes.append("Kept the imported ground floor only.")
    return venue, notes
