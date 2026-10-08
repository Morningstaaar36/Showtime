"""Solver: VenueSpec (walls, regions, sizes) → Venue (exact, valid geometry).

Placement is deterministic. Objects that cannot be placed without blocking an exit or
overlapping something are left out and reported, so the designer agent can adjust the spec.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from api.core.extensions import geometry as geo
from api.models import Exit, Floor, Obstacle, StageParams, Stair, Venue, Zone
from api.models.venue import ObstacleKind
from api.models.venue_spec import ExitSpec, FeatureSpec, UpperFloorSpec, VenueSpec, Wall

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1

MARGIN_M = 1.5  # zones and features keep this far from the outer walls (less in small rooms)
STAGE_GAP_M = 2.0  # clear strip in front of the stage
EXIT_CLEAR_M = 3.0  # features keep this far from exits
UPPER_ELEVATION_M = 4.5
STAIR_LENGTH_M = 9.0  # 4.5 m rise at a comfortable slope

_REGIONS: dict[str, tuple[float, float, float, float]] = {  # u0, u1, v0, v1 (v = towards stage)
    "whole": (0, 1, 0, 1),
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
    "other": ("other", 2.0),
}


@dataclass
class BuildResult:
    """The venue plus what the solver had to change or leave out."""

    venue: Venue
    notes: list[str] = field(default_factory=list)


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


def _inner(spec: VenueSpec) -> Rect:
    """Area left for people and features: inside the margin and clear of the stage."""
    m = min(MARGIN_M, 0.08 * min(spec.width_m, spec.depth_m))
    x0, y0, x1, y1 = m, m, spec.width_m - m, spec.depth_m - m
    if spec.stage is not None:
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
    spec: VenueSpec, walkable: list[tuple[float, float]], blocked: Polygon | None, notes: list[str]
) -> list[Exit]:
    exits: list[Exit] = []
    per_wall: dict[str, list[ExitSpec]] = defaultdict(list)
    for e in spec.exits:
        per_wall[e.wall].append(e)
    outdoor = spec.mode == "outdoor"
    for wall, items in per_wall.items():
        span = _wall_span(spec, wall)  # type: ignore[arg-type]
        taken: list[tuple[float, float]] = []
        for i, e in enumerate(sorted(items, key=lambda x: x.position), start=1):
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
                        f"Moved the {wall} exit {i} by {abs(c - want):.0f} m to keep it clear."
                    )
                taken.append((c - half, c + half))
                break
            if chosen is None:
                notes.append(f"No room for exit {i} on the {wall} wall; left it out.")
                continue
            label = e.label or _exit_name(wall, i, len(items), outdoor)  # type: ignore[arg-type]
            prefix = "gate" if outdoor else "door"
            exits.append(
                Exit(
                    id=f"{prefix}_{wall[0]}{i}",
                    polygon=chosen,
                    width_m=round(width, 2),
                    label=label,
                )
            )
    return exits


def _place_feature(
    spec: VenueSpec, f: FeatureSpec, slot: tuple[int, int], inner: Rect, avoid: Polygon
) -> Rect | None:
    """First position (from the preferred one outward) that overlaps nothing in `avoid`."""
    stage_wall: Wall = spec.stage.wall if spec.stage else "north"
    along, depth = f.width_m, f.depth_m
    if f.place in ("north", "south", "east", "west"):
        wall: Wall = f.place
        span = _wall_span(spec, wall)
        along = min(along, span - 2)
        n, k = slot
        prefer = span * (k + 1) / (n + 1)
        cands = [prefer + s * dd for dd in range(0, int(span), 1) for s in (1, -1)]
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


def build_venue(spec: VenueSpec, venue_id: str = "draft") -> BuildResult:
    """Solve a spec into a venue. Never raises for layout problems; reports them in notes."""
    notes: list[str] = []
    W, D = spec.width_m, spec.depth_m
    walkable = geo.rect(0, 0, W, D)
    obstacles: list[Obstacle] = []
    stage_params: StageParams | None = None
    if spec.stage is not None:
        sr = _stage_rect(spec)
        obstacles.append(
            Obstacle(
                id="stage",
                kind="stage",
                polygon=geo.rect(*sr),
                label="Stage",
                height_m=spec.stage.roof_height_m if spec.mode == "outdoor" else 1.0,
            )
        )
        if spec.mode == "outdoor":
            sw, sd = sr[2] - sr[0], sr[3] - sr[1]
            stage_params = StageParams(
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
        if spec.front_barrier:
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
    stage_poly = geo.to_polygon(obstacles[0].polygon) if spec.stage is not None else None

    upper = stair = None
    if spec.upper_floor is not None:
        if spec.mode == "outdoor":
            notes.append("Open-air sites have one level; the upper floor was left out.")
        elif D < STAIR_LENGTH_M + 12:
            notes.append(f"The venue is too shallow ({D:.0f} m) for a balcony with a stair.")
        else:
            upper, stair, structure = _upper_floor(spec, spec.upper_floor, notes)
            obstacles.append(structure)

    exits = _place_exits(spec, walkable, stage_poly, notes)
    if not exits:
        notes.append("No exit could be placed. Add at least one exit on a free wall.")

    inner = _inner(spec)
    exit_clear = [geo.to_polygon(e.polygon).buffer(EXIT_CLEAR_M) for e in exits]
    placed: list[Polygon] = [geo.to_polygon(o.polygon).buffer(1.0) for o in obstacles]
    if stair is not None:
        placed.append(geo.to_polygon(stair.bottom_polygon).buffer(1.5))
    per_wall: dict[str, int] = defaultdict(int)
    for f in spec.features:
        if f.place in ("north", "south", "east", "west"):
            per_wall[f.place] += 1
    seen: dict[str, int] = defaultdict(int)
    used_ids: set[str] = {o.id for o in obstacles}
    for f in spec.features:
        k = seen[f.place]
        seen[f.place] += 1
        r = _place_feature(
            spec, f, (per_wall.get(f.place, 1), k), inner, unary_union([*placed, *exit_clear])
        )
        name = f.label or f.kind.replace("_", " ").capitalize()
        if r is None:
            notes.append(f"Left out “{name}”: no free spot that keeps exits and walkways clear.")
            continue
        kind, height = _KIND[f.kind]
        base = f.kind if f.kind != "other" else "feature"
        n, oid = 1, f"{base}_1"
        while oid in used_ids:
            n += 1
            oid = f"{base}_{n}"
        used_ids.add(oid)
        poly = geo.rect(*r)
        obstacles.append(Obstacle(id=oid, kind=kind, polygon=poly, height_m=height, label=name))
        placed.append(geo.to_polygon(poly).buffer(1.0))

    # zones: each region once, split across zones sharing it, never overlapping each other
    stage_wall: Wall = spec.stage.wall if spec.stage else "north"
    blockers = unary_union([geo.to_polygon(o.polygon).buffer(0.3) for o in obstacles])
    if stair is not None:
        blockers = blockers.union(geo.to_polygon(stair.bottom_polygon).buffer(1.0))
    used: Polygon = Polygon()
    zones: list[Zone] = []
    by_region: dict[str, list[int]] = defaultdict(list)
    upper_words = ("balcony", "mezzanine", "gallery", "upper", "first floor", "level 1")
    for i, z in enumerate(spec.zones):
        if upper is not None and any(w in z.label.lower() for w in upper_words):
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
            rect = box(*_frame(stage_wall, inner, a, b, v0, v1)).buffer(-0.3)
            area = rect.difference(blockers).difference(used)
            z = spec.zones[i]
            if area.is_empty or area.area < 4:
                notes.append(f"No room left for “{z.label}”; overlapping zones were merged away.")
                continue
            part = geo.largest_part(area).simplify(0.05)
            used = used.union(part)
            zid = "zone_" + str(len(zones) + 1)
            zones.append(Zone(id=zid, polygon=geo.to_points(part), people=z.people, label=z.label))

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
        extensions={"generated": {"from": "description", "assumptions": list(spec.assumptions)}},
    )
    return BuildResult(venue=venue, notes=notes)
