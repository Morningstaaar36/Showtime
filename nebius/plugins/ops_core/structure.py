"""Building structure ops: floors, stairs, walls, doors, rooms, routes and people profiles.

Every op validates against the current venue with a readable message (what is wrong and
how to fix it), returns a new venue without touching its input, and has an exact inverse.
Fields named `index` and `restore` exist only for undo and are hidden from the agents.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, ValidationError
from shapely.geometry import LineString, Point, Polygon

from api.core.extensions import geometry as geo
from api.models import Floor, Obstacle, PatchOpIn, Route, Stair, Venue, Zone
from api.models.venue import EventKind, PeopleGroup
from plugins.ops_core import building as bld
from plugins.ops_core.common import (
    _P,
    Pt,
    _annotation_state,
    _drop_annotations,
    _find,
    _floor_index,
    _id_taken,
    _insert,
    _op,
    _restore_annotations,
    _write_annotation_state,
)

Side = Literal["north", "south", "east", "west"]
ROOM_WALL_M = 0.2
MAX_START_DENSITY_PPM2 = 4.0  # same limit as the geometry validator


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _bbox(points: list[Pt]) -> str:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return f"x {_f(min(xs))}–{_f(max(xs))}, y {_f(min(ys))}–{_f(max(ys))}"


def _auto_id(venue: Venue, prefix: str, start: int = 1) -> str:
    taken = venue.all_ids()
    n = start
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


def _raw(name: str, **kw: Any) -> PatchOpIn:
    """Like `_op`, but keeps explicit nulls (they clear a field)."""
    return PatchOpIn.model_validate({"op": name, **kw})


def _free_share(floor: Floor, points: list[Pt]) -> float:
    """Share of a polygon that lies on open floor (inside the outline, not under obstacles)."""
    poly = geo.to_polygon(points)
    if poly.area <= 0:
        return 0.0
    return float(poly.intersection(geo.free_space(floor)).area / poly.area)


def _outline_share(floor: Floor, points: list[Pt]) -> float:
    poly = geo.to_polygon(points)
    if poly.area <= 0:
        return 0.0
    return float(poly.intersection(geo.to_polygon(floor.walkable)).area / poly.area)


def _wall_lines(floor: Floor, skip: str | None = None) -> list[list[Pt]]:
    out = []
    for o in floor.obstacles:
        if o.kind != "wall" or o.id == skip:
            continue
        try:
            out.append(bld.wall_line(o)[0])
        except ValueError:
            continue
    return out


def _groups_problem(zone: Zone, groups: list[PeopleGroup]) -> str | None:
    try:
        Zone.model_validate({**zone.model_dump(), "groups": [g.model_dump() for g in groups]})
    except ValidationError as exc:
        return exc.errors()[0]["msg"].removeprefix("Value error, ")
    return None


def _check_groups(groups: list[PeopleGroup] | None) -> str | None:
    if not groups:
        return None
    probe = Zone(id="probe", polygon=[(0, 0), (1, 0), (1, 1)], people=0)
    return _groups_problem(probe, groups)


# --- floors ------------------------------------------------------------------------


class AddFloorParams(_P):
    op: Literal["add_floor"] = "add_floor"
    floor_id: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=80)
    height_m: float = Field(default=3.5, ge=2.0, le=20)
    copy_walls: bool = True
    index: int | None = Field(default=None, ge=0)  # position in the list (used by undo)
    restore: dict[str, Any] | None = None  # used by undo: the removed floor and what went with it


def _new_floor_id(venue: Venue, p: AddFloorParams) -> str:
    if p.restore is not None:
        return str(p.restore["floor"]["floor_id"])
    if p.floor_id:
        return p.floor_id
    return _auto_id(venue, "F", start=len(venue.floors))


def _top_floor(venue: Venue) -> Floor:
    return max(venue.floors, key=lambda f: f.elevation_m)


def _copied_walls(venue: Venue, top: Floor, new_id: str) -> list[Obstacle]:
    taken = set(venue.all_ids()) | {new_id}
    out = []
    for o in top.obstacles:
        if o.kind != "wall":
            continue
        base = o.id.removeprefix(f"{top.floor_id}_")
        cand = f"{new_id}_{base}"
        n = 2
        while cand in taken:
            cand = f"{new_id}_{base}_{n}"
            n += 1
        taken.add(cand)
        out.append(o.model_copy(update={"id": cand}, deep=True))
    return out


class AddFloorOp:
    name = "add_floor"
    description = (
        "Add a storey above the highest floor: same outline as the floor below it, its "
        "interior walls copied when copy_walls is true, no exits or people yet. Connect it "
        "with add_stair."
    )
    example = '{"op": "add_floor", "name": "Second floor", "height_m": 3.5}'
    params_model = AddFloorParams

    def validate(self, venue: Venue, params: AddFloorParams) -> list[str]:
        new_id = _new_floor_id(venue, params)
        if _id_taken(venue, new_id):
            return [f"The id '{new_id}' is already used. Pick another floor_id or leave it out."]
        if params.restore is not None:
            try:
                Floor.model_validate(params.restore["floor"])
            except (KeyError, ValidationError) as exc:
                return [f"The floor to restore is not valid: {exc}"]
        return []

    def apply(self, venue: Venue, params: AddFloorParams) -> Venue:
        v = venue.model_copy(deep=True)
        if params.restore is not None:
            _restore_floor(v, params.restore, params.index)
            return v
        new_id = _new_floor_id(v, params)
        top = _top_floor(v)
        floor = Floor(
            floor_id=new_id,
            name=params.name or f"Floor {len(v.floors)}",
            elevation_m=round(top.elevation_m + params.height_m, 3),
            walkable=list(top.walkable),
            obstacles=_copied_walls(v, top, new_id) if params.copy_walls else [],
        )
        _insert(v.floors, params.index, floor)
        return v

    def invert(self, before: Venue, params: AddFloorParams) -> list[PatchOpIn]:
        return [_op("remove_floor", floor_id=_new_floor_id(before, params))]


def _floor_object_ids(floor: Floor) -> list[str]:
    return [
        floor.floor_id,
        *(o.id for o in floor.obstacles),
        *(e.id for e in floor.exits),
        *(z.id for z in floor.zones),
    ]


def _restore_floor(v: Venue, restore: dict[str, Any], index: int | None) -> None:
    _insert(v.floors, index, Floor.model_validate(restore["floor"]))
    for item in restore.get("stairs", []):
        _insert(v.stairs, item["index"], Stair.model_validate(item["stair"]))
    for item in restore.get("routes", []):
        _insert(v.routes, item["index"], Route.model_validate(item["route"]))
    zone_routes: dict[str, str] = restore.get("zone_routes", {})
    for f in v.floors:
        for z in f.zones:
            if z.id in zone_routes:
                z.route_id = zone_routes[z.id]
    for oid, state in restore.get("annotations", {}).items():
        _write_annotation_state(v, oid, state)


class RemoveFloorParams(_P):
    op: Literal["remove_floor"] = "remove_floor"
    floor_id: str


class RemoveFloorOp:
    name = "remove_floor"
    description = (
        "Remove a floor with everything on it, the stairs that reach it and the walking "
        "routes drawn on it. The last floor cannot be removed."
    )
    example = '{"op": "remove_floor", "floor_id": "F2"}'
    params_model = RemoveFloorParams

    def validate(self, venue: Venue, params: RemoveFloorParams) -> list[str]:
        if _floor_index(venue, params.floor_id) is None:
            known = ", ".join(f.floor_id for f in venue.floors)
            return [f"Unknown floor '{params.floor_id}'. Floors: {known}."]
        if len(venue.floors) == 1:
            return [f"'{params.floor_id}' is the only floor; a venue needs at least one."]
        return []

    def apply(self, venue: Venue, params: RemoveFloorParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        floor = v.floors.pop(fi)
        gone = _floor_object_ids(floor)
        stairs = [s for s in v.stairs if params.floor_id in (s.from_floor, s.to_floor)]
        routes = [r for r in v.routes if r.floor_id == params.floor_id]
        v.stairs = [s for s in v.stairs if s not in stairs]
        v.routes = [r for r in v.routes if r not in routes]
        route_ids = {r.id for r in routes}
        for f in v.floors:
            for z in f.zones:
                if z.route_id in route_ids:
                    z.route_id = None
        for oid in [*gone, *(s.id for s in stairs), *route_ids]:
            _drop_annotations(v, oid)
        return v

    def invert(self, before: Venue, params: RemoveFloorParams) -> list[PatchOpIn]:
        fi = _floor_index(before, params.floor_id)
        assert fi is not None
        floor = before.floors[fi]
        stairs: list[dict[str, Any]] = [
            {"index": i, "stair": s.model_dump(mode="json")}
            for i, s in enumerate(before.stairs)
            if params.floor_id in (s.from_floor, s.to_floor)
        ]
        routes: list[dict[str, Any]] = [
            {"index": i, "route": r.model_dump(mode="json")}
            for i, r in enumerate(before.routes)
            if r.floor_id == params.floor_id
        ]
        route_ids = {r["route"]["id"] for r in routes}
        zone_routes = {
            z.id: z.route_id
            for f in before.floors
            if f.floor_id != params.floor_id
            for z in f.zones
            if z.route_id in route_ids
        }
        ids = [*_floor_object_ids(floor), *(s["stair"]["id"] for s in stairs), *route_ids]
        annotations = {}
        for oid in ids:
            state = _annotation_state(before, oid)
            if any(value is not None for value in state.values()):
                annotations[oid] = state
        restore = {
            "floor": floor.model_dump(mode="json"),
            "stairs": stairs,
            "routes": routes,
            "zone_routes": zone_routes,
            "annotations": annotations,
        }
        return [_op("add_floor", index=fi, restore=restore)]


# --- stairs ------------------------------------------------------------------------


class AddStairParams(_P):
    op: Literal["add_stair"] = "add_stair"
    id: str | None = Field(default=None, min_length=1, max_length=60)
    from_floor: str
    to_floor: str
    x: float = Field(ge=-10_000, le=10_000)
    y: float = Field(ge=-10_000, le=10_000)
    width_m: float = Field(default=1.5, ge=0.8, le=10)
    run_m: float = Field(default=6.0, ge=2.0, le=40)
    direction: Side = "north"
    index: int | None = Field(default=None, ge=0)  # position in the list (used by undo)
    restore: dict[str, Any] | None = None  # used by undo: the removed stair as stored


def _stair_id(venue: Venue, p: AddStairParams) -> str:
    if p.restore is not None:
        return str(p.restore["id"])
    return p.id or _auto_id(venue, "stair_")


def _make_stair(venue: Venue, p: AddStairParams) -> Stair:
    if p.restore is not None:
        return Stair.model_validate(p.restore)
    upper, lower = venue.floor(p.from_floor), venue.floor(p.to_floor)
    _, top, bottom = bld.stair_shapes(p.x, p.y, p.width_m, p.run_m, p.direction)
    rise = upper.elevation_m - lower.elevation_m
    return Stair(
        id=_stair_id(venue, p),
        from_floor=p.from_floor,
        to_floor=p.to_floor,
        top_polygon=top,
        bottom_polygon=bottom,
        width_m=p.width_m,
        length_m=round(math.hypot(p.run_m, rise), 3),
    )


class AddStairOp:
    name = "add_stair"
    description = (
        "Add a straight stair from an upper floor (from_floor) down to a lower one "
        "(to_floor). x, y is the centre of the stairwell (width_m across, run_m long); "
        "direction is the way people face walking down: they step on at the far side on the "
        "upper floor and step off at the near side of the lower floor."
    )
    example = (
        '{"op": "add_stair", "from_floor": "F2", "to_floor": "F1", "x": 37, "y": 20, '
        '"width_m": 1.5, "run_m": 6, "direction": "south"}'
    )
    params_model = AddStairParams

    def validate(self, venue: Venue, params: AddStairParams) -> list[str]:
        sid = _stair_id(venue, params)
        if _id_taken(venue, sid):
            return [f"The id '{sid}' is already used. Pick another id or leave it out."]
        if params.restore is not None:
            return []
        known = ", ".join(f.floor_id for f in venue.floors)
        for fid in (params.from_floor, params.to_floor):
            if _floor_index(venue, fid) is None:
                return [f"Unknown floor '{fid}'. Floors: {known}."]
        if params.from_floor == params.to_floor:
            return ["A stair must join two different floors: from_floor is the upper one."]
        upper, lower = venue.floor(params.from_floor), venue.floor(params.to_floor)
        if upper.elevation_m <= lower.elevation_m:
            return [
                f"from_floor must be the upper floor: {upper.floor_id} is at "
                f"{_f(upper.elevation_m)} m and {lower.floor_id} at {_f(lower.elevation_m)} m. "
                "Swap from_floor and to_floor."
            ]
        foot, top, bottom = bld.stair_shapes(
            params.x, params.y, params.width_m, params.run_m, params.direction
        )
        problems = []
        for floor in (upper, lower):
            if _outline_share(floor, foot) < 0.95:
                xs = [p[0] for p in floor.walkable]
                ys = [p[1] for p in floor.walkable]
                problems.append(
                    f"The stairwell ({_bbox(foot)}) sticks out of floor {floor.floor_id} "
                    f"(outline x {_f(min(xs))}–{_f(max(xs))}, y {_f(min(ys))}–{_f(max(ys))}). "
                    "Move x, y inwards or turn the stair with direction."
                )
        if problems:
            return problems
        for floor, landing, which in ((upper, top, "top"), (lower, bottom, "bottom")):
            share = _free_share(floor, landing)
            if share < 0.9:
                problems.append(
                    f"The {which} landing ({_bbox(landing)}) on {floor.floor_id} is "
                    f"{(1 - share) * 100:.0f}% covered by walls or other objects. Move the "
                    "stair or the objects so people can step on and off."
                )
        return problems

    def apply(self, venue: Venue, params: AddStairParams) -> Venue:
        v = venue.model_copy(deep=True)
        _insert(v.stairs, params.index, _make_stair(v, params))
        return v

    def invert(self, before: Venue, params: AddStairParams) -> list[PatchOpIn]:
        return [_op("remove_stair", stair_id=_stair_id(before, params))]


class RemoveStairParams(_P):
    op: Literal["remove_stair"] = "remove_stair"
    stair_id: str


class RemoveStairOp:
    name = "remove_stair"
    description = "Remove a stair."
    example = '{"op": "remove_stair", "stair_id": "stair_1"}'
    params_model = RemoveStairParams

    def validate(self, venue: Venue, params: RemoveStairParams) -> list[str]:
        if not any(s.id == params.stair_id for s in venue.stairs):
            known = ", ".join(s.id for s in venue.stairs) or "none"
            return [f"Unknown stair '{params.stair_id}'. Stairs: {known}."]
        return []

    def apply(self, venue: Venue, params: RemoveStairParams) -> Venue:
        v = venue.model_copy(deep=True)
        v.stairs = [s for s in v.stairs if s.id != params.stair_id]
        _drop_annotations(v, params.stair_id)
        return v

    def invert(self, before: Venue, params: RemoveStairParams) -> list[PatchOpIn]:
        i, s = next((i, s) for i, s in enumerate(before.stairs) if s.id == params.stair_id)
        return [
            _op("add_stair", from_floor=s.from_floor, to_floor=s.to_floor, x=0, y=0,
                index=i, restore=s.model_dump(mode="json")),
            *_restore_annotations(before, s.id),
        ]  # fmt: skip


class WidenStairParams(_P):
    op: Literal["widen_stair"] = "widen_stair"
    stair_id: str
    width_m: float = Field(ge=0.8, le=6.0)
    # every flight of the same stairwell (stacked within 4 m), so the whole way down is wider
    whole_stairwell: bool = True
    restore: dict[str, float] | None = None  # used by undo: stair id -> previous width


class WidenStairOp:
    name = "widen_stair"
    description = (
        "Change a stair's width in metres (how many people per second it carries); by "
        "default every flight of the same stairwell changes, so the whole way down is wider."
    )
    example = '{"op": "widen_stair", "stair_id": "stair_a_1", "width_m": 2.0}'
    params_model = WidenStairParams

    def validate(self, venue: Venue, params: WidenStairParams) -> list[str]:
        if params.restore is None and not any(s.id == params.stair_id for s in venue.stairs):
            known = ", ".join(s.id for s in venue.stairs) or "none"
            return [f"Unknown stair '{params.stair_id}'. Stairs: {known}."]
        return []

    def _targets(self, venue: Venue, params: WidenStairParams) -> dict[str, float]:
        if params.restore is not None:
            return dict(params.restore)
        ids = geo.stairwell(venue, params.stair_id) if params.whole_stairwell else [params.stair_id]
        return {sid: params.width_m for sid in ids}

    def apply(self, venue: Venue, params: WidenStairParams) -> Venue:
        v = venue.model_copy(deep=True)
        widths = self._targets(v, params)
        for s in v.stairs:
            if s.id in widths:
                s.width_m = widths[s.id]
        return v

    def invert(self, before: Venue, params: WidenStairParams) -> list[PatchOpIn]:
        ids = self._targets(before, params)
        old = {s.id: s.width_m for s in before.stairs if s.id in ids}
        return [_op("widen_stair", stair_id=params.stair_id, width_m=1.0, restore=old)]


# --- walls and doors ---------------------------------------------------------------


class AddWallParams(_P):
    op: Literal["add_wall"] = "add_wall"
    floor_id: str
    id: str | None = Field(default=None, min_length=1, max_length=60)
    points: list[Pt] = Field(min_length=2, max_length=50)
    thickness_m: float = Field(default=0.2, ge=0.05, le=2)
    height_m: float | None = Field(default=None, gt=0, le=50)


def _wall_id(venue: Venue, p: AddWallParams) -> str:
    return p.id or _auto_id(venue, "wall_")


def _snapped(venue: Venue, p: AddWallParams) -> list[Pt]:
    floor = venue.floor(p.floor_id)
    return bld.snap_wall(p.points, floor.walkable, _wall_lines(floor), p.thickness_m)


class AddWallOp:
    name = "add_wall"
    description = (
        "Add an interior wall along a polyline of points (people cannot cross it). Ends "
        "within 0.3 m of the outline or of another wall are joined to it. Cut doors into it "
        "with add_door."
    )
    example = (
        '{"op": "add_wall", "floor_id": "F0", "points": [[20, 0], [20, 25]], "thickness_m": 0.2}'
    )
    params_model = AddWallParams

    def validate(self, venue: Venue, params: AddWallParams) -> list[str]:
        fi = _floor_index(venue, params.floor_id)
        if fi is None:
            known = ", ".join(f.floor_id for f in venue.floors)
            return [f"Unknown floor '{params.floor_id}'. Floors: {known}."]
        wid = _wall_id(venue, params)
        if _id_taken(venue, wid):
            return [f"The id '{wid}' is already used. Pick another id or leave it out."]
        why = bld.check_wall_line([bld.rnd(p) for p in params.points])
        if why:
            return [f"Wall '{wid}' cannot be drawn: {why}."]
        floor = venue.floors[fi]
        line = LineString(_snapped(venue, params))
        inside = line.intersection(geo.to_polygon(floor.walkable)).length / line.length
        if inside < 0.5:
            return [
                f"Wall '{wid}' lies mostly outside floor {floor.floor_id} "
                f"({_bbox(floor.walkable)}). Give points inside the outline."
            ]
        return []

    def apply(self, venue: Venue, params: AddWallParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        line = _snapped(v, params)
        v.floors[fi].obstacles.append(
            Obstacle(
                id=_wall_id(v, params),
                kind="wall",
                polygon=bld.wall_polygon(line, params.thickness_m),
                height_m=params.height_m,
                line=line,
            )
        )
        return v

    def invert(self, before: Venue, params: AddWallParams) -> list[PatchOpIn]:
        return [_op("remove_obstacle", obstacle_id=_wall_id(before, params))]


class AddDoorParams(_P):
    op: Literal["add_door"] = "add_door"
    floor_id: str
    wall_id: str
    x: float
    y: float
    width_m: float = Field(default=1.0, ge=0.6, le=10)


def _door_pieces(venue: Venue, p: AddDoorParams) -> tuple[Obstacle, list[Obstacle]]:
    """(original wall, wall pieces after the cut); raises ValueError with the reason."""
    floor = venue.floor(p.floor_id)
    wall = next(o for o in floor.obstacles if o.id == p.wall_id)
    line, thickness = bld.wall_line(wall)
    pieces = bld.cut_door(line, p.x, p.y, p.width_m)
    if not pieces:
        raise ValueError(
            f"a {_f(p.width_m)} m door would take out the whole wall; remove the wall instead"
        )
    taken = set(venue.all_ids())
    ids = [wall.id]
    if len(pieces) > 1:
        suffix = "b"
        while f"{wall.id}_{suffix}" in taken:
            suffix = chr(ord(suffix) + 1) if suffix < "z" else suffix + "z"
        ids.append(f"{wall.id}_{suffix}")
    out = [
        Obstacle(
            id=oid,
            kind="wall",
            polygon=bld.wall_polygon(piece, thickness),
            height_m=wall.height_m,
            label=wall.label,
            line=piece,
        )
        for oid, piece in zip(ids, pieces, strict=True)
    ]
    return wall, out


class AddDoorOp:
    name = "add_door"
    description = (
        "Cut a door (a gap people can walk through) into an interior wall, centred on the "
        "point of the wall nearest to x, y. The wall becomes up to two pieces: wall_id and "
        "wall_id_b. Doors to the outside are exits: use add_exit for those."
    )
    example = (
        '{"op": "add_door", "floor_id": "F0", "wall_id": "wall_1", "x": 20, "y": 12, '
        '"width_m": 1.2}'
    )
    params_model = AddDoorParams

    def validate(self, venue: Venue, params: AddDoorParams) -> list[str]:
        fi = _floor_index(venue, params.floor_id)
        if fi is None:
            known = ", ".join(f.floor_id for f in venue.floors)
            return [f"Unknown floor '{params.floor_id}'. Floors: {known}."]
        floor = venue.floors[fi]
        wall = next((o for o in floor.obstacles if o.id == params.wall_id), None)
        if wall is None:
            walls = [o.id for o in floor.obstacles if o.kind == "wall"]
            listed = ", ".join(walls[:12]) or "none"
            return [f"Floor {floor.floor_id} has no wall '{params.wall_id}'. Walls: {listed}."]
        if wall.kind != "wall":
            return [
                f"'{wall.id}' is a {wall.kind}, not a wall. Doors can only be cut into walls; "
                "move or resize the object instead."
            ]
        try:
            line, _ = bld.wall_line(wall)
        except ValueError as exc:
            return [f"No door can be cut: {exc}."]
        d = LineString(line).distance(Point(params.x, params.y))
        if d > 3.0:
            return [
                f"The point ({_f(params.x)}, {_f(params.y)}) is {_f(d)} m from wall "
                f"'{wall.id}' ({_bbox(wall.polygon)}). Give a point on the wall."
            ]
        try:
            _door_pieces(venue, params)
        except ValueError as exc:
            return [f"No door in '{wall.id}': {exc}."]
        return []

    def apply(self, venue: Venue, params: AddDoorParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        wall, pieces = _door_pieces(v, params)
        obstacles = v.floors[fi].obstacles
        at = next(i for i, o in enumerate(obstacles) if o.id == wall.id)
        obstacles[at : at + 1] = pieces
        return v

    def invert(self, before: Venue, params: AddDoorParams) -> list[PatchOpIn]:
        fi = _floor_index(before, params.floor_id)
        assert fi is not None
        wall, pieces = _door_pieces(before, params)
        at = next(i for i, o in enumerate(before.floors[fi].obstacles) if o.id == wall.id)
        return [
            *(_op("remove_obstacle", obstacle_id=p.id) for p in pieces),
            _op(
                "add_obstacle",
                floor_id=params.floor_id,
                id=wall.id,
                kind=wall.kind,
                polygon=wall.polygon,
                height_m=wall.height_m,
                label=wall.label,
                line=wall.line,
                index=at,
            ),
            *_restore_annotations(before, wall.id),
        ]


# --- rooms -------------------------------------------------------------------------


class AddRoomParams(_P):
    op: Literal["add_room"] = "add_room"
    floor_id: str
    id: str | None = Field(default=None, min_length=1, max_length=60)
    x: float
    y: float
    width_m: float = Field(ge=1.5, le=500)
    depth_m: float = Field(ge=1.5, le=500)
    door_wall: Side = "south"
    door_width_m: float = Field(default=1.0, ge=0.6, le=10)
    people: int | None = Field(default=None, ge=0, le=100_000)
    label: str | None = Field(default=None, max_length=80)
    groups: list[PeopleGroup] | None = None


def _room_id(venue: Venue, p: AddRoomParams) -> str:
    return p.id or _auto_id(venue, "room_")


def _room_rect(venue: Venue, p: AddRoomParams) -> tuple[float, float, float, float]:
    return bld.snap_rect(p.x, p.y, p.width_m, p.depth_m, venue.floor(p.floor_id).walkable)


def _room_zone_polygon(x0: float, y0: float, x1: float, y1: float) -> list[Pt]:
    inset = ROOM_WALL_M / 2 + 0.1
    return geo.rect(x0 + inset, y0 + inset, x1 - inset, y1 - inset)


class AddRoomOp:
    name = "add_room"
    description = (
        "Add a closed rectangular room: x, y is its south-west corner, width_m runs east and "
        "depth_m north. Its walls have one door (door_width_m wide, in the middle of "
        "door_wall). Give people to also add a starting zone inside it (id = the room id)."
    )
    example = (
        '{"op": "add_room", "floor_id": "F0", "id": "office_1", "x": 2, "y": 2, '
        '"width_m": 6, "depth_m": 4, "door_wall": "north", "people": 12, "label": "Office"}'
    )
    params_model = AddRoomParams

    def validate(self, venue: Venue, params: AddRoomParams) -> list[str]:
        fi = _floor_index(venue, params.floor_id)
        if fi is None:
            known = ", ".join(f.floor_id for f in venue.floors)
            return [f"Unknown floor '{params.floor_id}'. Floors: {known}."]
        floor = venue.floors[fi]
        rid = _room_id(venue, params)
        for oid in (f"{rid}_walls", *([rid] if params.people is not None else [])):
            if _id_taken(venue, oid):
                return [f"The id '{oid}' is already used. Pick another room id."]
        x0, y0, x1, y1 = _room_rect(venue, params)
        rect = geo.rect(x0, y0, x1, y1)
        outside = Polygon(rect).difference(geo.to_polygon(floor.walkable)).area
        if outside > 0.01 * Polygon(rect).area:
            return [
                f"Room '{rid}' ({_bbox(rect)}) sticks out of floor {floor.floor_id} "
                f"(outline {_bbox(floor.walkable)}) by {outside:.1f} m². Move it with x, y or "
                "make it smaller."
            ]
        side = x1 - x0 if params.door_wall in ("north", "south") else y1 - y0
        if params.door_width_m > side - 2 * ROOM_WALL_M:
            return [
                f"The {params.door_wall} side of room '{rid}' is {_f(side)} m long, too short "
                f"for a {_f(params.door_width_m)} m door. Use a narrower door or a longer side."
            ]
        if bld.side_on_outline(x0, y0, x1, y1, params.door_wall, floor.walkable):
            return [
                f"The {params.door_wall} side of room '{rid}' is the floor's outer wall, so its "
                "door would lead outside. Put the door on a side facing the inside "
                "(door_wall), or add an exit there with add_exit."
            ]
        problem = _check_groups(params.groups)
        if problem:
            return [f"Room '{rid}' people groups: {problem}."]
        if params.people:
            area = Polygon(_room_zone_polygon(x0, y0, x1, y1)).area
            if params.people / max(area, 1e-9) > MAX_START_DENSITY_PPM2:
                return [
                    f"{params.people} people do not fit in room '{rid}' ({area:.0f} m² inside): "
                    f"at most {int(area * MAX_START_DENSITY_PPM2)} can stand there. Make the "
                    "room bigger or lower the headcount."
                ]
        return []

    def apply(self, venue: Venue, params: AddRoomParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        rid = _room_id(v, params)
        x0, y0, x1, y1 = _room_rect(v, params)
        ring = bld.room_ring(x0, y0, x1, y1, params.door_wall, params.door_width_m)
        floor = v.floors[fi]
        floor.obstacles.append(
            Obstacle(
                id=f"{rid}_walls",
                kind="wall",
                polygon=bld.wall_polygon(ring, ROOM_WALL_M),
                label=f"{params.label} walls" if params.label else None,
                line=ring,
            )
        )
        if params.people is not None:
            floor.zones.append(
                Zone(
                    id=rid,
                    polygon=_room_zone_polygon(x0, y0, x1, y1),
                    people=params.people,
                    label=params.label,
                    groups=list(params.groups or []),
                )
            )
        return v

    def invert(self, before: Venue, params: AddRoomParams) -> list[PatchOpIn]:
        rid = _room_id(before, params)
        ops = [_op("remove_obstacle", obstacle_id=f"{rid}_walls")]
        if params.people is not None:
            ops.append(_op("remove_zone", zone_id=rid))
        return ops


# --- people profiles, routes and the event kind ---------------------------------------


class SetZoneProfileParams(_P):
    op: Literal["set_zone_profile"] = "set_zone_profile"
    zone_id: str
    groups: list[PeopleGroup] | None = None
    pre_movement_s: float | None = Field(default=None, ge=0, le=1800)
    route_id: str | None = None


PROFILE_FIELDS = ("groups", "pre_movement_s", "route_id")


def _zone(venue: Venue, zone_id: str) -> tuple[Floor, Zone] | None:
    loc = _find(venue, zone_id)
    if loc is None or loc[1] != "zone":
        return None
    floor = venue.floors[loc[0]]
    return floor, floor.zones[loc[2]]


class SetZoneProfileOp:
    name = "set_zone_profile"
    description = (
        "Describe who starts in a zone: groups (shares of elderly, child, wheelchair, bed or "
        "staff people; the rest are general adults), pre_movement_s (seconds before they start "
        "moving) and route_id (a walking route they follow first). Give only the fields that "
        "change; null clears one."
    )
    example = (
        '{"op": "set_zone_profile", "zone_id": "ward_a", "groups": [{"kind": "bed", "share": '
        '0.3}, {"kind": "staff", "share": 0.1}], "pre_movement_s": 120}'
    )
    params_model = SetZoneProfileParams

    def validate(self, venue: Venue, params: SetZoneProfileParams) -> list[str]:
        found = _zone(venue, params.zone_id)
        if found is None:
            return [f"Unknown zone '{params.zone_id}'."]
        floor, zone = found
        given = params.model_fields_set & set(PROFILE_FIELDS)
        if not given:
            return ["Nothing to change: give groups, pre_movement_s or route_id."]
        if params.groups:
            problem = _groups_problem(zone, params.groups)
            if problem:
                return [f"Zone '{zone.id}' people groups: {problem}."]
        if params.route_id is not None:
            route = next((r for r in venue.routes if r.id == params.route_id), None)
            if route is None:
                known = ", ".join(r.id for r in venue.routes) or "none"
                return [f"Unknown route '{params.route_id}'. Routes: {known}."]
            if route.floor_id != floor.floor_id:
                return [
                    f"Route '{route.id}' is on {route.floor_id} but zone '{zone.id}' is on "
                    f"{floor.floor_id}. Draw a route on {floor.floor_id}."
                ]
        return []

    def apply(self, venue: Venue, params: SetZoneProfileParams) -> Venue:
        v = venue.model_copy(deep=True)
        found = _zone(v, params.zone_id)
        assert found is not None
        _, zone = found
        given = params.model_fields_set
        if "groups" in given:
            zone.groups = list(params.groups or [])
        if "pre_movement_s" in given:
            zone.pre_movement_s = params.pre_movement_s
        if "route_id" in given:
            zone.route_id = params.route_id
        return v

    def invert(self, before: Venue, params: SetZoneProfileParams) -> list[PatchOpIn]:
        found = _zone(before, params.zone_id)
        assert found is not None
        _, zone = found
        back: dict[str, Any] = {}
        given = params.model_fields_set
        if "groups" in given:
            back["groups"] = [g.model_dump() for g in zone.groups]
        if "pre_movement_s" in given:
            back["pre_movement_s"] = zone.pre_movement_s
        if "route_id" in given:
            back["route_id"] = zone.route_id
        return [_raw("set_zone_profile", zone_id=zone.id, **back)]


class AddRouteParams(_P):
    op: Literal["add_route"] = "add_route"
    id: str | None = Field(default=None, min_length=1, max_length=60)
    floor_id: str
    points: list[Pt] = Field(min_length=2, max_length=200)
    width_m: float | None = Field(default=None, gt=0, le=100)
    label: str | None = Field(default=None, max_length=80)
    index: int | None = Field(default=None, ge=0)  # position in the list (used by undo)


def _route_id(venue: Venue, p: AddRouteParams) -> str:
    return p.id or _auto_id(venue, "route_")


class AddRouteOp:
    name = "add_route"
    description = (
        "Draw a walking route on a floor (a march, procession or queue line), points in "
        "walking order. Zones follow it when set_zone_profile gives them its route_id."
    )
    example = (
        '{"op": "add_route", "floor_id": "F0", "id": "march", "points": [[5, 40], [60, 40], '
        '[60, 5]], "width_m": 8, "label": "March route"}'
    )
    params_model = AddRouteParams

    def validate(self, venue: Venue, params: AddRouteParams) -> list[str]:
        fi = _floor_index(venue, params.floor_id)
        if fi is None:
            known = ", ".join(f.floor_id for f in venue.floors)
            return [f"Unknown floor '{params.floor_id}'. Floors: {known}."]
        rid = _route_id(venue, params)
        if _id_taken(venue, rid):
            return [f"The id '{rid}' is already used. Pick another id or leave it out."]
        outline = geo.to_polygon(venue.floors[fi].walkable)
        for i, (x, y) in enumerate(params.points, start=1):
            if outline.distance(Point(x, y)) > 1.0:
                return [
                    f"Point {i} ({_f(x)}, {_f(y)}) of route '{rid}' is outside floor "
                    f"{params.floor_id} ({_bbox(venue.floors[fi].walkable)}). Keep the route "
                    "on the floor."
                ]
        if LineString(params.points).length < 1.0:
            return [f"Route '{rid}' is shorter than 1 m; give points further apart."]
        return []

    def apply(self, venue: Venue, params: AddRouteParams) -> Venue:
        v = venue.model_copy(deep=True)
        route = Route(
            id=_route_id(v, params),
            floor_id=params.floor_id,
            points=params.points,
            width_m=params.width_m,
            label=params.label,
        )
        _insert(v.routes, params.index, route)
        return v

    def invert(self, before: Venue, params: AddRouteParams) -> list[PatchOpIn]:
        return [_op("remove_route", route_id=_route_id(before, params))]


class RemoveRouteParams(_P):
    op: Literal["remove_route"] = "remove_route"
    route_id: str


class RemoveRouteOp:
    name = "remove_route"
    description = "Remove a walking route; zones that followed it go straight to the exits."
    example = '{"op": "remove_route", "route_id": "march"}'
    params_model = RemoveRouteParams

    def validate(self, venue: Venue, params: RemoveRouteParams) -> list[str]:
        if not any(r.id == params.route_id for r in venue.routes):
            known = ", ".join(r.id for r in venue.routes) or "none"
            return [f"Unknown route '{params.route_id}'. Routes: {known}."]
        return []

    def apply(self, venue: Venue, params: RemoveRouteParams) -> Venue:
        v = venue.model_copy(deep=True)
        v.routes = [r for r in v.routes if r.id != params.route_id]
        for f in v.floors:
            for z in f.zones:
                if z.route_id == params.route_id:
                    z.route_id = None
        _drop_annotations(v, params.route_id)
        return v

    def invert(self, before: Venue, params: RemoveRouteParams) -> list[PatchOpIn]:
        i, r = next((i, r) for i, r in enumerate(before.routes) if r.id == params.route_id)
        ops = [
            _op(
                "add_route",
                id=r.id,
                floor_id=r.floor_id,
                points=r.points,
                width_m=r.width_m,
                label=r.label,
                index=i,
            )
        ]
        for f in before.floors:
            for z in f.zones:
                if z.route_id == r.id:
                    ops.append(_raw("set_zone_profile", zone_id=z.id, route_id=r.id))
        return ops + _restore_annotations(before, r.id)


class SetEventKindParams(_P):
    op: Literal["set_event_kind"] = "set_event_kind"
    event_kind: EventKind | None


class SetEventKindOp:
    name = "set_event_kind"
    description = (
        "Say what kind of event or building this is (concert, hospital, school, march ...); "
        "it sets how people behave by default. null means not said."
    )
    example = '{"op": "set_event_kind", "event_kind": "hospital"}'
    params_model = SetEventKindParams

    def validate(self, venue: Venue, params: SetEventKindParams) -> list[str]:
        return []

    def apply(self, venue: Venue, params: SetEventKindParams) -> Venue:
        v = venue.model_copy(deep=True)
        v.event_kind = params.event_kind
        return v

    def invert(self, before: Venue, params: SetEventKindParams) -> list[PatchOpIn]:
        return [_raw("set_event_kind", event_kind=before.event_kind)]


STRUCTURE_OPS = [
    AddFloorOp(),
    RemoveFloorOp(),
    AddStairOp(),
    RemoveStairOp(),
    WidenStairOp(),
    AddWallOp(),
    AddDoorOp(),
    AddRoomOp(),
    SetZoneProfileOp(),
    AddRouteOp(),
    RemoveRouteOp(),
    SetEventKindOp(),
]
