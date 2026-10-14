"""Sim-side handlers for scenario events, dispatched by `type`.

Each handler gets the per-floor run context (see engine_jupedsim.FloorRun) and the
event dict. Handlers may return a callable `step(ctx) -> bool` that runs every frame
until it returns True (used for spawns that need free space).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from script_api import ScriptRunner
from shapely.geometry import Point

Step = Callable[[Any], bool]
HELD_SPEED = 0.0


def close_exit_now(ctx: Any, ex: Any) -> tuple[int, int]:
    """Close an exit: people heading there pick another one, or wait at it if none is left."""
    ex.open = False
    moved = trapped = 0
    for jid, info in list(ctx.agents.items()):
        if info.target != ex.id:
            continue
        alt = ctx.best_exit(ctx.position(jid), exclude={ex.id})
        if alt is None:
            ctx.hold_at_blocked_exit(jid, ex)
            trapped += 1
        else:
            ctx.switch(jid, alt)
            moved += 1
    return moved, trapped


def open_exit_now(ctx: Any, ex: Any) -> int:
    """Reopen an exit: people for whom it is now the best choice turn towards it."""
    ex.open = True
    moved = 0
    for jid, info in list(ctx.agents.items()):
        if info.kind == "trapped" or info.target != ex.id:
            best = ctx.best_exit(ctx.position(jid))
            if best == ex.id and best != info.target:
                ctx.switch(jid, ex.id)
                moved += 1
    return moved


def slow_everyone(ctx: Any, factor: float, zone: Any = None) -> int:
    """Multiply walking speed by factor (in a zone, or everywhere and for later arrivals)."""
    affected = 0
    for jid, info in ctx.agents.items():
        if zone is not None and not zone.contains(Point(ctx.position(jid))):
            continue
        info.speed_factor *= factor
        ctx.apply_speed(jid)
        affected += 1
    if zone is None:
        ctx.global_speed_factor *= factor
    return affected


def surge_step(ctx: Any, zone_id: str, n: int, group: str) -> Step:
    """Spawn n extra people in a zone as room frees up (one batch per frame)."""
    zone = ctx.zones[zone_id]
    queue = list(ctx.sample_points(zone, n * 2))
    state = {"left": n}

    def step(c: Any) -> bool:
        if state["left"] <= 0 or not queue:
            if state["left"] > 0:
                c.note(f"Surge in {zone_id}: {state['left']} people could not fit")
            return True
        placed = c.spawn_points(queue, state["left"], group=group, quotas=c.plan_quotas(zone_id))
        state["left"] -= placed
        return state["left"] <= 0

    # what a checkpoint needs to restart this spawn later
    step.pending = lambda: {  # type: ignore[attr-defined]
        "type": "surge",
        "zone_id": zone_id,
        "people": state["left"],
        "group": group,
    }
    return step


def block_exit(ctx: Any, ev: dict[str, Any]) -> Step | None:
    ex = ctx.exits.get(ev["exit_id"])
    if ex is None:
        return None
    moved, trapped = close_exit_now(ctx, ex)
    ctx.note(
        f"{ex.id} blocked at {ctx.t:.0f} s: {moved} people rerouted"
        + (f", {trapped} trapped" if trapped else "")
    )
    ctx.log_event("block_exit", ev, moved=moved, trapped=trapped)
    return None


def unblock_exit(ctx: Any, ev: dict[str, Any]) -> Step | None:
    ex = ctx.exits.get(ev["exit_id"])
    if ex is None:
        return None
    moved = open_exit_now(ctx, ex)
    ctx.log_event("unblock_exit", ev, moved=moved)
    return None


def surge(ctx: Any, ev: dict[str, Any]) -> Step | None:
    if ev["zone_id"] not in ctx.zones:
        return None
    step = surge_step(ctx, ev["zone_id"], int(ev["extra_people"]), f"surge:{ev['zone_id']}")
    ctx.log_event("surge", ev)
    return step


def slowdown(ctx: Any, ev: dict[str, Any]) -> Step | None:
    zone_id = ev.get("zone_id")
    zone = ctx.zones.get(zone_id) if zone_id else None
    affected = slow_everyone(ctx, float(ev["factor"]), zone)
    ctx.log_event("slowdown", ev, affected=affected)
    return None


def counterflow(ctx: Any, ev: dict[str, Any]) -> Step | None:
    ex = ctx.exits.get(ev["exit_id"])
    if ex is None:
        return None
    target_zone = ctx.zones.get(ev.get("target_zone_id") or "")
    goal = target_zone.centroid if target_zone is not None else ctx.free.centroid
    journey = ctx.counterflow_journey(ex.id, (goal.x, goal.y))
    entry = ex.polygon.buffer(3.0).intersection(ctx.free)
    state = {"left": int(ev["people"])}
    seed_box = ctx.sample_points(entry, state["left"] * 3)

    def step(c: Any) -> bool:
        if c.inflow_closed(ex.id):
            if state["left"] > 0:
                c.note(f"One-way flow held {state['left']} people outside {ex.id}")
            return True
        if state["left"] <= 0:
            return True
        # at most ~1.3 people per metre of width per second can push in
        budget = max(1, int(1.3 * ex.width_m * c.frame_dt))
        placed = c.spawn_points(
            seed_box,
            min(budget, state["left"]),
            group=f"inflow:{ex.id}",
            journey=journey,
            kind="counterflow",
        )
        state["left"] -= placed
        return state["left"] <= 0

    step.pending = lambda: {  # type: ignore[attr-defined]
        "type": "counterflow",
        "exit_id": ex.id,
        "people": state["left"],
        "target_zone_id": ev.get("target_zone_id"),
    }
    ctx.log_event("counterflow", ev)
    return step


def one_way(ctx: Any, ev: dict[str, Any]) -> Step | None:
    ctx.closed_inflows.add(ev["exit_id"])
    ctx.log_event("one_way", ev)
    return None


def staggered_release(ctx: Any, ev: dict[str, Any]) -> Step | None:
    until = float(ev.get("at_s", 0.0)) + float(ev["delay_s"])
    held = 0
    for jid, info in ctx.agents.items():
        if info.group == ev["zone_id"]:
            info.held_until = until
            ctx.apply_speed(jid)
            held += 1
    ctx.log_event("staggered_release", ev, held=held)
    return None


def marshal_redirect(ctx: Any, ev: dict[str, Any]) -> Step | None:
    to = ctx.exits.get(ev["to_exit_id"])
    if to is None or not to.open:
        ctx.note(f"Marshal could not redirect to {ev['to_exit_id']}: exit not open")
        return None
    frm = ev.get("from_exit_id")
    x, y = ev.get("x"), ev.get("y")
    radius = float(ev.get("radius_m", 8.0))
    cands = []
    for jid, info in ctx.agents.items():
        if info.target == to.id or info.kind == "counterflow":
            continue
        if frm and info.target != frm:
            continue
        if x is not None and y is not None:
            px, py = ctx.position(jid)
            if (px - x) ** 2 + (py - y) ** 2 > radius**2:
                continue
        cands.append(jid)
    cands.sort()
    k = int(round(len(cands) * float(ev.get("fraction", 0.5))))
    chosen = list(ctx.rng.choice(np.asarray(cands), size=k, replace=False)) if k else []
    for jid in chosen:
        ctx.switch(int(jid), to.id)
    if x is None or y is None:
        src = ctx.exits.get(frm) if frm else None
        x, y = src.center if src else to.center
    ctx.marshals.append(
        {
            "t_s": round(ctx.t, 1),
            "x": round(float(x), 2),
            "y": round(float(y), 2),
            "floor_id": ctx.floor_id,
            "speech": ev.get("speech") or f"This way to {to.id}!",
            "moved": len(chosen),
            "marshal_id": ev.get("marshal_id"),
        }
    )
    ctx.log_event("marshal_redirect", ev, moved=len(chosen))
    return None


def script(ctx: Any, ev: dict[str, Any]) -> Step | None:
    """An AI- or user-written scenario: on_step(view, act) every every_s seconds."""
    runner = ScriptRunner(ctx, ev)
    ctx.scripts.append(runner)
    runner.tick(ctx)
    return None


HANDLERS: dict[str, Callable[[Any, dict[str, Any]], Step | None]] = {
    "block_exit": block_exit,
    "unblock_exit": unblock_exit,
    "surge": surge,
    "slowdown": slowdown,
    "counterflow": counterflow,
    "one_way": one_way,
    "staggered_release": staggered_release,
    "marshal_redirect": marshal_redirect,
    "script": script,
}

# Which id field ties an event to a floor (events without one apply to every floor).
FLOOR_KEYS = ("exit_id", "zone_id", "to_exit_id")
