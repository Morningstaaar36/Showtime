"""JuPedSim engine: per-floor simulations chained through stairs (section 10.2-10.3).

Upper floors run first; people reaching a stair top are queued on the stair
(travel = length / STAIR_SPEED, throughput = width x STAIR_FLOW) and injected at the
stair bottom of the floor below at the computed times.
"""

from __future__ import annotations

import heapq
import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jupedsim as jps
import numpy as np
import shapely
from jps_build import (
    AgentInfo,
    ExitInfo,
    assign_targets,
    floor_geometry,
    floor_run_order,
    inside,
    nearest_free_point,
    place_people,
    to_poly,
)
from script_api import ScriptRunner
from shapely.geometry import Polygon

from plugins.events import FLOOR_KEYS, HANDLERS, surge_step

ENGINE_ID = "jupedsim"
REWIND_SINGLE_FLOOR = "rewind needs a single-floor venue"
COUNTERFLOW_STAIR_FACTOR = 0.5  # same as the instant estimate (plugins/events_core)


# People who move differently (a zone's `groups`): level walking speed (m/s) and body radius (m).
# Sources and limits in docs/ASSUMPTIONS.md ("People mix"). Mirrored in api/core/tier1.py.
KIND_SPEED = {"elderly": 0.97, "child": 1.0, "wheelchair": 0.69, "bed": 0.5}
KIND_RADIUS = {"child": 0.17, "wheelchair": 0.4, "bed": 0.6}


def assign_kinds(n: int, groups: list[dict[str, Any]], rng: np.random.Generator) -> list[str]:
    """A kind for each of `n` placed people: exact shares (largest remainder), seeded order."""
    if n <= 0 or not groups:
        return ["general"] * max(n, 0)
    want = [(str(g["kind"]), float(g["share"]) * n) for g in groups]
    counts = {k: int(x) for k, x in want}
    left = n - sum(counts.values()) - round(n * (1 - sum(float(g["share"]) for g in groups)))
    for k, _x in sorted(want, key=lambda kx: -(kx[1] - int(kx[1])))[: max(left, 0)]:
        counts[k] += 1
    kinds = [k for k, c in counts.items() for _ in range(c)]
    kinds += ["general"] * (n - len(kinds))
    return [kinds[i] for i in rng.permutation(n)]


def mobility_pick(gid: int, share: float) -> bool:
    """Whether person `gid` belongs to a share (a fixed hash: same people every run and floor)."""
    return ((gid * 2654435761) % 4294967296) / 4294967296.0 < share


def _ev_key(ev: dict[str, Any]) -> str:
    return json.dumps(ev, sort_keys=True, default=str)


@dataclass
class FloorOutput:
    """What one floor run produced."""

    floor_id: str
    frames_t: list[float] = field(default_factory=list)
    frames: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=list)
    exit_times: list[tuple[float, int, str]] = field(default_factory=list)  # (t, gid, exit)
    stair_arrivals: list[tuple[float, int, str]] = field(default_factory=list)
    remaining: int = 0
    trapped: int = 0  # people with no open exit (genuine), not model stragglers
    pending: int = 0  # people never placed (no space) or still queued
    no_exit: int = 0  # people never placed because their floor had no open exit
    status: str = "ok"
    sim_time: float = 0.0
    notes: list[str] = field(default_factory=list)
    marshals: list[dict[str, Any]] = field(default_factory=list)
    event_log: list[dict[str, Any]] = field(default_factory=list)


class FloorRun:
    """One floor's JuPedSim simulation plus the bookkeeping event handlers need."""

    def __init__(
        self,
        floor: dict[str, Any],
        venue: dict[str, Any],
        settings: dict[str, Any],
        plan: dict[str, Any],
        events: list[dict[str, Any]],
        seed: int,
        gids: list[int],
        arrivals: list[tuple[float, int, str]],
        base_floor: dict[str, Any] | None = None,
        intervention_at_s: float | None = None,
        checkpoint_at_s: float | None = None,
        checkpoint_path: Path | None = None,
        resume_state: dict[str, Any] | None = None,
        slow: dict[int, float] | None = None,
        kinds: dict[int, str] | None = None,
    ) -> None:
        self.floor_id: str = floor["floor_id"]
        # slower walkers (mobility_share): gid -> level speed, shared by every floor so a
        # person stays slow on the floors below and on the stairs
        self.slow: dict[int, float] = slow if slow is not None else {}
        # who is not a general adult (a zone's people mix): gid -> kind, shared by every floor
        self.kinds: dict[int, str] = kinds if kinds is not None else {}
        self.mobility_rules: list[tuple[float, float]] = []
        self.settings = settings
        self.plan = plan
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.gids = gids  # shared counter [next_gid]
        self.dt = float(settings.get("dt", 0.05))
        self.frame_dt = float(settings.get("frame_dt", 0.25))
        self.radius = float(settings.get("agent_radius", 0.22))
        self.time_gap = float(settings.get("agent_time_gap", 1.0))
        self.rejected = 0
        self.out = FloorOutput(floor_id=self.floor_id)
        self.t = 0.0
        self.global_speed_factor = 1.0
        self.closed_inflows: set[str] = set()
        self.marshals = self.out.marshals
        self.intervention_at_s = intervention_at_s
        patched_geom = floor_geometry(floor)
        self.patched_free = patched_geom.free
        start_floor = base_floor if (base_floor is not None and intervention_at_s) else floor
        self.free = floor_geometry(start_floor).free
        self.geometry_pending = (
            base_floor is not None
            and intervention_at_s is not None
            and not self.free.equals(self.patched_free)
        )
        self.model_name = str(settings.get("model", "cfsm"))
        if self.model_name == "avm":
            # Anticipation velocity model (JuPedSim >= 1.3): fewer deadlocks at bottlenecks
            model: Any = jps.AnticipationVelocityModel(rng_seed=seed & 0x7FFFFFFF)
            self.params_cls: Any = jps.AnticipationVelocityModelAgentParameters
        else:
            model = jps.CollisionFreeSpeedModel()
            self.params_cls = jps.CollisionFreeSpeedModelAgentParameters
        self.sim = jps.Simulation(model=model, geometry=self.free, dt=self.dt)

        base_exit_ids = {e["id"] for e in (base_floor or floor).get("exits", [])}
        self.exits: dict[str, ExitInfo] = {}
        self.load: dict[str, int] = {}
        self.late_exits: set[str] = set()
        flow = float(settings.get("specific_flow", 1.3))
        for e in floor.get("exits", []):
            poly = patched_geom.exit_stages[e["id"]]
            info = ExitInfo(
                id=e["id"],
                polygon=poly,
                width_m=float(e["width_m"]),
                kind="exit",
                open=not e.get("blocked", False),
                capacity_pps=flow * e["width_m"],
            )
            if intervention_at_s and e["id"] not in base_exit_ids:
                # a fix's new exit: its stage is created at the intervention time, after
                # the layout switch, so the run is identical to its parent before that
                info.open = False
                self.late_exits.add(e["id"])
                self.exits[info.id] = info
                self.load[info.id] = 0
                continue
            self._add_exit(info)
        stair_flow = float(settings.get("stair_flow", 1.0))
        for s in venue.get("stairs", []):
            if s["from_floor"] == self.floor_id:
                poly = inside(self.free, to_poly(s["top_polygon"]))
                self._add_exit(
                    ExitInfo(
                        id=s["id"],
                        polygon=poly,
                        width_m=float(s["width_m"]),
                        kind="stair",
                        capacity_pps=stair_flow * s["width_m"],
                    )
                )
        self.bottoms: dict[str, Polygon] = {
            s["id"]: inside(self.free, to_poly(s["bottom_polygon"]))
            for s in venue.get("stairs", [])
            if s["to_floor"] == self.floor_id
        }

        self.zones: dict[str, Polygon] = {}
        for z in floor.get("zones", []):
            area = to_poly(z["polygon"]).intersection(self.free)
            if not area.is_empty:
                self.zones[z["id"]] = area
        self.zone_people = {z["id"]: int(z["people"]) for z in floor.get("zones", [])}
        self.zone_groups = {z["id"]: list(z.get("groups") or []) for z in floor.get("zones", [])}

        self.agents: dict[int, AgentInfo] = {}
        self.held: list[tuple[float, int]] = []
        self.hold_journeys: dict[str, tuple[int, int]] = {}
        self.cf_journeys: dict[tuple[str, tuple[float, float]], tuple[int, int, str]] = {}
        self.arrivals = sorted(arrivals)
        self.arrival_queue: list[tuple[float, int, str]] = []
        # at the same instant, rules that close or reopen things act before spawns
        first = {"one_way": 0, "block_exit": 1, "unblock_exit": 1}
        self.events = sorted(
            events, key=lambda e: (float(e.get("at_s", 0.0)), first.get(str(e.get("type")), 2))
        )
        self.steps: list[Any] = []
        self.scripts: list[Any] = []  # ScriptRunner per `script` event (script_api.py)
        self.t0 = 0.0  # simulated time this run starts at (> 0 when resuming a checkpoint)
        self.fired: list[dict[str, Any]] = []
        self.checkpoint_at_s = checkpoint_at_s
        self.checkpoint_path = checkpoint_path
        self.checkpoint_t: float | None = None
        self.resume_state = resume_state
        if resume_state is not None:
            # events already applied before the checkpoint are part of its state
            done = Counter(_ev_key(e) for e in resume_state.get("fired_events", []))
            kept = []
            for e in self.events:
                if done[_ev_key(e)] > 0:
                    done[_ev_key(e)] -= 1
                else:
                    kept.append(e)
            self.events = kept
        self._gid_of: dict[int, int] = {}
        self.last_exit_t: dict[str, float] = {}
        self.squeezed: set[int] = set()
        self.clogs: list[dict[str, Any]] = []
        self.squeeze_radius = float(settings.get("squeeze_radius", 0.15))
        self.clog_after_s = float(settings.get("clog_after_s", 4.0))
        self._next_clog_check = 2.0
        self._snap: dict[int, tuple[float, float]] = {}
        self._still: dict[int, int] = {}
        self._next_stuck_check = 5.0
        self.unstuck = 0
        self.sidesteps = 0

    # ------------------------------------------------------------------ setup
    def _add_exit(self, info: ExitInfo) -> None:
        info.stage_id = self.sim.add_exit_stage(info.polygon)
        info.journey_id = self.sim.add_journey(jps.JourneyDescription([info.stage_id]))
        self.exits[info.id] = info
        self.load[info.id] = 0

    def _speed(self) -> float:
        s = self.settings
        if self.rng.random() < float(s.get("slow_walker_fraction", 0.05)):
            v = self.rng.normal(0.7, 0.1)
            return float(np.clip(v, 0.4, 0.9))
        v = self.rng.normal(
            float(s.get("walk_speed_mean", 1.34)), float(s.get("walk_speed_sd", 0.26))
        )
        return float(np.clip(v, 0.6, 2.0))

    def plan_quotas(self, group: str) -> dict[str, int]:
        quotas = self.plan.get("groups", {}).get(group) or {}
        return {k: int(v) for k, v in quotas.items() if k in self.exits and self.exits[k].open}

    def populate(self) -> None:
        """Place every zone's people at t = 0 and give them targets."""
        for i, (zid, area) in enumerate(self.zones.items()):
            n = self.zone_people.get(zid, 0)
            if n <= 0:
                continue
            points, kinds, shortfall = self._place_zone(zid, area, n, self.seed * 1000 + i)
            if shortfall:
                self.note(f"Zone {zid}: {shortfall} people did not fit and were left out")
                self.out.pending += shortfall
            quotas = self.plan_quotas(zid)
            targets = assign_targets(points, quotas, self.exits) if quotas else []
            for k, pos in enumerate(points):
                target = targets[k] if targets else self.nearest_exit(pos)
                if target is None:
                    self.note(f"Zone {zid} has no open exit on {self.floor_id}")
                    left = len(points) - k
                    self.out.pending += left
                    self.out.no_exit += left
                    break
                who = kinds[k]
                speed = None
                if who in KIND_SPEED:
                    speed = float(np.clip(KIND_SPEED[who] * self.rng.normal(1.0, 0.1), 0.2, 2.0))
                self._add_agent(pos, zid, target, initial=True, speed=speed, people_kind=who)

    def _place_zone(
        self, zid: str, area: Polygon, n: int, seed: int
    ) -> tuple[list[tuple[float, float]], list[str], int]:
        """Positions and kinds for a zone's people (and how many did not fit).

        People wider than an adult (wheelchairs, beds) are placed first at their own spacing,
        then everyone else around them, so nobody is placed overlapping a wide neighbour.
        """
        kinds = assign_kinds(n, self.zone_groups.get(zid, []), np.random.default_rng(seed))
        wide = [k for k in kinds if KIND_RADIUS.get(k, self.radius) > self.radius]
        if not wide:
            placement = place_people(jps, area, n, seed=seed, radius=self.radius)
            return placement.points, kinds[: len(placement.points)], placement.shortfall
        big = max(KIND_RADIUS[k] for k in wide)
        first = place_people(jps, area, len(wide), seed=seed, radius=big)
        rest = [k for k in kinds if KIND_RADIUS.get(k, self.radius) <= self.radius]
        # every spot an adult could take (a full lattice), then keep those clear of wide people
        room = int(area.area / (2 * self.radius + 0.02) ** 2)
        spare = place_people(jps, area, max(room, len(rest)), seed=seed + 1, radius=self.radius)
        gap = big + self.radius + 0.02
        taken = np.asarray(first.points, dtype=float).reshape(-1, 2)
        others: list[tuple[float, float]] = []
        for pt in spare.points:
            if len(others) == len(rest):
                break
            if len(taken) and float(np.min(np.hypot(*(taken - np.asarray(pt)).T))) < gap:
                continue
            others.append(pt)
        points = list(first.points) + others
        out_kinds = wide[: len(first.points)] + rest[: len(others)]
        return points, out_kinds, n - len(points)

    def _add_agent(
        self,
        pos: tuple[float, float],
        group: str,
        target: str,
        journey: tuple[int, int] | None = None,
        kind: str = "normal",
        gid: int | None = None,
        initial: bool = False,
        speed: float | None = None,
        people_kind: str = "general",
    ) -> int | None:
        ex = self.exits[target]
        speed = self._speed() if speed is None else speed
        if gid is not None and people_kind == "general":
            people_kind = self.kinds.get(gid, "general")  # someone arriving down a stair
        radius = KIND_RADIUS.get(people_kind, self.radius)
        if kind == "normal":
            speed = self.mobility_speed(gid if gid is not None else self.gids[0], speed)
        jid_stage = journey if journey is not None else (ex.journey_id, ex.stage_id)
        jid = None
        # a bed or wheelchair is wider than the spacing people were placed at: if it does not
        # fit there, it keeps its speed and takes an ordinary person's room
        for r in dict.fromkeys((radius, self.radius)):
            try:
                jid = self.sim.add_agent(
                    self.params_cls(
                        position=pos,
                        journey_id=jid_stage[0],
                        stage_id=jid_stage[1],
                        desired_speed=speed * self.global_speed_factor,
                        radius=r,
                        **({"time_gap": self.time_gap} if self.model_name != "avm" else {}),
                    )
                )
                break
            except Exception:
                continue
        if jid is None:
            if initial:
                self.rejected += 1
            return None
        if gid is None:
            gid = self.gids[0]
            self.gids[0] += 1
        if people_kind != "general":
            self.kinds[gid] = people_kind
            if people_kind in KIND_SPEED:  # stays this slow on the stairs and the floors below
                self.slow[gid] = min(self.slow.get(gid, speed), speed)
        self.agents[jid] = AgentInfo(
            gid=gid,
            group=group,
            target=target,
            speed=speed,
            spawn_t=self.t,
            kind=kind,
            speed_factor=self.global_speed_factor,
        )
        self.load[target] = self.load.get(target, 0) + 1
        self._gid_of[jid] = gid
        return jid

    # ------------------------------------------------------------- handler API
    def mobility_speed(self, gid: int, speed: float) -> float:
        """Level walking speed of person `gid` after the slower-walker rules of this floor."""
        for share, v in self.mobility_rules:
            if mobility_pick(gid, share):
                self.slow[gid] = min(self.slow.get(gid, v), v)
        v = self.slow.get(gid)
        return min(speed, v) if v is not None else speed

    def note(self, text: str) -> None:
        if text not in self.out.notes and len(self.out.notes) < 40:
            self.out.notes.append(text)

    def log_event(self, kind: str, ev: dict[str, Any], **extra: Any) -> None:
        self.out.event_log.append(
            {"t_s": round(self.t, 2), "type": kind, "floor_id": self.floor_id, **extra}
        )

    def position(self, jid: int) -> tuple[float, float]:
        p = self.sim.agent(jid).position
        return (float(p[0]), float(p[1]))

    def best_exit(self, pos: tuple[float, float], exclude: set[str] | None = None) -> str | None:
        """Open exit minimising walk time + queue time (people already heading there)."""
        best, best_cost = None, math.inf
        for ex in self.exits.values():
            if not ex.open or (exclude and ex.id in exclude):
                continue
            cx, cy = ex.center
            walk = math.hypot(pos[0] - cx, pos[1] - cy) / 1.3
            cost = walk + self.load.get(ex.id, 0) / max(ex.capacity_pps, 0.1)
            if cost < best_cost:
                best, best_cost = ex.id, cost
        return best

    def nearest_exit(self, pos: tuple[float, float]) -> str | None:
        """Closest open exit by straight-line distance (initial choice without a plan)."""
        open_exits = [e for e in self.exits.values() if e.open]
        if not open_exits:
            return None
        return min(
            open_exits, key=lambda e: math.hypot(pos[0] - e.center[0], pos[1] - e.center[1])
        ).id

    def switch(self, jid: int, exit_id: str) -> None:
        info = self.agents.get(jid)
        if info is None:
            return
        ex = self.exits[exit_id]
        self.sim.switch_agent_journey(jid, ex.journey_id, ex.stage_id)
        if info.target in self.load:
            self.load[info.target] -= 1
        info.target = exit_id
        if info.kind == "trapped":
            info.kind = "normal"
        self.load[exit_id] = self.load.get(exit_id, 0) + 1

    def hold_at_blocked_exit(self, jid: int, ex: ExitInfo) -> None:
        if ex.id not in self.hold_journeys:
            cx, cy = ex.center
            px, py = nearest_free_point(self.free, cx, cy)
            stage = self.sim.add_waypoint_stage((px, py), 1.5)
            self.hold_journeys[ex.id] = (
                self.sim.add_journey(jps.JourneyDescription([stage])),
                stage,
            )
        journey, stage = self.hold_journeys[ex.id]
        self.sim.switch_agent_journey(jid, journey, stage)
        info = self.agents[jid]
        info.kind = "trapped"

    def apply_speed(self, jid: int) -> None:
        info = self.agents.get(jid)
        if info is None:
            return
        held = info.held_until is not None and info.held_until > self.t
        speed = 0.0 if held else info.speed * info.speed_factor
        self.sim.agent(jid).model.desired_speed = speed
        if held:
            heapq.heappush(self.held, (float(info.held_until or 0.0), jid))

    def inflow_closed(self, exit_id: str) -> bool:
        return exit_id in self.closed_inflows

    def sample_points(self, area: Any, n: int) -> list[tuple[float, float]]:
        """Random points at least one body radius (+5 cm) away from walls."""
        if area.is_empty or n <= 0:
            return []
        shrunk = area.intersection(self.free.buffer(-(self.radius + 0.05)))
        area = shrunk if not shrunk.is_empty else area
        minx, miny, maxx, maxy = area.bounds
        out: list[tuple[float, float]] = []
        for _ in range(20):
            xs = self.rng.uniform(minx, maxx, size=n * 2)
            ys = self.rng.uniform(miny, maxy, size=n * 2)
            mask = shapely.contains_xy(area, xs, ys)
            out.extend(zip(xs[mask].tolist(), ys[mask].tolist(), strict=True))
            if len(out) >= n:
                break
        return out[:n]

    def _free_spot(self, pos: tuple[float, float]) -> bool:
        if not shapely.contains_xy(self.free, pos[0], pos[1]):
            return False
        # agents_in_range returns an iterator that is always truthy: test for a first item
        return next(iter(self.sim.agents_in_range(pos, 2 * self.radius + 0.05)), None) is None

    def spawn_points(
        self,
        queue: list[tuple[float, float]],
        n: int,
        group: str,
        quotas: dict[str, int] | None = None,
        journey: tuple[int, int, str] | None = None,
        kind: str = "normal",
    ) -> int:
        """Place up to n people from `queue` where there is room; consumed points are removed."""
        placed = 0
        tries = 0
        keep: list[tuple[float, float]] = []
        while queue and placed < n and tries < n * 6:
            pos = queue.pop()
            tries += 1
            if not self._free_spot(pos):
                keep.append(pos)
                continue
            if journey is not None:
                target = journey[2]
                jid = self._add_agent(
                    pos, group, target, journey=(journey[0], journey[1]), kind=kind
                )
            else:
                target = self._quota_target(quotas) if quotas else self.best_exit(pos)
                if target is None:
                    break
                jid = self._add_agent(pos, group, target, kind=kind)
            if jid is not None:
                placed += 1
                if kind == "normal":
                    self.apply_speed(jid)
        queue[:0] = keep
        return placed

    def _quota_target(self, quotas: dict[str, int]) -> str | None:
        ids = [k for k, v in quotas.items() if v > 0 and self.exits[k].open]
        if not ids:
            return None
        weights = np.asarray([quotas[k] for k in ids], dtype=float)
        return str(self.rng.choice(ids, p=weights / weights.sum()))

    def counterflow_journey(
        self, entry_exit: str, goal: tuple[float, float]
    ) -> tuple[int, int, str]:
        key = (entry_exit, (round(goal[0], 1), round(goal[1], 1)))
        if key in self.cf_journeys:
            return self.cf_journeys[key]
        gx, gy = nearest_free_point(self.free, goal[0], goal[1])
        final = self.best_exit((gx, gy), exclude={entry_exit}) or entry_exit
        wp = self.sim.add_waypoint_stage((gx, gy), 2.0)
        jd = jps.JourneyDescription([wp, self.exits[final].stage_id])
        jd.set_transition_for_stage(
            wp, jps.Transition.create_fixed_transition(self.exits[final].stage_id)
        )
        journey = (self.sim.add_journey(jd), wp, final)
        self.cf_journeys[key] = journey
        return journey

    # ------------------------------------------------------- checkpoint/resume
    def _write_checkpoint(self) -> None:
        """Everything needed to restart this floor from now (velocities are not kept)."""
        agents = []
        for ag in self.sim.agents():
            info = self.agents.get(ag.id)
            if info is None:
                continue
            agents.append(
                {
                    "gid": info.gid,
                    "x": float(ag.position[0]),
                    "y": float(ag.position[1]),
                    "target": info.target,
                    "kind": info.kind,
                    "group": info.group,
                    "speed": info.speed,
                    "speed_factor": info.speed_factor,
                    "held_until": info.held_until,
                    "spawn_t": info.spawn_t,
                    "radius": float(ag.model.radius),
                }
            )
        pending = [s.pending() for s in self.steps if hasattr(s, "pending")]
        state = {
            "version": 1,
            "t": round(self.t, 4),
            "floor_id": self.floor_id,
            "seed": self.seed,
            "next_gid": self.gids[0],
            "agents": agents,
            "exits": {eid: ex.open for eid, ex in self.exits.items()},
            "closed_inflows": sorted(self.closed_inflows),
            "global_speed_factor": self.global_speed_factor,
            "mobility_rules": [list(r) for r in self.mobility_rules],
            "slow": {str(k): v for k, v in self.slow.items()},
            "kinds": {str(k): v for k, v in self.kinds.items()},
            "pending_spawns": [p for p in pending if p.get("people", 0) > 0],
            "pending_people": self.out.pending + self.rejected,
            "no_exit_people": self.out.no_exit,
            "exit_times": [list(x) for x in self.out.exit_times],
            "fired_events": self.fired,
            "scripts": [sc.snapshot() for sc in self.scripts],
            "notes": list(self.out.notes),
            "event_log": list(self.out.event_log),
            "marshals": list(self.out.marshals),
        }
        if self.checkpoint_path is not None:
            self.checkpoint_path.write_text(json.dumps(state))
        self.checkpoint_t = self.t
        self.log_event("checkpoint", {}, people=len(agents))

    def _restore(self, cp: dict[str, Any]) -> None:
        """Start from a checkpoint instead of placing the zones' people."""
        self.t0 = float(cp["t"])
        self.t = self.t0
        self.gids[0] = max(self.gids[0], int(cp["next_gid"]))
        for eid, is_open in cp.get("exits", {}).items():
            if eid in self.exits and eid not in self.late_exits:
                self.exits[eid].open = bool(is_open)
        self.closed_inflows = set(cp.get("closed_inflows", []))
        self.global_speed_factor = float(cp.get("global_speed_factor", 1.0))
        self.mobility_rules = [(float(a), float(b)) for a, b in cp.get("mobility_rules", [])]
        self.slow.update({int(k): float(v) for k, v in cp.get("slow", {}).items()})
        self.kinds.update({int(k): str(v) for k, v in cp.get("kinds", {}).items()})
        self.out.exit_times = [(float(t), int(g), str(e)) for t, g, e in cp["exit_times"]]
        self.out.notes = list(cp.get("notes", []))
        self.out.event_log = list(cp.get("event_log", []))
        self.out.marshals[:] = cp.get("marshals", [])
        self.out.pending = int(cp.get("pending_people", 0))
        self.out.no_exit = int(cp.get("no_exit_people", 0))
        self.last_exit_t = {eid: self.t0 for eid in self.exits}
        self._next_clog_check = self.t0 + 2.0
        self._next_stuck_check = self.t0 + 5.0
        lost = 0
        for a in cp["agents"]:
            pos = (float(a["x"]), float(a["y"]))
            target = a["target"]
            if target not in self.exits or (not self.exits[target].open and a["kind"] != "trapped"):
                target = self.best_exit(pos) or target
            if target not in self.exits:
                lost += 1
                continue
            kind = a["kind"] if a["kind"] in ("normal", "counterflow", "trapped") else "normal"
            jid = None
            # someone squeezed against a wall or door jamb is nudged just inside the free space
            for p in (pos, nearest_free_point(self.free, pos[0], pos[1])):
                jid = self._add_agent(
                    p,
                    a["group"],
                    target,
                    kind="normal" if kind == "trapped" else kind,
                    gid=int(a["gid"]),
                    speed=float(a["speed"]),
                )
                if jid is not None:
                    break
            if jid is None:
                lost += 1
                continue
            info = self.agents[jid]
            info.speed_factor = float(a["speed_factor"])
            info.held_until = a.get("held_until")
            info.spawn_t = float(a.get("spawn_t", 0.0))
            if kind == "trapped":
                self.hold_at_blocked_exit(jid, self.exits[target])
            if float(a.get("radius", self.radius)) < self.radius - 1e-6:
                self.sim.agent(jid).model.radius = float(a["radius"])
                self.squeezed.add(jid)
            self.apply_speed(jid)
        if lost:
            self.note(f"{lost} people could not be put back at the checkpoint")
            self.out.pending += lost
        for p in cp.get("pending_spawns", []):
            n_log = len(self.out.event_log)
            if p["type"] == "surge" and p["zone_id"] in self.zones:
                self.steps.append(surge_step(self, p["zone_id"], int(p["people"]), p["group"]))
            elif p["type"] == "counterflow" and p["exit_id"] in self.exits:
                ev = {
                    "type": "counterflow",
                    "exit_id": p["exit_id"],
                    "people": int(p["people"]),
                    "target_zone_id": p.get("target_zone_id"),
                }
                step = HANDLERS["counterflow"](self, ev)
                if step is not None:
                    self.steps.append(step)
            del self.out.event_log[n_log:]
        for snap in cp.get("scripts", []):
            self.scripts.append(ScriptRunner(self, snap["event"], restore=snap))
        self.note(
            f"Rewound to {self.t0:g} s: {len(self.agents)} people put back where they stood "
            "(walking speeds restart from standstill)"
        )
        self.log_event("resume", {}, people=len(self.agents))

    # ---------------------------------------------------------------- the loop
    def _record(self) -> None:
        n = self.sim.agent_count()
        ids = np.empty(n, dtype=np.uint16)
        xs = np.empty(n, dtype=np.float32)
        ys = np.empty(n, dtype=np.float32)
        for k, ag in enumerate(self.sim.agents()):
            if k >= n:
                break
            info = self.agents.get(ag.id)
            ids[k] = (info.gid if info else 0) & 0xFFFF
            xs[k], ys[k] = ag.position
        self.out.frames_t.append(round(self.t, 3))
        self.out.frames.append((ids, xs, ys))

    def _doorway_capture(self) -> None:
        """Anyone standing in an open doorway leaves through it.

        JuPedSim only removes people at the exit they are heading for; someone pushed into
        another door's opening would otherwise plug it for everyone behind them.
        """
        for ex in self.exits.values():
            if not ex.open or ex.kind != "exit":
                continue
            for jid in self.sim.agents_in_polygon(ex.polygon):
                info = self.agents.get(jid)
                if info is None or info.target == ex.id or info.kind == "counterflow":
                    continue
                if info.kind == "trapped":
                    info.kind = "normal"
                self.switch(jid, ex.id)

    def _unclog(self) -> None:
        """Squeeze rule: a door with a queue but nobody through for `clog_after_s` seconds.

        The collision-free speed model can deadlock where flows converge on a door. Real
        bodies compress under pressure, so people within 3 m of a clogged door get a smaller
        body radius until they are through (documented in docs/ASSUMPTIONS.md).
        """
        for ex in self.exits.values():
            if not ex.open or self.load.get(ex.id, 0) <= 0:
                continue
            last = self.last_exit_t.get(ex.id, 0.0)
            if self.t - last < self.clog_after_s:
                continue
            cx, cy = ex.center
            near = [
                j
                for j in self.sim.agents_in_range((cx, cy), 3.0 + ex.width_m / 2)
                if j in self.agents and self.agents[j].target == ex.id
            ]
            if not near:
                continue
            newly = 0
            for jid in near:
                if jid in self.squeezed:
                    continue
                try:
                    self.sim.agent(jid).model.radius = self.squeeze_radius
                except Exception:
                    continue
                self.squeezed.add(jid)
                newly += 1
            if newly:
                self.clogs.append(
                    {
                        "t_s": round(self.t, 1),
                        "exit_id": ex.id,
                        "people": newly,
                        "floor_id": self.floor_id,
                    }
                )
                self.last_exit_t[ex.id] = self.t  # give the squeeze time to work

    def _unstick(self) -> None:
        """Small deadlocks: someone who has not moved 15 cm in 10 s with almost nobody
        around (≤ 3 people within 1.5 m) gets the squeeze radius so they can sidestep.
        Dense jams are left alone: they are real congestion, not a model artifact."""
        snap: dict[int, tuple[float, float]] = {}
        for ag in self.sim.agents():
            snap[ag.id] = (float(ag.position[0]), float(ag.position[1]))
        for jid, pos in snap.items():
            info = self.agents.get(jid)
            prev = self._snap.get(jid)
            held = info is not None and info.held_until is not None and info.held_until > self.t
            if (
                info is None
                or prev is None
                or held
                or info.kind == "trapped"
                or math.hypot(pos[0] - prev[0], pos[1] - prev[1]) >= 0.15
            ):
                self._still[jid] = 0
                continue
            self._still[jid] = self._still.get(jid, 0) + 1
            if self._still[jid] < 2:
                continue
            near = sum(1 for _ in self.sim.agents_in_range(pos, 1.5)) - 1
            if near > 3:
                continue
            if jid not in self.squeezed:
                try:
                    self.sim.agent(jid).model.radius = self.squeeze_radius
                except Exception:
                    continue
                self.squeezed.add(jid)
                self.unstuck += 1
            elif self._still[jid] >= 3:
                self._sidestep(jid, pos)
                self._still[jid] = 0
        self._snap = snap

    def _sidestep(self, jid: int, pos: tuple[float, float]) -> None:
        """Head-on deadlock: walk 1 m sideways via a waypoint, then on to the same exit."""
        info = self.agents.get(jid)
        if info is None or info.target not in self.exits:
            return
        ex = self.exits[info.target]
        dx, dy = ex.center[0] - pos[0], ex.center[1] - pos[1]
        norm = math.hypot(dx, dy) or 1.0
        nx_, ny_ = -dy / norm, dx / norm
        best: tuple[int, tuple[float, float]] | None = None
        for sign in (1.0, -1.0):
            cand = (
                pos[0] + sign * nx_ * 1.0 + dx / norm * 0.3,
                pos[1] + sign * ny_ * 1.0 + dy / norm * 0.3,
            )
            if not shapely.contains_xy(self.free.buffer(-self.radius), cand[0], cand[1]):
                continue
            crowd = sum(1 for _ in self.sim.agents_in_range(cand, 0.6))
            if best is None or crowd < best[0]:
                best = (crowd, cand)
        if best is None:
            return
        wp = self.sim.add_waypoint_stage(best[1], 0.4)
        jd = jps.JourneyDescription([wp, ex.stage_id])
        jd.set_transition_for_stage(wp, jps.Transition.create_fixed_transition(ex.stage_id))
        self.sim.switch_agent_journey(jid, self.sim.add_journey(jd), wp)
        self.sidesteps += 1

    def _intervene(self) -> None:
        """Time travel: the fix starts now (new exits open, geometry changes, rebalance)."""
        if self.geometry_pending:
            try:
                self.sim.switch_geometry(self.patched_free)
                self.free = self.patched_free
            except RuntimeError:
                self.note(
                    "The fix's layout change could not be applied mid-run "
                    "(people stood where it goes); it was skipped in this run"
                )
            self.geometry_pending = False
        for eid in self.late_exits:
            try:
                self._add_exit(self.exits[eid])
                self.exits[eid].open = True
            except RuntimeError:
                self.note(f"The fix's new exit {eid} could not be opened mid-run")
        moved = 0
        for jid, info in list(self.agents.items()):
            if info.kind != "normal":
                continue
            best = self.best_exit(self.position(jid))
            if best and best != info.target:
                self.switch(jid, best)
                moved += 1
        self.log_event("intervention", {}, moved=moved)

    def _due_arrivals(self) -> None:
        while self.arrivals and self.arrivals[0][0] <= self.t:
            self.arrival_queue.append(self.arrivals.pop(0))
        if not self.arrival_queue:
            return
        left: list[tuple[float, int, str]] = []
        for t_arr, gid, stair_id in self.arrival_queue:
            area = self.bottoms.get(stair_id)
            placed = False
            if area is not None:
                for pos in self.sample_points(area, 6):
                    if self._free_spot(pos):
                        quotas = self.plan.get("stairs", {}).get(stair_id) or {}
                        quotas = {
                            k: int(v)
                            for k, v in quotas.items()
                            if k in self.exits and self.exits[k].open
                        }
                        target = self._quota_target(quotas) if quotas else self.best_exit(pos)
                        if (
                            target
                            and self._add_agent(
                                pos, f"stair:{stair_id}", target, kind="normal", gid=gid
                            )
                            is not None
                        ):
                            placed = True
                        break
            if not placed:
                left.append((t_arr, gid, stair_id))
        self.arrival_queue = left

    def _now(self) -> float:
        return self.t0 + float(self.sim.elapsed_time())

    def run(self, max_sim_s: float, deadline: float, progress: Any) -> FloorOutput:
        if self.resume_state is not None:
            self._restore(self.resume_state)
        else:
            self.populate()
        ev_idx = 0
        intervened = self.intervention_at_s is None
        spawn_types = {"surge", "counterflow"}
        self._record()
        next_frame = self.t0 + self.frame_dt
        it = 0
        while True:
            self.t = self._now()
            if (
                self.checkpoint_at_s is not None
                and self.checkpoint_t is None
                and self.t >= self.checkpoint_at_s - 1e-9
            ):
                self._write_checkpoint()
            if not intervened and self.t >= float(self.intervention_at_s or 0.0):
                self._intervene()
                intervened = True
            while (
                ev_idx < len(self.events)
                and float(self.events[ev_idx].get("at_s", 0)) <= self.t + 1e-9
            ):
                ev = self.events[ev_idx]
                ev_idx += 1
                handler = HANDLERS.get(ev.get("type", ""))
                if handler is None:
                    self.note(f"Event type '{ev.get('type')}' is not supported by the engine")
                    continue
                self.fired.append(ev)
                step = handler(self, ev)
                if step is not None and not step(self):
                    self.steps.append(step)
            while self.held and self.held[0][0] <= self.t:
                _, jid = heapq.heappop(self.held)
                self.apply_speed(jid)
            future_spawns = any(e.get("type") in spawn_types for e in self.events[ev_idx:])
            if (
                not self.agents
                and not self.steps
                and not self.arrivals
                and not self.arrival_queue
                and not future_spawns
            ):
                break
            if self.t >= max_sim_s:
                self.out.status = "partial"
                break
            if it % 50 == 0 and time.monotonic() > deadline:
                self.out.status = "timeout"
                break
            self.sim.iterate()
            it += 1
            for jid in self.sim.removed_agents():
                info = self.agents.pop(jid, None)
                if info is None:
                    continue
                self.load[info.target] = self.load.get(info.target, 1) - 1
                t_rm = round(self._now(), 3)
                self.last_exit_t[info.target] = t_rm
                self.squeezed.discard(jid)
                if self.exits[info.target].kind == "stair":
                    self.out.stair_arrivals.append((t_rm, info.gid, info.target))
                else:
                    self.out.exit_times.append((t_rm, info.gid, info.target))
            if self._now() >= next_frame - 1e-9:
                self.t = self._now()
                self.steps = [s for s in self.steps if not s(self)]
                for sc in self.scripts:
                    sc.tick(self)
                self._due_arrivals()
                self._doorway_capture()
                if self.t >= self._next_clog_check:
                    self._unclog()
                    self._next_clog_check = self.t + 1.0
                if self.t >= self._next_stuck_check:
                    self._unstick()
                    self._next_stuck_check = self.t + 5.0
                self._record()
                next_frame += self.frame_dt
                progress(self.floor_id, self.t, len(self.agents))
        if self.unstuck:
            self.out.event_log.append(
                {
                    "type": "unstuck",
                    "t_s": round(self.t, 1),
                    "people": self.unstuck,
                    "sidesteps": self.sidesteps,
                    "floor_id": self.floor_id,
                }
            )
        self.out.trapped = sum(1 for a in self.agents.values() if a.kind == "trapped")
        if self.clogs:
            doors = sorted({c["exit_id"] for c in self.clogs})
            self.note(
                f"Clogging at {', '.join(doors)}: people squeezed through ({len(self.clogs)} times)"
            )
            self.out.event_log.extend({"type": "clog", **c} for c in self.clogs)
        if self.rejected:
            self.note(
                f"{self.rejected} people could not be placed on {self.floor_id} "
                "(too close to a wall) and were left out"
            )
            self.out.pending += self.rejected
        if self.checkpoint_at_s is not None and self.checkpoint_t is None:
            self.note(f"No checkpoint written: the run ended before {self.checkpoint_at_s:g} s")
        self.out.sim_time = round(self._now(), 2)
        self.out.remaining = len(self.agents)
        self.out.pending += len(self.arrivals) + len(self.arrival_queue)
        return self.out


def stair_schedule(
    arrivals: list[tuple[float, int, str]],
    venue: dict[str, Any],
    settings: dict[str, Any],
    slow: dict[int, float] | None = None,
    counterflow: dict[str, float] | None = None,
) -> list[tuple[float, int, str]]:
    """FIFO entry per stair: at most width x flow people per s step on, each then takes
    length / speed to reach the bottom.

    `slow` (gid -> level speed) scales a slower walker's stair speed by speed / mean walking
    speed; `counterflow` (stair id -> time) halves a stair's flow from that time (a group
    climbing against the crowd, e.g. firefighters). With neither, the leaving times equal the
    plain FIFO queue max(t + length / speed, previous + headway).
    """
    stairs = {s["id"]: s for s in venue.get("stairs", [])}
    speed = float(settings.get("stair_speed", 0.6))
    flow = float(settings.get("stair_flow", 1.0))
    mean = float(settings.get("walk_speed_mean", 1.34))
    slow = slow or {}
    counterflow = counterflow or {}
    out: list[tuple[float, int, str]] = []
    last: dict[str, float] = {}
    for t, gid, sid in sorted(arrivals):
        s = stairs[sid]
        headway = 1.0 / max(flow * float(s["width_m"]), 0.05)
        enter = max(t, last.get(sid, -math.inf) + headway)
        cf = counterflow.get(sid)
        if cf is not None and enter >= cf:
            enter = max(t, last.get(sid, -math.inf) + headway / COUNTERFLOW_STAIR_FACTOR)
        last[sid] = enter
        ratio = min(1.0, slow[gid] / mean) if gid in slow else 1.0
        out.append((round(enter + float(s["length_m"]) / (speed * ratio), 3), gid, sid))
    return out


def run(
    work: Path,
    request: dict[str, Any],
    venue: dict[str, Any],
    events: list[dict[str, Any]],
    plan: dict[str, Any],
    settings: dict[str, Any],
    base_venue: dict[str, Any] | None,
) -> dict[str, Any]:
    """Run every floor (each before the floors its stairs lead to) and return raw outputs."""
    started = time.monotonic()
    deadline = started + float(request.get("max_wall_s", 240))
    max_sim_s = float(request.get("max_sim_s", 900))
    seed = int(request.get("seed", 42))
    floors = floor_run_order(venue)
    floor_of: dict[str, str] = {}
    for f in venue["floors"]:
        floor_of[f["floor_id"]] = f["floor_id"]
        for coll in ("exits", "zones"):
            for item in f.get(coll, []):
                floor_of[item["id"]] = f["floor_id"]
    stair_ids = {s["id"] for s in venue.get("stairs", [])}
    for s in venue.get("stairs", []):
        floor_of[s["id"]] = s["from_floor"]  # a stair is a way out of its upper floor
    stair_cf = {}
    for ev in events:
        if ev.get("type") == "counterflow" and ev.get("exit_id") in stair_ids:
            sid = str(ev["exit_id"])
            stair_cf[sid] = min(stair_cf.get(sid, math.inf), float(ev.get("at_s", 0.0)))
    slow: dict[int, float] = {}
    kinds: dict[int, str] = {}
    base_floors = {f["floor_id"]: f for f in (base_venue or {}).get("floors", [])}
    progress_path = work / "progress.json"
    last_write = [0.0]
    total = sum(int(z["people"]) for f in venue["floors"] for z in f.get("zones", []))

    def progress(floor_id: str, t: float, remaining: int) -> None:
        now = time.monotonic()
        if now - last_write[0] < 1.0:
            return
        last_write[0] = now
        progress_path.write_text(
            json.dumps(
                {
                    "floor_id": floor_id,
                    "sim_time_s": round(t, 1),
                    "agents_remaining": remaining,
                    "agents_total": total,
                    "wall_s": round(now - started, 1),
                }
            )
        )

    checkpoint_at = request.get("checkpoint_at_s")
    resume_state: dict[str, Any] | None = None
    rewind_note: str | None = None
    if (checkpoint_at is not None or request.get("resume")) and len(venue["floors"]) > 1:
        rewind_note = REWIND_SINGLE_FLOOR
        checkpoint_at = None
    elif request.get("resume"):
        cp_path = work / "checkpoint.json"
        if cp_path.exists():
            resume_state = json.loads(cp_path.read_text())
        else:
            rewind_note = "No checkpoint.json to rewind to: the run started from the beginning"
    rewind: dict[str, float] = {}
    gids = [1]
    outputs: list[FloorOutput] = []
    pending_arrivals: dict[str, list[tuple[float, int, str]]] = {}
    for idx, f in enumerate(floors):
        fid = f["floor_id"]
        floor_events = []
        for ev in events:
            ref = next((ev[k] for k in FLOOR_KEYS if ev.get(k)), None)
            if ref is None or floor_of.get(ref) == fid:
                floor_events.append(ev)
        fr = FloorRun(
            f,
            venue,
            settings,
            plan,
            floor_events,
            seed=seed + idx * 7919,
            gids=gids,
            arrivals=pending_arrivals.get(fid, []),
            base_floor=None if resume_state else base_floors.get(fid),
            intervention_at_s=None if resume_state else request.get("intervention_at_s"),
            checkpoint_at_s=float(checkpoint_at) if checkpoint_at is not None else None,
            checkpoint_path=work / "checkpoint.json",
            resume_state=resume_state,
            slow=slow,
            kinds=kinds,
        )
        out = fr.run(max_sim_s, deadline, progress)
        if rewind_note:
            out.notes.insert(0, rewind_note)
            rewind_note = None
        outputs.append(out)
        if fr.checkpoint_t is not None:
            rewind["checkpoint_t_s"] = round(fr.checkpoint_t, 2)
        if resume_state is not None:
            rewind["resumed_from_s"] = round(fr.t0, 2)
        if out.stair_arrivals:
            sched = stair_schedule(out.stair_arrivals, venue, settings, slow, stair_cf)
            stairs = {s["id"]: s for s in venue.get("stairs", [])}
            for t, gid, sid in sched:
                pending_arrivals.setdefault(stairs[sid]["to_floor"], []).append((t, gid, sid))
        if out.status == "timeout":
            break
    # everyone actually created (initial people, surges, counterflow, stair transfers count once),
    # plus people who were never created because no exit was open: they did not get out
    return {
        "outputs": outputs,
        "wall_s": time.monotonic() - started,
        "people_total": gids[0] - 1 + sum(o.no_exit for o in outputs),
        "people_planned": total,
        "rewind": rewind,
        "kinds": kinds,
    }
