"""Tier 1 instant estimate (section 10.5): hydraulic exit model, no simulation.

1. Walking distances: Dijkstra on a grid over the walkable space (edges may not cross
   walls), cached per layout.
2. Exit choice: people are routed zone → (stair →) exit with a min-cost flow; the total
   evacuation time T is the smallest horizon for which every exit and stair can pass its
   load (capacity = SPECIFIC_FLOW × width, stairs STAIR_FLOW × width).
3. Queues: fluid queue per exit, departures D(t) = min_s≤t [A(s) + c·(t − s)].
4. Density near a queue (screening formula, see docs/ASSUMPTIONS.md):
   D = D_cap + (D_jam − D_cap)·(1 − e^(−Q_max/Q0)), D_cap = 1.9, D_jam = 5.4, Q0 = 150.
"""

from __future__ import annotations

import itertools
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from api.core.extensions import Registry, T1Exit, T1Group, Tier1State
from api.core.extensions import geometry as geo
from api.core.venue_ops import venue_hash
from api.models import Hotspot, PerExit, RunMetrics, RunResult, ScenarioEventIn, Stair, Venue

D_CAP = 1.9  # people/m² at maximum specific flow (SFPE fundamental diagram)
D_JAM = 5.4  # jam density (Weidmann 1993)
Q0 = 150.0  # queue size (people) at which density approaches jam (calibrated on Tier 3)
HORIZON_S = 7200
FORMULA = (
    "T_exit = walk time + queue; capacity = specific flow × width; "
    "queue density D = 1.9 + 3.5·(1 − e^(−Q/150))"
)


@dataclass
class FloorGrid:
    """Distance fields (metres) from every exit/stair source on one floor."""

    res: float
    x0: float
    y0: float
    nx: int
    ny: int
    free_idx: np.ndarray  # flat indices of walkable cells
    dist: dict[str, np.ndarray]  # source id -> distance per walkable cell (inf if unreachable)
    centers: np.ndarray  # (n_free, 2)


_GRID_CACHE: OrderedDict[str, dict[str, FloorGrid]] = OrderedDict()


def _layout_key(venue: Venue) -> str:
    v = venue.model_copy(deep=True)
    for f in v.floors:
        for z in f.zones:
            z.people = 0
        for e in f.exits:
            e.blocked = False
    return venue_hash(v)


def _floor_grid(venue: Venue, floor_id: str) -> FloorGrid:
    f = venue.floor(floor_id)
    free = geo.free_space(f)
    minx, miny, maxx, maxy = free.bounds
    res = 0.5 if free.area < 2500 else 1.0
    nx_ = int(math.ceil((maxx - minx) / res)) + 1
    ny_ = int(math.ceil((maxy - miny) / res)) + 1
    xs = minx + (np.arange(nx_) + 0.5) * res
    ys = miny + (np.arange(ny_) + 0.5) * res
    gx, gy = np.meshgrid(xs, ys)
    shapely.prepare(free)
    walk = shapely.contains_xy(free, gx.ravel(), gy.ravel())
    idx = np.flatnonzero(walk)
    pos = -np.ones(nx_ * ny_, dtype=np.int64)
    pos[idx] = np.arange(len(idx))
    centers = np.column_stack([gx.ravel()[idx], gy.ravel()[idx]])
    rows, cols, wts = [], [], []
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        r = idx // nx_
        c = idx % nx_
        r2, c2 = r + dy, c + dx
        ok = (r2 >= 0) & (r2 < ny_) & (c2 < nx_)
        a = idx[ok]
        b = (r2 * nx_ + c2)[ok]
        okb = walk[b]
        a, b = a[okb], b[okb]
        lines = shapely.linestrings(
            np.stack(
                [
                    np.column_stack([gx.ravel()[a], gy.ravel()[a]]),
                    np.column_stack([gx.ravel()[b], gy.ravel()[b]]),
                ],
                axis=1,
            )
        )
        inside = shapely.covers(free, lines)
        a, b = a[inside], b[inside]
        w = res * math.hypot(dx, dy)
        rows.append(pos[a])
        cols.append(pos[b])
        wts.append(np.full(len(a), w))
    n = len(idx)
    graph = coo_matrix(
        (np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    ).tocsr()
    sources: dict[str, Any] = {e.id: geo.to_polygon(e.polygon) for e in f.exits}
    for s in venue.stairs:
        if s.from_floor == floor_id:
            sources[s.id] = geo.to_polygon(s.top_polygon)
    dist: dict[str, np.ndarray] = {}
    for sid, poly in sources.items():
        near = shapely.distance(poly, shapely.points(centers)) <= res * 1.1
        src = np.flatnonzero(near)
        if len(src) == 0:
            src = np.asarray(
                [int(np.argmin(shapely.distance(poly, shapely.points(centers))))], dtype=np.intp
            )
        d = dijkstra(graph, directed=False, indices=src, min_only=True)
        dist[sid] = np.asarray(d, dtype=np.float64)
    return FloorGrid(
        res=res, x0=minx, y0=miny, nx=nx_, ny=ny_, free_idx=idx, dist=dist, centers=centers
    )


def floor_grids(venue: Venue) -> dict[str, FloorGrid]:
    """Cached distance fields for every floor of a layout."""
    key = _layout_key(venue)
    if key in _GRID_CACHE:
        _GRID_CACHE.move_to_end(key)
        return _GRID_CACHE[key]
    grids = {f.floor_id: _floor_grid(venue, f.floor_id) for f in venue.floors}
    _GRID_CACHE[key] = grids
    while len(_GRID_CACHE) > 32:
        _GRID_CACHE.popitem(last=False)
    return grids


def _area_dist(
    grid: FloorGrid, poly_points: list[tuple[float, float]], source: str
) -> tuple[float, float, float]:
    """(min, mean, max) walking distance from cells inside a polygon to a source."""
    poly = geo.to_polygon(poly_points)
    inside = shapely.contains_xy(poly, grid.centers[:, 0], grid.centers[:, 1])
    d = (
        grid.dist[source][inside]
        if np.any(inside)
        else grid.dist[source][
            [int(np.argmin(shapely.distance(poly, shapely.points(grid.centers))))]
        ]
    )
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return (math.inf, math.inf, math.inf)
    return (float(d.min()), float(d.mean()), float(d.max()))


def build_state(venue: Venue, settings: Any) -> tuple[Tier1State, dict[str, Any]]:
    """Tier 1 input from the venue: exits, stairs and one group per zone."""
    grids = floor_grids(venue)
    exits: dict[str, T1Exit] = {}
    for f in venue.floors:
        for e in f.exits:
            cx, cy = geo.centroid(e.polygon)
            exits[e.id] = T1Exit(
                id=e.id,
                floor_id=f.floor_id,
                x=cx,
                y=cy,
                width_m=e.width_m,
                capacity_pps=settings.specific_flow * e.width_m,
                blocked_from_s=0.0 if e.blocked else None,
                label=e.label or e.id,
            )
    for s in venue.stairs:
        cx, cy = geo.centroid(s.top_polygon)
        exits[s.id] = T1Exit(
            id=s.id,
            floor_id=s.from_floor,
            x=cx,
            y=cy,
            width_m=s.width_m,
            capacity_pps=settings.stair_flow * s.width_m,
            kind="stair",
            leads_to_floor=s.to_floor,
            stair_delay_s=s.length_m / settings.stair_speed,
            label=s.id,
        )
    groups: dict[str, T1Group] = {}
    for f in venue.floors:
        for z in f.zones:
            if z.people <= 0:
                continue
            cx, cy = geo.centroid(z.polygon)
            groups[z.id] = T1Group(id=z.id, floor_id=f.floor_id, x=cx, y=cy, people=z.people)
    state = Tier1State(exits=exits, groups=groups, walk_speed_mps=settings.walk_speed_mean)
    return state, {"grids": grids}


@dataclass
class _Route:
    group: str
    exit: str
    stairs: tuple[str, ...]  # stair flights taken in order, top floor first
    stair_t: tuple[float, ...]  # first arrival at each of those stairs
    t_first: float
    t_mean: float
    t_last: float

    @property
    def via(self) -> str | None:
        return self.stairs[0] if self.stairs else None


@dataclass
class _Walk:
    """One group walking out: who, how fast, and where routes are collected."""

    group: str
    speed: float
    state: Tier1State
    grids: dict[str, FloorGrid]
    stairs: dict[str, Stair]
    out: list[_Route]


def _follow(
    w: _Walk,
    floor: str,
    area: list[Any],
    t: tuple[float, float, float],
    chain: tuple[str, ...],
    chain_t: tuple[float, ...],
    seen: frozenset[str],
) -> None:
    """Routes from `area` on `floor` to every exit, going down any chain of stairs."""
    grid = w.grids[floor]
    v = w.speed
    for ex in w.state.exits.values():
        if ex.floor_id != floor or ex.id not in grid.dist:
            continue
        dmin, dmean, dmax = _area_dist(grid, area, ex.id)
        if not math.isfinite(dmean):
            continue
        if chain:  # from the zone the spread of distances matters; from a stair landing not
            dmin = dmax = dmean
        a, m, b = t[0] + dmin / v, t[1] + dmean / v, t[2] + dmax / v
        if ex.kind == "exit":
            w.out.append(_Route(w.group, ex.id, chain, chain_t, a, m, b))
            continue
        st = w.stairs[ex.id]
        if st.to_floor in seen or st.to_floor not in w.grids:
            continue
        d = ex.stair_delay_s
        _follow(
            w,
            st.to_floor,
            st.bottom_polygon,
            (a + d, m + d, b + d),
            (*chain, ex.id),
            (*chain_t, a),
            seen | {st.to_floor},
        )


def _routes(venue: Venue, state: Tier1State, grids: dict[str, FloorGrid]) -> list[_Route]:
    zones = {z.id: (f.floor_id, z.polygon) for f in venue.floors for z in f.zones}
    stairs = {s.id: s for s in venue.stairs}
    out: list[_Route] = []
    for g in state.groups.values():
        zid = g.id.split(":")[1] if g.id.startswith("surge:") else g.id
        if zid not in zones:
            continue
        floor_id, poly = zones[zid]
        v = state.walk_speed_mps * state.global_speed_factor * g.speed_factor
        t0 = g.release_s
        walk = _Walk(g.id, v, state, grids, stairs, out)
        _follow(walk, floor_id, poly, (t0, t0, t0), (), (), frozenset({floor_id}))
    return out


def _close(ex: T1Exit, horizon: float) -> float:
    return horizon if ex.blocked_from_s is None else min(horizon, ex.blocked_from_s)


def _network(state: Tier1State, routes: list[_Route], horizon: float) -> nx.DiGraph:
    g = nx.DiGraph()
    for grp in state.groups.values():
        g.add_edge("S", f"g:{grp.id}", capacity=grp.people, weight=0)
    first: dict[str, float] = {}
    for r in routes:
        first[r.exit] = min(first.get(r.exit, math.inf), r.t_first)
        for sid, t_at in zip(r.stairs, r.stair_t, strict=True):
            first[sid] = min(first.get(sid, math.inf), t_at)
    for r in routes:
        ex = state.exits[r.exit]
        if r.t_first >= _close(ex, horizon):
            continue
        w = int(round(r.t_mean))
        if not r.stairs:
            g.add_edge(f"g:{r.group}", f"e:{r.exit}", capacity=10**9, weight=w)
            continue
        if any(
            t_at >= _close(state.exits[sid], horizon)
            for sid, t_at in zip(r.stairs, r.stair_t, strict=True)
        ):
            continue
        g.add_edge(f"g:{r.group}", f"si:{r.stairs[0]}", capacity=10**9, weight=0)
        for upper, lower in itertools.pairwise(r.stairs):
            g.add_edge(f"so:{upper}", f"si:{lower}", capacity=10**9, weight=0)
        g.add_edge(f"so:{r.stairs[-1]}", f"e:{r.exit}", capacity=10**9, weight=w)
    for ex in state.exits.values():
        span = _close(ex, horizon) - first.get(ex.id, math.inf)
        cap = int(math.floor(max(span, 0.0) * ex.capacity_pps)) if math.isfinite(span) else 0
        if ex.kind == "stair":
            g.add_edge(f"si:{ex.id}", f"so:{ex.id}", capacity=cap, weight=0)
        else:
            g.add_edge(f"e:{ex.id}", "T", capacity=cap, weight=0)
    return g


def _maxflow(g: nx.DiGraph) -> int:
    if "S" not in g or "T" not in g:
        return 0
    return int(nx.maximum_flow_value(g, "S", "T"))


def _uniform_ramp(t: np.ndarray, a: float, b: float, n: float) -> np.ndarray:
    if b <= a + 1e-6:
        return np.where(t >= a, n, 0.0)
    return n * np.clip((t - a) / (b - a), 0.0, 1.0)


def run_tier1(
    venue: Venue,
    events: list[ScenarioEventIn],
    registry: Registry,
    settings: Any,
    run_id: str = "t1",
    attack_id: str | None = None,
    fix_id: str | None = None,
) -> RunResult:
    """Instant estimate for a venue under a list of scenario events."""
    t_start = time.perf_counter()
    state, ctx = build_state(venue, settings)
    for ev in sorted(events, key=lambda e: e.at_s):
        if not registry.has("ScenarioEvent", ev.type):
            state.notes.append(f"Event '{ev.type}' has no instant-estimate effect.")
            continue
        spec = registry.event(ev.type)
        spec.tier1_effect(state, spec.params_model.model_validate(ev.model_dump()))
    routes = _routes(venue, state, ctx["grids"])
    total = sum(g.people for g in state.groups.values())

    lo, hi = 1.0, float(HORIZON_S)
    reachable = _maxflow(_network(state, routes, hi))
    if reachable < total:
        state.notes.append(f"{total - reachable} people have no usable route to an open exit.")
    if reachable == 0:
        return _empty_result(run_id, venue, total, state.notes, attack_id, fix_id, t_start)
    while hi - lo > 1.0:
        mid = (lo + hi) / 2
        if _maxflow(_network(state, routes, mid)) >= reachable:
            hi = mid
        else:
            lo = mid
    net = _network(state, routes, math.ceil(hi))
    flow = nx.max_flow_min_cost(net, "S", "T")

    plan_groups: dict[str, dict[str, int]] = {}
    plan_stairs: dict[str, dict[str, int]] = {}
    route_by = {(r.group, r.exit, r.stairs): r for r in routes}
    loads: dict[str, list[tuple[_Route, float]]] = {}
    for grp in state.groups.values():
        node = f"g:{grp.id}"
        for nxt, f in flow.get(node, {}).items():
            if f <= 0:
                continue
            if nxt.startswith("e:"):
                eid = nxt[2:]
                r = route_by[(grp.id, eid, ())]
                loads.setdefault(eid, []).append((r, float(f)))
                plan_groups.setdefault(
                    grp.id.split(":")[1] if grp.id.startswith("surge:") else grp.id, {}
                ).setdefault(eid, 0)
                plan_groups[grp.id.split(":")[1] if grp.id.startswith("surge:") else grp.id][
                    eid
                ] += int(f)
            elif nxt.startswith("si:"):
                sid = nxt[3:]
                gk = grp.id.split(":")[1] if grp.id.startswith("surge:") else grp.id
                plan_groups.setdefault(gk, {}).setdefault(sid, 0)
                plan_groups[gk][sid] += int(f)
    # split stair flow onto the next stair or the exits below, in proportion to the stair's
    # outgoing flow, following chains of stairs down a multi-storey building
    stair_out: dict[str, dict[str, float]] = {}
    for st in [e for e in state.exits.values() if e.kind == "stair"]:
        out_edges = {k: float(v) for k, v in flow.get(f"so:{st.id}", {}).items() if v > 0}
        if sum(out_edges.values()) <= 0:
            continue
        stair_out[st.id] = out_edges
        plan_stairs[st.id] = {k.split(":", 1)[1]: int(v) for k, v in out_edges.items()}

    def descend(grp_id: str, chain: tuple[str, ...], amount: float) -> None:
        out_edges = stair_out.get(chain[-1], {})
        tot_out = sum(out_edges.values())
        for node, f_out in out_edges.items():
            share = amount * f_out / tot_out
            kind, target = node.split(":", 1)
            if kind == "e":
                via = route_by.get((grp_id, target, chain))
                if via is not None:
                    loads.setdefault(target, []).append((via, share))
            elif kind == "si" and target not in chain:
                descend(grp_id, (*chain, target), share)

    for grp in state.groups.values():
        for nxt, into in flow.get(f"g:{grp.id}", {}).items():
            if into > 0 and nxt.startswith("si:"):
                descend(grp.id, (nxt[3:],), float(into))

    t_axis = np.arange(0, HORIZON_S + 1, 1.0)
    evacuated = np.zeros_like(t_axis)
    per_exit: list[PerExit] = []
    hotspots: list[Hotspot] = []
    exit_info: dict[str, dict[str, float]] = {}
    peak_density = 0.0
    for ex in state.exits.values():
        if ex.kind == "stair":
            continue
        arrivals = np.zeros_like(t_axis)
        n_e = 0.0
        for r, f in loads.get(ex.id, []):
            arrivals += _uniform_ramp(t_axis, r.t_first, r.t_last, f)
            n_e += f
        if n_e <= 0:
            per_exit.append(PerExit(exit_id=ex.id, people=0, mean_flow_pps=0.0))
            continue
        c = ex.capacity_pps
        dep = np.minimum(arrivals, c * t_axis + np.minimum.accumulate(arrivals - c * t_axis))
        if ex.blocked_from_s is not None:
            cut = int(min(ex.blocked_from_s, HORIZON_S))
            dep[cut:] = dep[cut]
        evacuated += dep
        queue = arrivals - dep
        q_max = float(queue.max())
        t_qmax = float(t_axis[int(np.argmax(queue))])
        first = float(t_axis[np.argmax(dep > 0.5)]) if np.any(dep > 0.5) else None
        last = float(t_axis[np.argmax(dep >= dep.max() - 0.5)])
        rate = (n_e / max(last - (first or 0.0), 1.0)) if first is not None else 0.0
        per_exit.append(
            PerExit(
                exit_id=ex.id,
                people=int(round(n_e)),
                mean_flow_pps=round(min(rate, c), 3),
                first_s=first,
                last_s=round(last, 1),
            )
        )
        dens = _density_estimate(q_max, arrivals, ex, state.walk_speed_mps)
        peak_density = max(peak_density, dens)
        exit_info[ex.id] = {
            "capacity_pps": round(c, 3),
            "queue_max": round(q_max, 1),
            "wait_max_s": round(q_max / c, 1),
            "density_est": round(dens, 2),
        }
        if dens >= settings.density_warn_ppm2 or q_max >= 25:
            level = "danger" if dens >= settings.density_danger_ppm2 else "warning"
            hotspots.append(
                Hotspot(
                    floor_id=ex.floor_id,
                    x=ex.x,
                    y=ex.y,
                    peak_density_ppm2=round(dens, 2),
                    t_s=t_qmax,
                    level=level,
                    near=ex.id,
                )
            )
    hotspots.sort(key=lambda h: -h.peak_density_ppm2)
    p95 = tmax = None
    if total > 0:
        hit95 = np.flatnonzero(evacuated >= 0.95 * total - 1e-6)
        hit_all = np.flatnonzero(evacuated >= total - 0.5)
        p95 = float(t_axis[hit95[0]]) if len(hit95) else None
        tmax = float(t_axis[hit_all[0]]) if len(hit_all) else None
    not_evac = int(round(max(total - float(evacuated[-1]), 0.0)))
    # time above thresholds: how long any exit queue sits at the estimated density
    above_d = sum(
        info["wait_max_s"]
        for info in exit_info.values()
        if info["density_est"] >= settings.density_danger_ppm2
    )
    above_w = sum(
        info["wait_max_s"]
        for info in exit_info.values()
        if info["density_est"] >= settings.density_warn_ppm2
    )
    metrics = RunMetrics(
        evac_time_p95_s=p95,
        evac_time_max_s=tmax,
        peak_density_ppm2=round(peak_density, 2),
        time_above_danger_s=round(above_d, 1),
        time_above_warning_s=round(above_w, 1),
        agents_total=total,
        agents_evacuated=total - not_evac,
        agents_not_evacuated=not_evac,
        per_exit=per_exit,
        extra={"solve_ms": round((time.perf_counter() - t_start) * 1000, 1)},
    )
    return RunResult(
        run_id=run_id,
        tier=1,
        status="ok" if not_evac == 0 else "partial",
        engine="tier1",
        metrics=metrics,
        hotspots=hotspots[:10],
        provider="local",
        venue_hash=venue_hash(venue),
        attack_id=attack_id,
        fix_id=fix_id,
        runtime_s=round(time.perf_counter() - t_start, 4),
        notes=state.notes,
        extensions={
            "plan": {"groups": plan_groups, "stairs": plan_stairs},
            "exits": exit_info,
            "formula": FORMULA,
            "horizon_s": math.ceil(hi),
        },
    )


def _density_estimate(q_max: float, arrivals: np.ndarray, ex: T1Exit, v: float) -> float:
    if q_max > 1.0:
        return D_CAP + (D_JAM - D_CAP) * (1.0 - math.exp(-q_max / Q0))
    rate = float(
        np.max(np.convolve(np.diff(arrivals, prepend=0.0), np.ones(10) / 10.0, mode="same"))
    )
    return min(D_CAP, rate / max(v * ex.width_m, 1e-6))


def _empty_result(
    run_id: str,
    venue: Venue,
    total: int,
    notes: list[str],
    attack_id: str | None,
    fix_id: str | None,
    t_start: float,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        tier=1,
        status="partial",
        engine="tier1",
        metrics=RunMetrics(agents_total=total, agents_not_evacuated=total),
        provider="local",
        venue_hash=venue_hash(venue),
        attack_id=attack_id,
        fix_id=fix_id,
        runtime_s=round(time.perf_counter() - t_start, 4),
        notes=notes,
        extensions={"plan": {"groups": {}, "stairs": {}}, "formula": FORMULA},
    )
