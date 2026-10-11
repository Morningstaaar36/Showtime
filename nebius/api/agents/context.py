"""Compact, deterministic text views of a venue and dynamic schemas for agent outputs.

Prompts must stay short for the 9B local model and identical across runs so recorded
responses replay (the record/replay cache key includes the messages).
"""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Annotated, Any, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.models import Venue, VenuePatch

# Fields that exist for undo or geometry plumbing, not for agents.
INTERNAL_FIELDS: dict[str, set[str]] = {
    "*": {"index"},
    "add_exit": {"polygon"},
    "add_obstacle": {"line"},
    "set_event": {"restore"},
}


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _bbox(points: list[tuple[float, float]]) -> str:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return f"x {_fmt(min(xs))}–{_fmt(max(xs))}, y {_fmt(min(ys))}–{_fmt(max(ys))}"


def wall_of(venue: Venue, floor_id: str, points: list[tuple[float, float]]) -> tuple[str, float]:
    """(wall name, position along that wall) of an exit, from the floor outline bounds."""
    f = venue.floor(floor_id)
    xs = [p[0] for p in f.walkable]
    ys = [p[1] for p in f.walkable]
    cx, cy = geo.centroid(points)
    d = {"south": cy - min(ys), "north": max(ys) - cy, "west": cx - min(xs), "east": max(xs) - cx}
    wall = min(d, key=lambda k: d[k])
    return wall, (cx if wall in ("north", "south") else cy)


def venue_summary(venue: Venue) -> str:
    """Short text description of a venue with every id an agent may use."""
    lines = [f"Venue: {venue.name} ({venue.mode}). {venue.total_people():,} people."]
    for f in venue.floors:
        xs = [p[0] for p in f.walkable]
        ys = [p[1] for p in f.walkable]
        lines.append(
            f"Floor {f.floor_id} ({f.name or f.floor_id}, elevation "
            f"{_fmt(f.elevation_m)} m): outline x {_fmt(min(xs))}–{_fmt(max(xs))}, "
            f"y {_fmt(min(ys))}–{_fmt(max(ys))}. North/south walls: center is x in "
            f"{_fmt(min(xs))}–{_fmt(max(xs))}; east/west walls: center is y in "
            f"{_fmt(min(ys))}–{_fmt(max(ys))}."
        )
        for e in f.exits:
            wall, pos = wall_of(venue, f.floor_id, e.polygon)
            along = "x" if wall in ("north", "south") else "y"
            label = f" ({e.label})" if e.label else ""
            lines.append(
                f"  exit {e.id}{label}: {_fmt(e.width_m)} m wide on the {wall} wall at "
                f"{along} = {_fmt(pos)}{' (BLOCKED)' if e.blocked else ''}"
            )
        for o in f.obstacles:
            if o.kind == "wall":
                continue
            label = f", {o.label}" if o.label else ""
            lines.append(f"  object {o.id} ({o.kind}{label}): {_bbox(o.polygon)}")
        walls = [o.id for o in f.obstacles if o.kind == "wall"]
        if walls:
            lines.append(f"  interior walls: {len(walls)} segments")
        for z in f.zones:
            label = f" ({z.label})" if z.label else ""
            lines.append(f"  zone {z.id}{label}: {z.people} people, {_bbox(z.polygon)}")
    for s in venue.stairs:
        lines.append(
            f"Stair {s.id}: from {s.from_floor} down to {s.to_floor}, "
            f"{_fmt(s.width_m)} m wide, {_fmt(s.length_m)} m long."
        )
    if venue.stage is not None:
        st = venue.stage
        lines.append(
            f"Stage structure: {_fmt(st.width_m)} × {_fmt(st.depth_m)} m, roof "
            f"{_fmt(st.roof_height_m)} m high, {st.legs} legs, ballast "
            f"{_fmt(st.ballast_kg_per_leg)} kg per leg."
        )
    return "\n".join(lines)


def ids_line(venue: Venue) -> str:
    """Valid ids grouped by kind."""
    ex = [e.id for f in venue.floors for e in f.exits]
    zo = [z.id for f in venue.floors for z in f.zones]
    ob = [o.id for f in venue.floors for o in f.obstacles if o.kind != "wall"]
    fl = [f.floor_id for f in venue.floors]
    return (
        f"exit ids: {', '.join(ex)}; zone ids: {', '.join(zo)}; object ids: "
        f"{', '.join(ob) or 'none'}; floor ids: {', '.join(fl)}"
    )


def _fields_doc(model: type[BaseModel], skip: set[str]) -> str:
    parts = []
    for name, f in model.model_fields.items():
        if name in skip or name in ("op", "type"):
            continue
        ann = getattr(f.annotation, "__name__", None) or str(f.annotation).replace("typing.", "")
        ann = ann.replace("Literal", "").replace("NoneType", "null")
        opt = "" if f.is_required() else "?"
        parts.append(f"{name}{opt}")
    return ", ".join(parts)


OP_EXAMPLES: dict[str, str] = {
    "move": '{"op": "move", "target": "<object, exit or zone id>", "dx": 0, "dy": -5}',
    "resize": '{"op": "resize", "target": "<id>", "width_m": 3}',
    "add_exit": '{"op": "add_exit", "floor_id": "F0", "id": "door_e1", "wall": "east", '
    '"center": 12, "width_m": 2}',
    "remove_exit": '{"op": "remove_exit", "exit_id": "<exit id>"}',
    "block_exit": '{"op": "block_exit", "exit_id": "<exit id>", "blocked": true}',
    "add_obstacle": '{"op": "add_obstacle", "floor_id": "F0", "id": "booth_1", "kind": "booth", '
    '"polygon": [[10, 10], [13, 10], [13, 12], [10, 12]]}',
    "remove_obstacle": '{"op": "remove_obstacle", "obstacle_id": "<object id>"}',
    "add_barrier_line": '{"op": "add_barrier_line", "floor_id": "F0", "id": "barrier_1", '
    '"points": [[10, 5], [10, 15]]}',
    "set_people": '{"op": "set_people", "zone_id": "<zone id>", "people": 250}',
    "add_zone": '{"op": "add_zone", "floor_id": "F0", "id": "zone_vip", "polygon": [[2, 2], '
    '[8, 2], [8, 6], [2, 6]], "people": 100}',
    "remove_zone": '{"op": "remove_zone", "zone_id": "<zone id>"}',
    "set_stage_param": '{"op": "set_stage_param", "param": "ballast_kg_per_leg", "value": 3000}',
}
OP_HINTS: dict[str, str] = {
    "move": "shift an object, exit or zone; dx > 0 is east, dy > 0 is north",
    "resize": "change a size; for an exit only width_m",
    "block_exit": "close an exit (blocked true) or reopen it (blocked false)",
    "set_people": "change the number of people in a zone",
    "set_stage_param": "change the stage structure: width_m, depth_m, roof_height_m, "
    "roof_area_m2, legs, ballast_kg_per_leg, friction_coeff, force_coeff, "
    "banner_area_m2",
    "remove_obstacle": "delete a booth, bar, barrier or other object",
}


def agent_ops(registry: Registry, allowed: set[str] | None = None) -> list[Any]:
    """Edit operations an agent may use; organizer-only ops (locks, provenance) never."""
    return [
        op
        for op in registry.all("PatchOp")
        if not getattr(op, "user_only", False) and (allowed is None or op.name in allowed)
    ]


def ops_doc(registry: Registry, allowed: set[str] | None = None) -> str:
    """One line per edit operation with a JSON example."""
    out = []
    for op in agent_ops(registry, allowed):
        example = getattr(op, "example", None) or OP_EXAMPLES.get(op.name)
        hint = OP_HINTS.get(op.name, op.description)
        if example is None:
            skip = INTERNAL_FIELDS["*"] | INTERNAL_FIELDS.get(op.name, set())
            example = f"{op.name}({_fields_doc(op.params_model, skip)})"
        out.append(f"- {op.name}: {hint}. {example}")
    return "\n".join(out)


def events_doc(registry: Registry, allowed: set[str]) -> str:
    """One line per scenario event type."""
    out = []
    for ev in registry.all("ScenarioEvent"):
        if ev.type not in allowed:
            continue
        out.append(f"- {ev.type}({_fields_doc(ev.params_model, set())}): {ev.description}")
    return "\n".join(out)


def _agent_model(src: type[BaseModel], name: str, skip: set[str]) -> type[BaseModel]:
    """Agent-facing copy of a params model.

    The tag field (`op` or `type`) comes first and is required: with grammar-constrained
    decoding a small model must commit to the operation before writing its fields, so the
    grammar then only allows that operation's fields.
    """
    fields: dict[str, Any] = {}
    tag = "op" if "op" in src.model_fields else "type" if "type" in src.model_fields else None
    if tag is not None:
        f = src.model_fields[tag]
        fields[tag] = (f.annotation, Field(...))
    for fname, f in src.model_fields.items():
        if fname in skip or fname == tag:
            continue
        fields[fname] = (f.annotation, copy.deepcopy(f))
    return create_model(name, __config__=ConfigDict(extra="forbid"), **fields)


@lru_cache(maxsize=32)
def _op_union(op_models: tuple[tuple[str, type[BaseModel]], ...]) -> Any:
    models = []
    for name, params in op_models:
        skip = INTERNAL_FIELDS["*"] | INTERNAL_FIELDS.get(name, set())
        models.append(_agent_model(params, f"Op_{name}", skip))
    if len(models) == 1:
        return models[0]
    return Annotated[Union[tuple(models)], Field(discriminator="op")]  # noqa: UP007


def op_union(registry: Registry, allowed: set[str] | None = None) -> Any:
    """Discriminated union of agent-facing edit operations."""
    items = tuple((op.name, op.params_model) for op in agent_ops(registry, allowed))
    return _op_union(items)


@lru_cache(maxsize=32)
def _event_union(ev_models: tuple[tuple[str, type[BaseModel]], ...]) -> Any:
    models = [_agent_model(params, f"Ev_{name}", set()) for name, params in ev_models]
    if len(models) == 1:
        return models[0]
    return Annotated[Union[tuple(models)], Field(discriminator="type")]  # noqa: UP007


def event_union(registry: Registry, allowed: set[str]) -> Any:
    """Discriminated union of scenario events an agent may use."""
    items = tuple(
        (ev.type, ev.params_model) for ev in registry.all("ScenarioEvent") if ev.type in allowed
    )
    return _event_union(items)


def _dir(dx: float, dy: float) -> str:
    parts = []
    if abs(dy) > 1e-9:
        parts.append(f"{_fmt(abs(dy))} m {'north' if dy > 0 else 'south'}")
    if abs(dx) > 1e-9:
        parts.append(f"{_fmt(abs(dx))} m {'east' if dx > 0 else 'west'}")
    return " and ".join(parts) or "0 m"


def explain_patch(venue: Venue, patch: VenuePatch) -> str:
    """Plain-language description of a patch, generated from the ops (not by the LLM)."""
    out: list[str] = []
    for op in patch.ops:
        d = op.model_dump()
        k = op.op
        if k == "move":
            out.append(f"Moved {d['target']} {_dir(d.get('dx', 0), d.get('dy', 0))}")
        elif k == "resize":
            dims = []
            if d.get("width_m"):
                dims.append(f"{_fmt(d['width_m'])} m wide")
            if d.get("depth_m"):
                dims.append(f"{_fmt(d['depth_m'])} m deep")
            out.append(f"Resized {d['target']} to {' and '.join(dims)}")
        elif k == "add_exit":
            where = (
                f" on the {d['wall']} wall at {_fmt(d['center'])} m"
                if d.get("wall") and d.get("center") is not None
                else ""
            )
            out.append(f"Added a {_fmt(d['width_m'])} m exit {d['id']}{where}")
        elif k == "remove_exit":
            out.append(f"Removed exit {d['exit_id']}")
        elif k == "block_exit":
            out.append(f"{'Blocked' if d.get('blocked', True) else 'Opened'} exit {d['exit_id']}")
        elif k == "add_obstacle":
            out.append(f"Added {d.get('kind', 'object')} {d['id']}")
        elif k == "remove_obstacle":
            out.append(f"Removed {d['obstacle_id']}")
        elif k == "add_barrier_line":
            out.append(f"Added a {d.get('kind', 'barrier')} line {d['id']}")
        elif k == "set_people":
            out.append(f"Set zone {d['zone_id']} to {d['people']:,} people")
        elif k == "add_zone":
            out.append(f"Added zone {d['id']} with {d['people']:,} people")
        elif k == "remove_zone":
            out.append(f"Removed zone {d['zone_id']}")
        elif k == "set_stage_param":
            out.append(f"Set stage {d['param'].replace('_', ' ')} to {_fmt(d['value'])}")
        else:
            out.append(f"Applied {k}")
    return "; ".join(out) + "." if out else "No change."
