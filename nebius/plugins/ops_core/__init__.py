"""Built-in venue edit operations (PatchOp extension point)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.models import Exit, Obstacle, PatchOpIn, Venue, Zone
from api.models.plan import ObjectConstraint
from api.models.scene import InputProvenance
from plugins.ops_core.common import (
    _P,
    PLAN_KEY,
    Pt,
    _annotation_state,
    _drop_annotations,
    _find,
    _floor_index,
    _id_taken,
    _insert,
    _items,
    _op,
    _restore_annotations,
    _write_annotation_state,
)
from plugins.ops_core.stairwell import STAIRWELL_OPS
from plugins.ops_core.structure import STRUCTURE_OPS


class Config(BaseModel):
    """No settings yet."""


# --- move --------------------------------------------------------------------


class MoveParams(_P):
    op: Literal["move"] = "move"
    target: str
    dx: float = Field(default=0.0, ge=-500, le=500)
    dy: float = Field(default=0.0, ge=-500, le=500)


class MoveOp:
    name = "move"
    description = "Move an obstacle (stage, barrier...), exit or zone by dx, dy metres."
    params_model = MoveParams

    def validate(self, venue: Venue, params: MoveParams) -> list[str]:
        return [] if _find(venue, params.target) else [f"Unknown object '{params.target}'."]

    def apply(self, venue: Venue, params: MoveParams) -> Venue:
        v = venue.model_copy(deep=True)
        loc = _find(v, params.target)
        assert loc is not None
        fi, kind, ii = loc
        item = _items(v, fi, kind)[ii]
        item.polygon = geo.translate(item.polygon, params.dx, params.dy)
        if isinstance(item, Obstacle) and item.line:
            item.line = geo.translate(item.line, params.dx, params.dy)
        return v

    def invert(self, before: Venue, params: MoveParams) -> list[PatchOpIn]:
        return [_op("move", target=params.target, dx=-params.dx, dy=-params.dy)]


# --- resize ------------------------------------------------------------------


class ResizeParams(_P):
    op: Literal["resize"] = "resize"
    target: str
    width_m: float | None = Field(default=None, gt=0, le=500)
    depth_m: float | None = Field(default=None, gt=0, le=500)


def _bbox(poly: list[Pt]) -> tuple[float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return max(xs) - min(xs), max(ys) - min(ys)


class ResizeOp:
    name = "resize"
    description = (
        "Resize an object about its centre. For exits, width_m is the door width; "
        "for others width_m is the x size and depth_m the y size."
    )
    params_model = ResizeParams

    def validate(self, venue: Venue, params: ResizeParams) -> list[str]:
        if not _find(venue, params.target):
            return [f"Unknown object '{params.target}'."]
        if params.width_m is None and params.depth_m is None:
            return ["Give width_m or depth_m."]
        return []

    def apply(self, venue: Venue, params: ResizeParams) -> Venue:
        v = venue.model_copy(deep=True)
        loc = _find(v, params.target)
        assert loc is not None
        fi, kind, ii = loc
        item = _items(v, fi, kind)[ii]
        if isinstance(item, Exit) and params.width_m:
            w, h = _bbox(item.polygon)
            if w >= h:
                item.polygon = geo.resize(item.polygon, params.width_m, None)
            else:
                item.polygon = geo.resize(item.polygon, None, params.width_m)
            item.width_m = params.width_m
        else:
            item.polygon = geo.resize(item.polygon, params.width_m, params.depth_m)
        return v

    def invert(self, before: Venue, params: ResizeParams) -> list[PatchOpIn]:
        loc = _find(before, params.target)
        assert loc is not None
        fi, kind, ii = loc
        item = _items(before, fi, kind)[ii]
        if isinstance(item, Exit):
            return [_op("resize", target=params.target, width_m=item.width_m)]
        w, h = _bbox(item.polygon)
        return [
            _op(
                "resize",
                target=params.target,
                width_m=w if params.width_m else None,
                depth_m=h if params.depth_m else None,
            )
        ]


# --- exits -------------------------------------------------------------------


class AddExitParams(_P):
    op: Literal["add_exit"] = "add_exit"
    floor_id: str
    id: str
    wall: Literal["north", "south", "east", "west"] | None = None
    center: float | None = None
    width_m: float = Field(gt=0.5, le=30)
    polygon: list[Pt] | None = None
    label: str | None = None
    index: int | None = Field(default=None, ge=0)  # position in the list (used by undo)


def _exit_name(venue: Venue, wall: str | None) -> str | None:
    """Readable default name for a new exit ("East door", "East gate 2")."""
    if wall is None:
        return None
    base = f"{wall.capitalize()} {'gate' if venue.mode == 'outdoor' else 'door'}"
    taken = {e.label for f in venue.floors for e in f.exits}
    n = 1
    while (name := base if n == 1 else f"{base} {n}") in taken:
        n += 1
    return name


class AddExitOp:
    name = "add_exit"
    description = (
        "Add an exit on a wall: wall is north/south/east/west, center is the position "
        "along that wall in metres (x for north/south, y for east/west); omit center for "
        "the middle of that side."
    )
    params_model = AddExitParams

    def _polygon(self, venue: Venue, p: AddExitParams) -> list[Pt]:
        if p.polygon:
            return p.polygon
        if p.wall is None:
            raise ValueError("add_exit needs a wall (north/south/east/west) or a polygon")
        fi = _floor_index(venue, p.floor_id)
        assert fi is not None
        floor = venue.floors[fi]
        first = geo.exit_on_wall(floor.walkable, p.wall, p.center, p.width_m)
        others = [geo.to_polygon(e.polygon).buffer(0.5) for e in floor.exits if e.id != p.id]
        # a door must open into one space: never across an interior wall (a door straddling
        # the wall between a room and the corridor leaves the room's people pinned to it)
        others += [geo.to_polygon(o.polygon).buffer(0.05) for o in floor.obstacles]
        if not any(geo.to_polygon(first).intersects(o) for o in others):
            return first
        # an exit or a wall is already there: take the nearest free spot on the same wall
        minx, miny, maxx, maxy = geo.to_polygon(floor.walkable).bounds
        lo, hi = (miny, maxy) if p.wall in ("east", "west") else (minx, maxx)
        want = p.center if p.center is not None else (lo + hi) / 2
        half = p.width_m / 2
        steps = int((hi - lo) / 0.5) + 1
        for c in sorted((lo + half + k * 0.5 for k in range(steps)), key=lambda c: abs(c - want)):
            if c > hi - half:
                continue
            try:
                cand = geo.exit_on_wall(floor.walkable, p.wall, c, p.width_m)
            except ValueError:
                continue
            if not any(geo.to_polygon(cand).intersects(o) for o in others):
                return cand
        raise ValueError(
            f"the {p.wall} wall has no free {p.width_m:g} m stretch left between exits and walls"
        )

    def validate(self, venue: Venue, params: AddExitParams) -> list[str]:
        if _floor_index(venue, params.floor_id) is None:
            return [f"Unknown floor '{params.floor_id}'."]
        if _id_taken(venue, params.id):
            return [f"The id '{params.id}' is already used."]
        try:
            self._polygon(venue, params)
        except ValueError as exc:
            return [f"Exit '{params.id}' could not be placed: {exc}."]
        return []

    def apply(self, venue: Venue, params: AddExitParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        _insert(
            v.floors[fi].exits,
            params.index,
            Exit(
                id=params.id,
                polygon=self._polygon(v, params),
                width_m=params.width_m,
                label=params.label or _exit_name(v, params.wall),
            ),
        )
        return v

    def invert(self, before: Venue, params: AddExitParams) -> list[PatchOpIn]:
        return [_op("remove_exit", exit_id=params.id)]


class RemoveExitParams(_P):
    op: Literal["remove_exit"] = "remove_exit"
    exit_id: str


class RemoveExitOp:
    name = "remove_exit"
    description = "Remove an exit permanently."
    params_model = RemoveExitParams

    def validate(self, venue: Venue, params: RemoveExitParams) -> list[str]:
        loc = _find(venue, params.exit_id)
        return [] if loc and loc[1] == "exit" else [f"Unknown exit '{params.exit_id}'."]

    def apply(self, venue: Venue, params: RemoveExitParams) -> Venue:
        v = venue.model_copy(deep=True)
        for f in v.floors:
            f.exits = [e for e in f.exits if e.id != params.exit_id]
        _drop_annotations(v, params.exit_id)
        return v

    def invert(self, before: Venue, params: RemoveExitParams) -> list[PatchOpIn]:
        loc = _find(before, params.exit_id)
        assert loc is not None
        fi, _, ii = loc
        e = before.floors[fi].exits[ii]
        ops = [
            _op(
                "add_exit",
                floor_id=before.floors[fi].floor_id,
                id=e.id,
                width_m=e.width_m,
                polygon=e.polygon,
                label=e.label,
                index=ii,
            )
        ]
        if e.blocked:
            ops.append(_op("block_exit", exit_id=e.id, blocked=True))
        return ops + _restore_annotations(before, e.id)


class BlockExitParams(_P):
    op: Literal["block_exit"] = "block_exit"
    exit_id: str
    blocked: bool = True


class BlockExitOp:
    name = "block_exit"
    description = "Mark an exit as blocked (blocked=true) or open it again (blocked=false)."
    params_model = BlockExitParams

    def validate(self, venue: Venue, params: BlockExitParams) -> list[str]:
        loc = _find(venue, params.exit_id)
        return [] if loc and loc[1] == "exit" else [f"Unknown exit '{params.exit_id}'."]

    def apply(self, venue: Venue, params: BlockExitParams) -> Venue:
        v = venue.model_copy(deep=True)
        for f in v.floors:
            for e in f.exits:
                if e.id == params.exit_id:
                    e.blocked = params.blocked
        return v

    def invert(self, before: Venue, params: BlockExitParams) -> list[PatchOpIn]:
        loc = _find(before, params.exit_id)
        assert loc is not None
        fi, _, ii = loc
        return [
            _op("block_exit", exit_id=params.exit_id, blocked=before.floors[fi].exits[ii].blocked)
        ]


# --- obstacles and barriers ----------------------------------------------------


class AddObstacleParams(_P):
    op: Literal["add_obstacle"] = "add_obstacle"
    floor_id: str
    id: str
    kind: Literal[
        "stage", "wall", "barrier", "fence", "booth", "seating", "column", "bar", "other"
    ] = "other"
    polygon: list[Pt] = Field(min_length=3)
    height_m: float | None = None
    label: str | None = None
    line: list[Pt] | None = None
    index: int | None = Field(default=None, ge=0)  # position in the list (used by undo)


class AddObstacleOp:
    name = "add_obstacle"
    description = "Add a non-walkable object (booth, bar, wall segment...) given as a polygon."
    params_model = AddObstacleParams

    def validate(self, venue: Venue, params: AddObstacleParams) -> list[str]:
        if _floor_index(venue, params.floor_id) is None:
            return [f"Unknown floor '{params.floor_id}'."]
        if _id_taken(venue, params.id):
            return [f"The id '{params.id}' is already used."]
        return []

    def apply(self, venue: Venue, params: AddObstacleParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        _insert(
            v.floors[fi].obstacles,
            params.index,
            Obstacle(
                id=params.id,
                kind=params.kind,
                polygon=params.polygon,
                height_m=params.height_m,
                label=params.label,
                line=params.line,
            ),
        )
        return v

    def invert(self, before: Venue, params: AddObstacleParams) -> list[PatchOpIn]:
        return [_op("remove_obstacle", obstacle_id=params.id)]


class RemoveObstacleParams(_P):
    op: Literal["remove_obstacle"] = "remove_obstacle"
    obstacle_id: str


class RemoveObstacleOp:
    name = "remove_obstacle"
    description = "Remove an obstacle, barrier or fence (the stage cannot be removed)."
    params_model = RemoveObstacleParams

    def validate(self, venue: Venue, params: RemoveObstacleParams) -> list[str]:
        loc = _find(venue, params.obstacle_id)
        if not loc or loc[1] != "obstacle":
            return [f"Unknown obstacle '{params.obstacle_id}'."]
        if venue.floors[loc[0]].obstacles[loc[2]].kind == "stage":
            return ["The stage cannot be removed; move or resize it instead."]
        return []

    def apply(self, venue: Venue, params: RemoveObstacleParams) -> Venue:
        v = venue.model_copy(deep=True)
        for f in v.floors:
            f.obstacles = [o for o in f.obstacles if o.id != params.obstacle_id]
        _drop_annotations(v, params.obstacle_id)
        return v

    def invert(self, before: Venue, params: RemoveObstacleParams) -> list[PatchOpIn]:
        loc = _find(before, params.obstacle_id)
        assert loc is not None
        fi, _, ii = loc
        o = before.floors[fi].obstacles[ii]
        return [
            _op(
                "add_obstacle",
                floor_id=before.floors[fi].floor_id,
                id=o.id,
                kind=o.kind,
                polygon=o.polygon,
                height_m=o.height_m,
                label=o.label,
                line=o.line,
                index=ii,
            ),
            *_restore_annotations(before, o.id),
        ]


class AddBarrierLineParams(_P):
    op: Literal["add_barrier_line"] = "add_barrier_line"
    floor_id: str
    id: str
    points: list[Pt] = Field(min_length=2, max_length=20)
    thickness_m: float = Field(default=0.3, gt=0.05, le=2)
    kind: Literal["barrier", "fence"] = "barrier"


class AddBarrierLineOp:
    name = "add_barrier_line"
    description = "Add a crowd barrier or fence along a polyline of points."
    params_model = AddBarrierLineParams

    def validate(self, venue: Venue, params: AddBarrierLineParams) -> list[str]:
        if _floor_index(venue, params.floor_id) is None:
            return [f"Unknown floor '{params.floor_id}'."]
        if _id_taken(venue, params.id):
            return [f"The id '{params.id}' is already used."]
        return []

    def apply(self, venue: Venue, params: AddBarrierLineParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        v.floors[fi].obstacles.append(
            Obstacle(
                id=params.id,
                kind=params.kind,
                polygon=geo.barrier_polygon(params.points, params.thickness_m),
                height_m=1.1,
                line=params.points,
            )
        )
        return v

    def invert(self, before: Venue, params: AddBarrierLineParams) -> list[PatchOpIn]:
        return [_op("remove_obstacle", obstacle_id=params.id)]


# --- zones and people ------------------------------------------------------------


class SetPeopleParams(_P):
    op: Literal["set_people"] = "set_people"
    zone_id: str
    people: int = Field(ge=0, le=100_000)


class SetPeopleOp:
    name = "set_people"
    description = "Set the headcount of a zone."
    params_model = SetPeopleParams

    def validate(self, venue: Venue, params: SetPeopleParams) -> list[str]:
        loc = _find(venue, params.zone_id)
        return [] if loc and loc[1] == "zone" else [f"Unknown zone '{params.zone_id}'."]

    def apply(self, venue: Venue, params: SetPeopleParams) -> Venue:
        v = venue.model_copy(deep=True)
        for f in v.floors:
            for z in f.zones:
                if z.id == params.zone_id:
                    z.people = params.people
        return v

    def invert(self, before: Venue, params: SetPeopleParams) -> list[PatchOpIn]:
        loc = _find(before, params.zone_id)
        assert loc is not None
        return [
            _op(
                "set_people",
                zone_id=params.zone_id,
                people=before.floors[loc[0]].zones[loc[2]].people,
            )
        ]


class AddZoneParams(_P):
    op: Literal["add_zone"] = "add_zone"
    floor_id: str
    id: str
    polygon: list[Pt] = Field(min_length=3)
    people: int = Field(ge=0, le=100_000)
    label: str | None = None
    index: int | None = Field(default=None, ge=0)  # position in the list (used by undo)
    # used by undo: the whole removed zone, so its people mix, start delay and route come back
    restore: dict[str, Any] | None = None


class AddZoneOp:
    name = "add_zone"
    description = "Add a starting zone with a headcount."
    params_model = AddZoneParams

    def validate(self, venue: Venue, params: AddZoneParams) -> list[str]:
        if _floor_index(venue, params.floor_id) is None:
            return [f"Unknown floor '{params.floor_id}'."]
        if _id_taken(venue, params.id):
            return [f"The id '{params.id}' is already used."]
        return []

    def apply(self, venue: Venue, params: AddZoneParams) -> Venue:
        v = venue.model_copy(deep=True)
        fi = _floor_index(v, params.floor_id)
        assert fi is not None
        zone = (
            Zone.model_validate(params.restore)
            if params.restore is not None
            else Zone(
                id=params.id, polygon=params.polygon, people=params.people, label=params.label
            )
        )
        _insert(v.floors[fi].zones, params.index, zone)
        return v

    def invert(self, before: Venue, params: AddZoneParams) -> list[PatchOpIn]:
        return [_op("remove_zone", zone_id=params.id)]


class RemoveZoneParams(_P):
    op: Literal["remove_zone"] = "remove_zone"
    zone_id: str


class RemoveZoneOp:
    name = "remove_zone"
    description = "Remove a starting zone."
    params_model = RemoveZoneParams

    def validate(self, venue: Venue, params: RemoveZoneParams) -> list[str]:
        loc = _find(venue, params.zone_id)
        return [] if loc and loc[1] == "zone" else [f"Unknown zone '{params.zone_id}'."]

    def apply(self, venue: Venue, params: RemoveZoneParams) -> Venue:
        v = venue.model_copy(deep=True)
        for f in v.floors:
            f.zones = [z for z in f.zones if z.id != params.zone_id]
        _drop_annotations(v, params.zone_id)
        return v

    def invert(self, before: Venue, params: RemoveZoneParams) -> list[PatchOpIn]:
        loc = _find(before, params.zone_id)
        assert loc is not None
        fi, _, ii = loc
        z = before.floors[fi].zones[ii]
        return [
            _op(
                "add_zone",
                floor_id=before.floors[fi].floor_id,
                id=z.id,
                polygon=z.polygon,
                people=z.people,
                label=z.label,
                index=ii,
                restore=z.model_dump(mode="json"),
            ),
            *_restore_annotations(before, z.id),
        ]


# --- stage parameters ---------------------------------------------------------------

StageParam = Literal[
    "width_m",
    "depth_m",
    "roof_height_m",
    "roof_area_m2",
    "legs",
    "ballast_kg_per_leg",
    "friction_coeff",
    "force_coeff",
    "banner_area_m2",
]


class SetStageParamParams(_P):
    op: Literal["set_stage_param"] = "set_stage_param"
    param: StageParam
    value: float = Field(ge=0)


class SetStageParamOp:
    name = "set_stage_param"
    description = "Change a stage structure parameter (e.g. ballast_kg_per_leg) for the wind check."
    params_model = SetStageParamParams

    def validate(self, venue: Venue, params: SetStageParamParams) -> list[str]:
        if venue.stage is None:
            return ["This venue has no stage structure (indoor venues have none)."]
        try:
            data = venue.stage.model_dump()
            data[params.param] = int(params.value) if params.param == "legs" else params.value
            type(venue.stage).model_validate(data)
        except ValueError as exc:
            return [f"Invalid stage value: {exc}"]
        return []

    def apply(self, venue: Venue, params: SetStageParamParams) -> Venue:
        v = venue.model_copy(deep=True)
        assert v.stage is not None
        data = v.stage.model_dump()
        data[params.param] = int(params.value) if params.param == "legs" else params.value
        v.stage = type(v.stage).model_validate(data)
        return v

    def invert(self, before: Venue, params: SetStageParamParams) -> list[PatchOpIn]:
        assert before.stage is not None
        return [
            _op(
                "set_stage_param",
                param=params.param,
                value=float(getattr(before.stage, params.param)),
            )
        ]


# --- event details ---------------------------------------------------------------


class SetEventParams(_P):
    op: Literal["set_event"] = "set_event"
    duration_h: float | None = Field(default=None, gt=0, le=72)
    alcohol: bool | None = None
    audience: Literal["standing", "seated", "mixed"] | None = None
    kind: str | None = Field(default=None, max_length=60)
    start: str | None = Field(default=None, max_length=25, description="local ISO time")
    restore: dict[str, Any] | None = None  # used by undo: the whole previous event record
    clear_start: bool = False  # used by undo: the venue had no start time before


class SetEventOp:
    name = "set_event"
    description = (
        "Set event details used for estimates: duration_h (hours open), alcohol (served or "
        "not), audience (standing, seated or mixed), kind (concert, conference ...), start "
        "(local ISO date and time). Give only the fields that change."
    )
    params_model = SetEventParams

    def validate(self, venue: Venue, params: SetEventParams) -> list[str]:
        if params.start is not None and venue.location is None:
            return ["The venue has no location, so a start time cannot be set."]
        return []

    def apply(self, venue: Venue, params: SetEventParams) -> Venue:
        v = venue.model_copy(deep=True)
        event = dict(
            params.restore if params.restore is not None else v.extensions.get("event") or {}
        )
        for key in ("duration_h", "alcohol", "audience", "kind"):
            val = getattr(params, key)
            if val is not None:
                event[key] = val
        rest = {k: val for k, val in v.extensions.items() if k != "event"}
        v.extensions = {**rest, "event": event} if event else rest
        if v.location is not None and (params.start is not None or params.clear_start):
            start = None if params.clear_start else params.start
            v.location = v.location.model_copy(update={"event_start": start})
        return v

    def invert(self, before: Venue, params: SetEventParams) -> list[PatchOpIn]:
        back: dict[str, Any] = {"restore": dict(before.extensions.get("event") or {})}
        if params.start is not None and before.location is not None:
            if before.location.event_start is None:
                back["clear_start"] = True
            else:
                back["start"] = before.location.event_start
        return [_op("set_event", **back)]


# --- annotations ----------------------------------------------------------------------

ChangeStatus = Literal["existing", "proposed"]


class SetAnnotationParams(_P):
    op: Literal["set_annotation"] = "set_annotation"
    target: str
    provenance: InputProvenance | None = None
    locked: bool | None = None
    change: ChangeStatus | None = None
    restore: dict[str, Any] | None = None  # used by undo: the object's previous entries


class SetAnnotationOp:
    name = "set_annotation"
    description = (
        "Record where an object's facts come from (provenance), lock it against changes, or "
        "mark an exit or obstacle as existing or proposed construction. Organizer-only."
    )
    params_model = SetAnnotationParams
    # agents never see this op: a lock must not be removable by the AI it restrains
    user_only = True

    def validate(self, venue: Venue, params: SetAnnotationParams) -> list[str]:
        kind = venue.all_ids().get(params.target)
        if kind is None:
            return [f"Unknown object '{params.target}'."]
        if params.restore is not None:
            return []
        if params.provenance is None and params.locked is None and params.change is None:
            return ["Nothing to record: give a provenance, a lock state or a change status."]
        if params.change is not None and kind not in ("exit", "obstacle"):
            return ["Only exits and obstacles can be marked existing or proposed."]
        return []

    def apply(self, venue: Venue, params: SetAnnotationParams) -> Venue:
        v = venue.model_copy(deep=True)
        if params.restore is not None:
            _write_annotation_state(v, params.target, params.restore)
            return v
        state = _annotation_state(v, params.target)
        if params.provenance is not None:
            state["provenance"] = params.provenance.model_dump(mode="json", exclude_none=True)
        entry = dict(state["annotation"] or {})
        if params.locked is not None:
            entry["locked"] = params.locked
        if params.change is not None:
            entry["change"] = params.change
        state["annotation"] = entry or None
        if PLAN_KEY in v.extensions and (params.locked is not None or params.change is not None):
            policy = ObjectConstraint.model_validate(state.get("policy") or {})
            if params.locked is not None:
                policy.locked = params.locked
            if params.change is not None:
                policy.origin = params.change
            state["policy"] = policy.model_dump(mode="json")
        _write_annotation_state(v, params.target, state)
        return v

    def invert(self, before: Venue, params: SetAnnotationParams) -> list[PatchOpIn]:
        return [
            _op(
                "set_annotation",
                target=params.target,
                restore=_annotation_state(before, params.target),
            )
        ]


ALL_OPS: list[Any] = [
    MoveOp(),
    ResizeOp(),
    AddExitOp(),
    RemoveExitOp(),
    BlockExitOp(),
    AddObstacleOp(),
    RemoveObstacleOp(),
    AddBarrierLineOp(),
    SetPeopleOp(),
    AddZoneOp(),
    RemoveZoneOp(),
    SetStageParamOp(),
    SetEventOp(),
    SetAnnotationOp(),
    *STRUCTURE_OPS,
    *STAIRWELL_OPS,
]


def showtime_register(registry: Registry, config: Config) -> None:
    """Register every built-in patch op."""
    for op in ALL_OPS:
        registry.add("PatchOp", op.name, op)
