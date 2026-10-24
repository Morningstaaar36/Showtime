"""Solver: VenueSpec (walls, regions, sizes) → Venue (exact, valid geometry).

Placement is deterministic. Objects that cannot be placed without blocking an exit or
overlapping something are left out and reported, so the designer agent can adjust the spec.
A spec with a `building` becomes several storeys (and basements) through
`api.core.building_gen.build_storeys`: stair cores, rooms off a corridor or open floors, and
exactly the headcount the spec gives for each level.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from api.core.building_gen import (
    DEFAULT_ROOM_W,
    ROOM_W,
    Core,
    StoreyPlan,
    build_storeys,
    floor_id,
    floor_name,
    level_order,
    place_core,
    split_holes,
)
from api.core.extensions import geometry as geo
from api.core.venue_parts import (
    PassagePart,
    area_exits,
    area_labels,
    area_shape,
    clear_of,
    dividers,
    heading_exits,
    solve_passages,
    walkable_with,
)
from api.models import Exit, Floor, Obstacle, StageParams, Stair, Venue, Zone
from api.models.venue import ObstacleKind
from api.models.venue_spec import (
    UPPER_WORDS,
    BuildingSpec,
    ExitSpec,
    FeatureSpec,
    UpperFloorSpec,
    VenueSpec,
    Wall,
    ZoneSpec,
)

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1

MARGIN_M = 1.5  # zones and features keep this far from the outer walls (less in small rooms)
STAGE_GAP_M = 2.0  # clear strip in front of the stage
EXIT_CLEAR_M = 3.0  # features keep this far from exits
UPPER_ELEVATION_M = 4.5
STAIR_LENGTH_M = 9.0  # 4.5 m rise at a comfortable slope

_REGIONS: dict[str, tuple[float, float, float, float]] = {  # u0, u1, v0, v1 (v = towards stage)
    "whole": (0, 1, 0, 1),
    "centre": (1 / 3, 2 / 3, 1 / 3, 2 / 3),
    "front": (0, 1, 2 / 3, 1),
    "middle": (0, 1, 1 / 3, 2 / 3),
    "back": (0, 1, 0, 1 / 3),
    "left": (0, 0.5, 0, 1),
    "right": (0.5, 1, 0, 1),
    "front_left": (0, 0.5, 0.5, 1),
    "front_right": (0.5, 1, 0.5, 1),
    "back_left": (0, 0.5, 0, 0.5),
    "back_right": (0.5, 1, 0, 0.5),
}
_KIND: dict[str, tuple[ObstacleKind, float]] = {  # spec kind → (obstacle kind, height m)
    "bar": ("bar", 3.0),
    "booth": ("booth", 2.5),
    "sound_desk": ("booth", 1.2),
    "toilets": ("booth", 2.5),
    "tent": ("booth", 3.0),
    "seating": ("seating", 0.8),
    "column": ("column", 4.0),
    "barrier": ("barrier", 1.1),
    "escalator": ("other", 1.2),
    "other": ("other", 2.0),
}
EVERY_LEVEL = ("escalator", "column")  # features that run through a building's storeys
ATRIUM_SHARE = 0.3  # an atrium void spans this share of the floor's width and depth


@dataclass
class BuildResult:
    """The venue plus what the solver had to change or leave out."""

    venue: Venue
    notes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)  # solver changes the organizer should know
    problems: list[str] = field(default_factory=list)  # what the spec must change (to the model)


def _facing(spec: VenueSpec) -> Wall:
    """The wall the crowd faces: the stage wall, north without a stage or with a central one."""
    if spec.stage is None or spec.stage.wall == "centre":
        return "north"
    return spec.stage.wall


def _frame(stage_wall: Wall, inner: Rect, u0: float, u1: float, v0: float, v1: float) -> Rect:
    """Region fractions (u across, v towards the stage) → rectangle in venue coordinates."""
    x0, y0, x1, y1 = inner
    w, d = x1 - x0, y1 - y0
    if stage_wall == "north":
        xs, ys = (x0 + u0 * w, x0 + u1 * w), (y0 + v0 * d, y0 + v1 * d)
    elif stage_wall == "south":
        xs, ys = (x1 - u1 * w, x1 - u0 * w), (y1 - v1 * d, y1 - v0 * d)
    elif stage_wall == "east":
        xs, ys = (x0 + v0 * w, x0 + v1 * w), (y1 - u1 * d, y1 - u0 * d)
    else:  # west
        xs, ys = (x1 - v1 * w, x1 - v0 * w), (y0 + u0 * d, y0 + u1 * d)
    return (min(xs), min(ys), max(xs), max(ys))


def _inner(spec: VenueSpec, margin: float = MARGIN_M) -> Rect:
    """Area left for people and features: inside the margin and clear of the stage."""
    m = min(margin, 0.08 * min(spec.width_m, spec.depth_m))
    x0, y0, x1, y1 = m, m, spec.width_m - m, spec.depth_m - m
    if spec.stage is not None and spec.stage.wall != "centre":
        cut = spec.stage.depth_m + STAGE_GAP_M
        side = spec.stage.wall
        if side == "north":
            y1 = min(y1, spec.depth_m - cut)
        elif side == "south":
            y0 = max(y0, cut)
        elif side == "east":
            x1 = min(x1, spec.width_m - cut)
        else:
            x0 = max(x0, cut)
    return (x0, y0, max(x1, x0 + 1), max(y1, y0 + 1))


def _wall_span(spec: VenueSpec, wall: Wall) -> float:
    return spec.width_m if wall in ("north", "south") else spec.depth_m


def _against(spec: VenueSpec, wall: Wall, center: float, along: float, depth: float) -> Rect:
    """Rectangle touching `wall` (0.5 m inset), centred at `center` along the wall."""
    w, d, inset = spec.width_m, spec.depth_m, 0.5
    if wall == "north":
        return (center - along / 2, d - inset - depth, center + along / 2, d - inset)
    if wall == "south":
        return (center - along / 2, inset, center + along / 2, inset + depth)
    if wall == "east":
        return (w - inset - depth, center - along / 2, w - inset, center + along / 2)
    return (inset, center - along / 2, inset + depth, center + along / 2)


def _stage_rect(spec: VenueSpec) -> Rect:
    st = spec.stage
    assert st is not None
    if st.wall == "centre":  # free-standing, people all round
        width, depth = min(st.width_m, spec.width_m - 8), min(st.depth_m, spec.depth_m - 8)
        cx, cy = spec.width_m / 2, spec.depth_m / 2
        return (cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2)
    span = _wall_span(spec, st.wall)
    width = min(st.width_m, span - 4)
    depth = min(
        st.depth_m, (_wall_span(spec, "east" if st.wall in ("north", "south") else "north")) / 3
    )
    w, d = spec.width_m, spec.depth_m
    c = span / 2
    if st.wall == "north":
        return (c - width / 2, d - depth, c + width / 2, d)
    if st.wall == "south":
        return (c - width / 2, 0, c + width / 2, depth)
    if st.wall == "east":
        return (w - depth, c - width / 2, w, c + width / 2)
    return (0, c - width / 2, depth, c + width / 2)


def _exit_name(wall: Wall, n: int, total: int, outdoor: bool) -> str:
    kind = "gate" if outdoor else "door"
    return f"{wall.capitalize()} {kind}" + (f" {n}" if total > 1 else "")


def _place_exits(
    spec: VenueSpec,
    items: list[ExitSpec],
    walkable: list[tuple[float, float]],
    blocked: Polygon | None,
    notes: list[str],
    prefix: str = "",
    where: str = "",
) -> list[tuple[ExitSpec, Exit]]:
    """Exits on their walls, each at the nearest free position to the one asked for."""
    placed: list[tuple[ExitSpec, Exit]] = []
    per_wall: dict[str, list[ExitSpec]] = defaultdict(list)
    for e in items:
        per_wall[e.wall].append(e)
    outdoor = spec.mode == "outdoor"
    for wall, group in per_wall.items():
        span = _wall_span(spec, wall)  # type: ignore[arg-type]
        taken: list[tuple[float, float]] = []
        for i, e in enumerate(sorted(group, key=lambda x: x.position), start=1):
            width = min(e.width_m, span - 2)
            half = width / 2
            lo, hi = half + 0.5, span - half - 0.5
            want = min(max(e.position * span, lo), hi)
            # nearest free position: not behind the stage, 1 m clear of other exits on this wall
            options = sorted(
                (lo + k * 0.5 for k in range(int((hi - lo) / 0.5) + 1)), key=lambda c: abs(c - want)
            )
            chosen: list[tuple[float, float]] | None = None
            for c in options:
                if any(c - half < b + 1 and c + half > a - 1 for a, b in taken):
                    continue
                pts = geo.exit_on_wall(walkable, wall, c, width)  # type: ignore[arg-type]
                if blocked is not None and geo.to_polygon(pts).buffer(0.5).intersects(blocked):
                    continue
                chosen = pts
                if abs(c - want) > 1:
                    notes.append(
                        f"Moved the {wall} exit {i}{where} by {abs(c - want):.0f} m "
                        "to keep it clear."
                    )
                taken.append((c - half, c + half))
                break
            if chosen is None:
                notes.append(f"No room for exit {i} on the {wall} wall{where}; left it out.")
                continue
            label = e.label or _exit_name(wall, i, len(group), outdoor)  # type: ignore[arg-type]
            kind = "gate" if outdoor else "door"
            placed.append(
                (
                    e,
                    Exit(
                        id=f"{prefix}{kind}_{wall[0]}{i}",
                        polygon=chosen,
                        width_m=round(width, 2),
                        label=label,
                    ),
                )
            )
    return placed


def _distinct_labels(exits: list[Exit]) -> list[Exit]:
    """Number repeated labels ("South gate" ×3 → "South gate 1", "South gate 2", ...)."""
    counts: dict[str, int] = defaultdict(int)
    for e in exits:
        counts[(e.label or "").strip().lower()] += 1
    seen: dict[str, int] = defaultdict(int)
    out: list[Exit] = []
    for e in exits:  # wall by wall, each wall from its west (or south) end
        key = (e.label or "").strip().lower()
        if e.label and counts[key] > 1:
            seen[key] += 1
            e = e.model_copy(update={"label": f"{e.label.strip()} {seen[key]}"})
        out.append(e)
    return out


SHRINK_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)  # a feature may lose up to half its length


def _place_feature(
    spec: VenueSpec, f: FeatureSpec, slot: tuple[int, int], inner: Rect, avoid: Polygon
) -> tuple[Rect, float] | None:
    """Slide the feature along its wall (or around its region) clear of `avoid`; if no
    position fits, shorten it step by step down to half its length. Returns the rectangle
    and the length factor used, or None when even the half-length feature does not fit."""
    for factor in SHRINK_STEPS:
        r = _slide_feature(spec, f, slot, inner, avoid, factor)
        if r is not None:
            return r, factor
    return None


def _slide_feature(
    spec: VenueSpec,
    f: FeatureSpec,
    slot: tuple[int, int],
    inner: Rect,
    avoid: Polygon,
    factor: float,
) -> Rect | None:
    """First position (from the preferred one outward) that overlaps nothing in `avoid`."""
    stage_wall = _facing(spec)
    along, depth = f.width_m * factor, f.depth_m
    if f.place in ("north", "south", "east", "west"):
        wall: Wall = f.place
        span = _wall_span(spec, wall)
        along = min(along, span - 2)
        n, k = slot
        prefer = span * (k + 1) / (n + 1)
        cands = [prefer + s * dd * 0.5 for dd in range(0, int(2 * span)) for s in (1, -1)]
        rects = [_against(spec, wall, c, along, depth) for c in cands]
    else:
        rx0, ry0, rx1, ry1 = _frame(stage_wall, inner, *_REGIONS[f.place])
        if stage_wall in ("east", "west"):
            along, depth = depth, along  # width runs across the room as seen from the crowd
        cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        steps = [(dx, dy) for r in range(0, 30) for dx in (-r, 0, r) for dy in (-r, 0, r)]
        rects = [
            (cx + dx - along / 2, cy + dy - depth / 2, cx + dx + along / 2, cy + dy + depth / 2)
            for dx, dy in dict.fromkeys(steps)
        ]
    outline = box(0.3, 0.3, spec.width_m - 0.3, spec.depth_m - 0.3)
    for r in rects:
        cand = box(*r)
        if outline.contains(cand) and not cand.intersects(avoid):
            return r
    return None


def _upper_floor(
    spec: VenueSpec, up: UpperFloorSpec, notes: list[str]
) -> tuple[Floor, Stair, Obstacle]:
    """Balcony floor along the north wall (mirrored for south) with one straight stair."""
    w, d = spec.width_m, spec.depth_m
    depth = min(up.depth_m, d - STAIR_LENGTH_M - 6)
    if depth < up.depth_m:
        notes.append(f"Made the {up.label.lower()} {depth:.0f} m deep so its stair fits.")
    sw = up.stair_width_m
    sx0 = w - 1 - sw - 0.5 if up.stair_end == "east" else 1.5
    sx1 = sx0 + sw
    edge = d - depth  # inner edge of the balcony
    top = geo.rect(sx0, edge + 0.5, sx1, edge + 3.5)
    bottom = geo.rect(sx0, edge - STAIR_LENGTH_M - 3, sx1, edge - STAIR_LENGTH_M)
    structure = geo.rect(sx0 - 0.3, edge - STAIR_LENGTH_M, sx1 + 0.3, edge)
    walk = geo.rect(0, edge, w, d)
    zone = box(1, edge + 1, w - 1, d - 1).difference(box(*_bounds(top)).buffer(1.0))
    zone_poly = geo.largest_part(zone)

    def flip(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return pts if up.along == "north" else [(x, d - y) for x, y in reversed(pts)]

    floor = Floor(
        floor_id="F1",
        name=up.label,
        elevation_m=UPPER_ELEVATION_M,
        walkable=flip(walk),
        zones=[
            Zone(
                id="upper", polygon=flip(geo.to_points(zone_poly)), people=up.people, label=up.label
            )
        ],
    )
    stair = Stair(
        id="stair_1",
        from_floor="F1",
        to_floor="F0",
        top_polygon=flip(top),
        bottom_polygon=flip(bottom),
        width_m=sw,
        length_m=STAIR_LENGTH_M,
    )
    obstacle = Obstacle(
        id="stair_structure",
        kind="other",
        polygon=flip(structure),
        height_m=UPPER_ELEVATION_M,
        label="Stair structure",
    )
    return floor, stair, obstacle


def _bounds(pts: list[tuple[float, float]]) -> Rect:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _stage_parts(spec: VenueSpec, notes: list[str]) -> tuple[list[Obstacle], StageParams | None]:
    """Stage (and its front barrier) as obstacles, plus the wind-check structure outdoors."""
    if spec.stage is None:
        return [], None
    W, D = spec.width_m, spec.depth_m
    sr = _stage_rect(spec)
    obstacles = [
        Obstacle(
            id="stage",
            kind="stage",
            polygon=geo.rect(*sr),
            label="Stage",
            height_m=spec.stage.roof_height_m if spec.mode == "outdoor" else 1.0,
        )
    ]
    params: StageParams | None = None
    if spec.mode == "outdoor":
        sw, sd = sr[2] - sr[0], sr[3] - sr[1]
        params = StageParams(
            width_m=round(max(sw, sd), 1),
            depth_m=round(min(sw, sd), 1),
            roof_height_m=spec.stage.roof_height_m,
            roof_area_m2=round(sw * sd, 1),
            legs=6 if max(sw, sd) >= 12 else 4,
            ballast_kg_per_leg=2000,
            friction_coeff=0.5,
            force_coeff=1.3,
            banner_area_m2=60,
        )
    if spec.front_barrier and spec.stage.wall == "centre":
        notes.append("A crowd barrier round a central stage is not drawn; add it in the editor.")
    elif spec.front_barrier:
        gap = STAGE_GAP_M / 2
        x0, y0, x1, y1 = sr
        line = {
            "north": [(x0 - 3, y0 - gap), (x1 + 3, y0 - gap)],
            "south": [(x0 - 3, y1 + gap), (x1 + 3, y1 + gap)],
            "east": [(x0 - gap, y0 - 3), (x0 - gap, y1 + 3)],
            "west": [(x1 + gap, y0 - 3), (x1 + gap, y1 + 3)],
        }[spec.stage.wall]
        line = [(min(max(x, 0.5), W - 0.5), min(max(y, 0.5), D - 0.5)) for x, y in line]
        obstacles.append(
            Obstacle(
                id="front_barrier",
                kind="barrier",
                polygon=geo.barrier_polygon(line, 0.3),
                line=line,
                height_m=1.1,
                label="Front-of-stage barrier",
            )
        )
    return obstacles, params


def _features(
    spec: VenueSpec,
    features: list[FeatureSpec],
    avoid: list[Polygon],
    used_ids: set[str],
    notes: list[str],
    assumptions: list[str],
    suffix: str = "",
) -> list[Obstacle]:
    """Place features clear of `avoid` (exits, stage, stairs) and of each other."""
    inner = _inner(spec)
    placed = list(avoid)
    per_wall: dict[str, int] = defaultdict(int)
    for f in features:
        if f.place in ("north", "south", "east", "west"):
            per_wall[f.place] += 1
    seen: dict[str, int] = defaultdict(int)
    out: list[Obstacle] = []
    for f in features:
        k = seen[f.place]
        seen[f.place] += 1
        got = _place_feature(spec, f, (per_wall.get(f.place, 1), k), inner, unary_union(placed))
        name = f.label or f.kind.replace("_", " ").capitalize()
        if got is None:
            notes.append(f"Left out “{name}”: no free spot that keeps exits and walkways clear.")
            continue
        r, factor = got
        if factor < 1.0:
            assumptions.append(
                f"Shortened “{name}” from {f.width_m:g} m to {f.width_m * factor:.1f} m so it "
                "keeps the exits and walkways clear."
            )
        kind, height = _KIND[f.kind]
        base = f.kind if f.kind != "other" else "feature"
        n, oid = 1, f"{base}_1{suffix}"
        while oid in used_ids:
            n += 1
            oid = f"{base}_{n}{suffix}"
        used_ids.add(oid)
        poly = geo.rect(*r)
        out.append(Obstacle(id=oid, kind=kind, polygon=poly, height_m=height, label=name))
        placed.append(geo.to_polygon(poly).buffer(1.0))
    return out


def build_venue(spec: VenueSpec, venue_id: str = "draft") -> BuildResult:
    """Solve a spec into a venue. Never raises for layout problems; reports them in notes."""
    if spec.building is not None:
        if spec.mode == "outdoor":
            res = _build_single(spec.model_copy(update={"building": None}), venue_id)
            res.problems.append(
                "An open-air site has one level: set mode to indoor for a building with "
                "storeys, or set building to null."
            )
            return res
        b = spec.building
        if b.storeys == 1 and not b.basements and b.interior == "open":
            # one open level is a hall: keep its regions, stage front and balcony. The ground
            # zone holds the main floor only: the balcony's people are built with the balcony.
            per = spec.level_people()
            up = spec.upper_floor.people if spec.upper_floor is not None else 0
            ground = per[0] if per else max(spec.total_people() - up, 0)
            zones = spec.zones or (
                [ZoneSpec(label=b.room_label or "People", people=ground)] if ground else []
            )
            return _build_single(
                spec.model_copy(update={"building": None, "zones": zones}), venue_id
            )
        return _build_building(spec, b, venue_id)
    return _build_single(spec, venue_id)


def _build_single(spec: VenueSpec, venue_id: str) -> BuildResult:
    """One floor (plus an optional balcony): the hall, field or square of the spec, with the
    passages that lead off it and the fences that split it into pens."""
    notes: list[str] = []
    assumptions: list[str] = []
    problems: list[str] = []
    D = spec.depth_m
    parts = solve_passages(spec, problems, notes, assumptions)
    walkable = walkable_with(spec, parts)
    main_floor = geo.rect(0, 0, spec.width_m, D)
    obstacles, stage_params = _stage_parts(spec, notes)
    stage_poly = geo.to_polygon(obstacles[0].polygon) if spec.stage is not None else None
    obstacles += dividers(spec)

    upper = stair = None
    if spec.upper_floor is not None:
        if spec.mode == "outdoor":
            notes.append("Open-air sites have one level; the upper floor was left out.")
        elif D < STAIR_LENGTH_M + 12:
            notes.append(f"The venue is too shallow ({D:.0f} m) for a balcony with a stair.")
        else:
            upper, stair, structure = _upper_floor(spec, spec.upper_floor, notes)
            obstacles.append(structure)

    lower = [e for e in spec.exits if e.level != 0]
    if lower:
        notes.append(
            "Exits on other levels need a building: put them on the ground floor or describe "
            "the storeys in building."
        )
    # exits stay off the stage, the passage openings and the fences
    keep_off = [g for g in [stage_poly] if g is not None]
    keep_off += [p.opening for p in parts]
    keep_off += [geo.to_polygon(o.polygon) for o in obstacles if o.id.startswith("divider_")]
    blocked = unary_union(keep_off) if keep_off else None
    exits = _distinct_labels(
        [x for _, x in _place_exits(spec, spec.exits, main_floor, blocked, notes)]
    )
    exits += [x for p in parts for x in p.exits]
    if not exits:
        notes.append("No exit could be placed. Add at least one exit on a free wall.")
    if not spec.zones:
        problems.append("No people: add a zone with the headcount.")
    obstacles += [o for p in parts for o in p.obstacles]

    exit_clear = [geo.to_polygon(e.polygon).buffer(EXIT_CLEAR_M) for e in exits]
    avoid: list[Polygon] = [geo.to_polygon(o.polygon).buffer(1.0) for o in obstacles]
    avoid += [p.opening.buffer(1.0) for p in parts]
    if stair is not None:
        avoid.append(geo.to_polygon(stair.bottom_polygon).buffer(1.5))
    obstacles += _features(
        spec, spec.features, [*avoid, *exit_clear], {o.id for o in obstacles}, notes, assumptions
    )

    blockers = unary_union([geo.to_polygon(o.polygon).buffer(0.3) for o in obstacles])
    if stair is not None:
        blockers = blockers.union(geo.to_polygon(stair.bottom_polygon).buffer(1.0))
    placed = _single_zones(spec, upper is not None, blockers, notes)
    placed += _area_zones(spec, parts, blockers, exits, problems)
    zones = _with_headings(spec, placed, exits, problems, parts)
    floors = [
        Floor(
            floor_id="F0",
            name="Ground",
            walkable=walkable,
            obstacles=obstacles,
            exits=exits,
            zones=zones,
        )
    ]
    if upper is not None:
        floors.append(upper)
    venue = Venue(
        venue_id=venue_id,
        name=spec.name,
        description="Generated from a description; check sizes against the real site.",
        mode=spec.mode,
        floors=floors,
        stairs=[stair] if stair is not None else [],
        stage=stage_params,
        extensions={
            "generated": {"from": "description", "assumptions": [*spec.assumptions, *assumptions]}
        },
    )
    return BuildResult(venue=venue, notes=notes, assumptions=assumptions, problems=problems)


DENSE_PPM2 = 3.5  # a zone this dense uses the floor up to TIGHT_MARGIN_M from the walls
TIGHT_MARGIN_M = 0.4


def _single_zones(
    spec: VenueSpec, has_upper: bool, blockers: Any, notes: list[str]
) -> list[tuple[int, Zone]]:
    """Each region once, split across the zones sharing it, never overlapping each other.
    Returns each zone with the index of the spec zone it comes from."""
    stage_wall = _facing(spec)
    inner = _inner(spec)
    tight = _inner(spec, TIGHT_MARGIN_M)
    used: Polygon = Polygon()
    zones: list[tuple[int, Zone]] = []
    by_region: dict[str, list[int]] = defaultdict(list)
    for i, z in enumerate(spec.zones):
        if z.area is not None:
            continue  # in a passage or the area at its end (_area_zones)
        if has_upper and any(w in z.label.lower() for w in UPPER_WORDS):
            notes.append(f"“{z.label}” is on the upper floor, so it was not added downstairs too.")
            continue
        by_region[z.region].append(i)
    order = sorted(by_region, key=lambda r: list(_REGIONS).index(r), reverse=True)  # small first
    for region in order:
        idx = by_region[region]
        u0, u1, v0, v1 = _REGIONS[region]
        for j, i in enumerate(idx):
            a = u0 + (u1 - u0) * j / len(idx)
            b = u0 + (u1 - u0) * (j + 1) / len(idx)
            z = spec.zones[i]
            rect = box(*_frame(stage_wall, inner, a, b, v0, v1)).buffer(-0.3)
            if z.people > DENSE_PPM2 * max(rect.area, 1e-9):  # a packed crowd: up to the walls
                rect = box(*_frame(stage_wall, tight, a, b, v0, v1)).buffer(-0.3)
            area = rect.difference(blockers).difference(used)
            if area.is_empty or area.area < 4:
                notes.append(f"No room left for “{z.label}”; overlapping zones were merged away.")
                continue
            if spec.dividers:  # a crowd across several pens: every pen gets its share
                found = [g for g in getattr(area, "geoms", [area]) if g.area >= 4]
                parts = [g.simplify(0.05) for g in found]
            else:
                parts = [geo.largest_part(area).simplify(0.05)]
            for part in parts:
                used = used.union(part)
            # a crowd all round a central stage: two halves, as zones have no holes
            pieces = [q for part in parts for q in split_holes(part) if q.area >= 1] or parts
            counts = _split_people(z.people, [q.area for q in pieces])
            for n, (q, people) in enumerate(zip(pieces, counts, strict=True), start=1):
                zid = "zone_" + str(len(zones) + 1)
                label = z.label if len(pieces) == 1 else f"{z.label} {n}"
                zones.append(
                    (i, Zone(id=zid, polygon=geo.to_points(q), people=people, label=label))
                )
    return zones


def _area_zones(
    spec: VenueSpec, parts: list[PassagePart], blockers: Any, exits: list[Exit], problems: list[str]
) -> list[tuple[int, Zone]]:
    """People standing in a passage or in the area at its end."""
    out: list[tuple[int, Zone]] = []
    keep = unary_union([blockers, *[geo.to_polygon(e.polygon).buffer(1.0) for e in exits]])
    for i, z in enumerate(spec.zones):
        if z.area is None:
            continue
        shape = area_shape(parts, z.area)
        if shape is None:
            names = ", ".join(f"“{n}”" for n in area_labels(parts)) or "none"
            problems.append(
                f"“{z.label}” stands in “{z.area}”, but no passage or end area has that name "
                f"(there are: {names}); use one of those labels or leave area empty."
            )
            continue
        q = clear_of(shape, keep)
        if q is None:
            problems.append(f"No room for “{z.label}” in “{z.area}”: make it larger.")
            continue
        out.append(
            (
                i,
                Zone(
                    id=f"area_{len(out) + 1}",
                    polygon=geo.to_points(q),
                    people=z.people,
                    label=z.label,
                ),
            )
        )
    return out


def _with_headings(
    spec: VenueSpec,
    zones: list[tuple[int, Zone]],
    exits: list[Exit],
    problems: list[str],
    parts: list[Any] | None = None,
) -> list[Zone]:
    """Zones whose people are going somewhere get those exits; ids are renumbered in order."""
    out: list[Zone] = []
    for n, (i, z) in enumerate(zones, start=1):
        heading = spec.zones[i].heading
        targets: list[str] = []
        if heading:
            # an exit's name, or a passage's ("heading for the ramp": its ways out)
            targets = heading_exits(exits, heading) or area_exits(parts or [], heading)
            if not targets:
                names = ", ".join(f"“{e.label}”" for e in exits)
                problems.append(
                    f"“{z.label}” heads for “{heading}”, but no exit has that name "
                    f"(there are: {names}); use an exit label or leave heading empty."
                )
        out.append(z.model_copy(update={"id": f"zone_{n}", "exit_ids": targets}))
    return out


def _split_people(total: int, weights: list[float]) -> list[int]:
    """`total` in proportion to `weights`, adding up exactly."""
    s = sum(weights) or 1.0
    out = [int(total * w / s) for w in weights]
    out[0] += total - sum(out)
    return out


# --- buildings with storeys ------------------------------------------------------------------


def _level_people(
    spec: VenueSpec, b: BuildingSpec, problems: list[str], assumptions: list[str]
) -> list[int] | None:
    """Exact headcount per level (lowest first), or None to estimate from floor area."""
    numbers = b.level_numbers
    n = len(numbers)
    where = f"{n} levels, {numbers[0]} to {numbers[-1]} (0 is street level)"
    for lv in b.levels:
        if lv.level not in numbers:
            problems.append(
                f"building.levels lists level {lv.level}, but the building has {where}: "
                "change storeys or basements, or that level."
            )
    per = spec.level_people()
    if per is not None:
        return per
    total = spec.total_people()
    if n == 1 and total:
        return [total]
    if total:
        problems.append(
            f"The building has {where}: give its headcount as building.people_per_floor (the "
            "same on every level) and building.levels for levels that differ, not as zones."
        )
        base, extra = divmod(total, n)
        assumptions.append(f"Spread {total:,} people evenly over the {n} levels.")
        return [base + (1 if i < extra else 0) for i in range(n)]
    problems.append("No headcount: set building.people_per_floor or building.levels.")
    return None


def _room_doors(spec: VenueSpec, b: BuildingSpec, exits: list[ExitSpec]) -> list[ExitSpec]:
    """Exits on the long walls of a room layout moved to the middle of the nearest room.

    Rooms line both long walls; a door where two rooms meet would cut their dividing wall
    and merge them. Doors on the end walls open onto the corridor and stay where they are.
    """
    long_walls = ("north", "south") if spec.width_m >= spec.depth_m else ("east", "west")
    length = max(spec.width_m, spec.depth_m)
    if b.rooms_per_floor is not None:
        n = math.ceil(b.rooms_per_floor / 2)
    else:
        n = max(1, round(length / ROOM_W.get(b.use or "", DEFAULT_ROOM_W)))
    out: list[ExitSpec] = []
    for e in exits:
        if e.wall in long_walls:
            k = min(n - 1, max(0, math.floor(e.position * n)))
            e = e.model_copy(update={"position": (k + 0.5) / n})
        out.append(e)
    return out


def _trim_empty_storeys(
    spec: VenueSpec, b: BuildingSpec, per: list[int] | None, notes: list[str]
) -> tuple[BuildingSpec, list[int] | None]:
    """Above a basement venue, storeys with nobody, no exit and no feature are left out.

    "A basement club" or "an underground platform" sometimes arrives with an extra empty
    storey on top; it changes nothing for the way out, so the solver drops it and says so.
    """
    if not b.basements or per is None:
        return b, per
    storeys = b.storeys
    while storeys > 1:
        k = storeys - 1
        used = per[b.basements + k] or any(e.level == k for e in spec.exits)
        if used or any(f.level == k for f in spec.features):
            break
        notes.append(f"Dropped the empty {floor_name(k).lower()} (no people, exits or features).")
        storeys -= 1
    if storeys == b.storeys:
        return b, per
    return b.model_copy(update={"storeys": storeys}), per[: b.basements + storeys]


def _core_target(spec: VenueSpec, place: str) -> tuple[float, float]:
    W, D = spec.width_m, spec.depth_m
    return {
        "west": (1.0, D / 2),
        "east": (W - 1.0, D / 2),
        "south": (W / 2, 1.0),
        "north": (W / 2, D - 1.0),
    }.get(place, (W / 2, D / 2))


def _build_building(spec: VenueSpec, b: BuildingSpec, venue_id: str) -> BuildResult:
    """Storeys and basements on the spec's footprint, built by `build_storeys`."""
    notes: list[str] = []
    assumptions: list[str] = []
    problems: list[str] = []
    if spec.passages or spec.dividers:
        problems.append(
            "Passages and dividers are drawn on one-level sites only: set building to null, or "
            "describe the tunnel or corridor as part of a storey."
        )
    W, D = spec.width_m, spec.depth_m
    per = _level_people(spec, b, problems, assumptions)
    b, per = _trim_empty_storeys(spec, b, per, notes)
    levels = level_order(b.storeys, b.basements)
    lowest, top = -b.basements, b.storeys - 1
    names = {lv.level: lv.name for lv in b.levels if lv.name and lowest <= lv.level <= top}
    if spec.upper_floor is not None:
        notes.append("A balcony is not drawn inside a building with storeys; add it in the editor.")
    if spec.zones and spec.level_people() is not None:
        notes.append("The building's headcount per level was used; its zones were left out.")

    stage_obs, _ = _stage_parts(spec, notes)
    stage_poly = geo.to_polygon(stage_obs[0].polygon) if stage_obs else None
    exits, via_stair = _street_exits(spec, b, stage_poly, problems, notes)
    void: Polygon | None = None
    if b.interior == "atrium" and b.storeys > 1:
        vw, vd = max(4.0, W * ATRIUM_SHARE), max(4.0, D * ATRIUM_SHARE)
        void = box(W / 2 - vw / 2, D / 2 - vd / 2, W / 2 + vw / 2, D / 2 + vd / 2)
    keep_clear = [unary_union([geo.to_polygon(x.polygon) for x in exits]).buffer(2.0)]
    if stage_poly is not None:
        keep_clear.append(stage_poly.buffer(1.5))
    if void is not None:
        keep_clear.append(void.buffer(0.8))
    cores = _stair_cores(spec, b, exits, via_stair, keep_clear, names, problems, assumptions)

    # obstacles by level: stage, atrium void and features (escalators and columns on every level)
    level_obs: dict[int, list[Obstacle]] = defaultdict(list)
    level_obs[0] += stage_obs
    for k in levels:
        if void is not None and k > 0:
            level_obs[k].append(
                Obstacle(
                    id=f"atrium_void_{floor_id(k).lower()}",
                    kind="other",
                    polygon=geo.to_points(void),
                    height_m=1.1,
                    label="Atrium (open to below)",
                )
            )
    avoid = [g.buffer(1.5) for c in cores for g in (c.a, c.b)]
    avoid += [geo.to_polygon(x.polygon).buffer(EXIT_CLEAR_M) for x in exits]
    if void is not None:
        avoid.append(void.buffer(1.0))
    _building_features(spec, b, per, avoid, level_obs, problems, notes, assumptions)

    ground = Venue(
        venue_id=venue_id,
        name=spec.name,
        mode="indoor",
        floors=[Floor(floor_id="F0", name="Ground", walkable=geo.rect(0, 0, W, D), exits=exits)],
    )
    rooms = b.interior == "rooms"
    plan = StoreyPlan(
        basements=b.basements,
        floor_people=per,
        cores=cores,
        rooms_per_floor=b.rooms_per_floor if rooms else None,
        level_obstacles=dict(level_obs),
        zone_word=b.room_label,
        floor_names=names,
    )
    built, more = build_storeys(
        ground,
        levels=b.storeys,
        use=b.use,
        interior="rooms" if rooms else "open",
        floor_height_m=b.floor_height_m,
        plan=plan,
    )
    if "building" not in built.extensions:  # no layout fitted: the model must change the spec
        problems += [n for n in more if n != "Kept the imported ground floor only."]
    else:
        notes += more
    venue = built.model_copy(
        update={
            "description": "Generated from a description; check sizes against the real site.",
            "extensions": {
                **built.extensions,
                "generated": {
                    "from": "description",
                    "assumptions": [*spec.assumptions, *assumptions],
                },
            },
        }
    )
    return BuildResult(venue=venue, notes=notes, assumptions=assumptions, problems=problems)


def _street_exits(
    spec: VenueSpec,
    b: BuildingSpec,
    stage_poly: Polygon | None,
    problems: list[str],
    notes: list[str],
) -> tuple[list[Exit], list[tuple[Exit, int]]]:
    """Every exit is a street door; one asked on another level also gets a stair to it.

    Returns the doors and, for each door reached by its own stair, that stair's far level
    (a basement: the stair goes up; an upper floor: an escape stair down).
    """
    lowest, top = -b.basements, b.storeys - 1
    asked = list(spec.exits)
    if b.interior == "rooms":  # a door in a long wall opens into the middle of a room
        asked = _room_doors(spec, b, asked)
    doors: list[ExitSpec] = []
    far: dict[int, int] = {}  # id of a door's spec → level its own stair comes from
    for e in asked:
        level = e.level
        if not lowest <= level <= top:
            problems.append(
                f"“{e.label or f'the {e.wall} exit'}” is on level {level}, but the building's "
                f"levels run from {lowest} to {top}: set its level (0 is street level)."
            )
            level = 0
        door = e.model_copy(update={"level": 0})
        if level != 0:
            far[id(door)] = level
        doors.append(door)
    if not doors:
        problems.append("No exit on street level (level 0): add the main door or gate there.")
    walkable = geo.rect(0, 0, spec.width_m, spec.depth_m)
    placed = _place_exits(spec, doors, walkable, stage_poly, notes)
    exits = _distinct_labels([x for _, x in placed])
    if not exits:
        notes.append("No exit could be placed. Add at least one exit on a free wall.")
    via = [(x, far[id(src)]) for (src, _), x in zip(placed, exits, strict=True) if id(src) in far]
    return exits, via


def _stair_cores(
    spec: VenueSpec,
    b: BuildingSpec,
    exits: list[Exit],
    via_stair: list[tuple[Exit, int]],
    keep_clear: list[Any],
    names: dict[int, str],
    problems: list[str],
    assumptions: list[str],
) -> list[Core]:
    """Stair cores where the spec puts them (both ends by default), clear of doors, stage and
    atrium, plus one beside each door that has a stair of its own (an exit on another level)."""
    W, D = spec.width_m, spec.depth_m
    foot = box(0, 0, W, D)
    links = [(k, k + 1) for k in range(-b.basements, b.storeys - 1)]
    if not links:
        return []
    spans = [(min(lv, 0), max(lv, 0)) for _, lv in via_stair]
    bare = [ln for ln in links if not any(a <= ln[0] and ln[1] <= z for a, z in spans)]
    wanted: list[tuple[str, float]] = [(c.place, c.width_m) for c in b.stairs]
    if not wanted and bare:
        ends = ("west", "east") if W >= D else ("south", "north")
        wanted = [(ends[0], 1.2), (ends[1], 1.2)]
        assumptions.append(f"Two 1.2 m stairs, near the {ends[0]} and {ends[1]} ends.")
    elif not wanted and via_stair:
        assumptions.append(
            "No stair cores were described, so the only stairs are the ones beside the exits "
            "on other levels; everyone above the street uses them. Add building.stairs for more."
        )
    cores: list[Core] = []

    def taken() -> list[Any]:
        return [g.buffer(1.0) for c in cores for g in (c.a, c.b)]

    for place, width in wanted:
        core = place_core(
            foot,
            _core_target(spec, place),
            width,
            unary_union([*keep_clear, *taken()]),
            corridor=b.interior == "rooms",
        )
        if core is None:
            problems.append(
                f"No room for a {width:g} m stair near the {place} of the building: make "
                "the building larger or put the stair elsewhere."
            )
            continue
        cores.append(core)
    doors = unary_union([geo.to_polygon(x.polygon) for x in exits])
    for door, level in via_stair:
        door_poly = geo.to_polygon(door.polygon)
        others = doors.difference(door_poly.buffer(0.1)).buffer(2.0)
        c = door_poly.centroid
        core = place_core(
            foot,
            (c.x, c.y),
            min(max(door.width_m, 0.8), 4.0),
            unary_union([*keep_clear[1:], others, door_poly.buffer(0.3), *taken()]),
        )
        if core is None:
            problems.append(f"No room for the stair to “{door.label}”: make the building larger.")
            continue
        # the street-level landing is the one beside the door
        span = (min(level, 0), max(level, 0))
        cores.append(Core(a=core.b, b=core.a, width_m=core.width_m, span=span))
    for lo, hi in links:
        if not any(c.joins(lo, hi) for c in cores):
            problems.append(
                f"No stair joins the {names.get(lo, floor_name(lo)).lower()} and the "
                f"{names.get(hi, floor_name(hi)).lower()}: add building.stairs."
            )
    return cores


def _building_features(
    spec: VenueSpec,
    b: BuildingSpec,
    per: list[int] | None,
    avoid: list[Any],
    level_obs: dict[int, list[Obstacle]],
    problems: list[str],
    notes: list[str],
    assumptions: list[str],
) -> None:
    """Features on their level (escalators and columns on all), added to `level_obs`.

    A feature without a level goes on street level, or on the busiest level when nobody is
    on street level (the bar of a basement club).
    """
    levels = level_order(b.storeys, b.basements)
    lowest, top = -b.basements, b.storeys - 1
    crowded = 0
    if per is not None and per[b.basements] == 0 and any(per):
        crowded = sorted(levels)[max(range(len(per)), key=per.__getitem__)]
    for f in spec.features:
        if f.level is not None and not lowest <= f.level <= top:
            problems.append(
                f"“{f.label or f.kind}” is on level {f.level}, but the building's levels run "
                f"from {lowest} to {top}: set its level."
            )
    every = [f for f in spec.features if f.level is None and f.kind in EVERY_LEVEL]
    if any(f.kind == "escalator" for f in every):
        assumptions.append("Escalators are drawn as obstacles; only the stairs count as ways out.")
    used_ids: set[str] = {o.id for obs in level_obs.values() for o in obs}
    plain = spec.model_copy(update={"stage": None})
    shared = _features(plain, every, avoid, used_ids, notes, assumptions, "_all")
    for k in levels:
        for o in shared:
            oid = o.id.replace("_all", "" if k == 0 else f"_{floor_id(k).lower()}")
            level_obs[k].append(o.model_copy(update={"id": oid}))
    for k in levels:
        mine = [
            f
            for f in spec.features
            if f not in every and (f.level if f.level is not None else crowded) == k
        ]
        if mine:
            here = [*avoid, *[geo.to_polygon(o.polygon).buffer(1.0) for o in level_obs[k]]]
            suffix = "" if k == 0 else f"_{floor_id(k).lower()}"
            level_obs[k] += _features(
                spec if k == 0 else plain, mine, here, used_ids, notes, assumptions, suffix
            )
