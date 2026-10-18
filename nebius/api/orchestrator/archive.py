"""Failure map: a quality-diversity archive for the red team (docs/RAINBOW.md).

MAP-Elites in the spirit of Rainbow Teaming (Samvelyan et al., NeurIPS 2024) and
RainbowPlus (2025): every attack has a descriptor, a cell = (hazard kind × where in the
venue), and each cell keeps its strongest attacks (up to `per_cell` elites). The red team is
asked to fill empty cells first, then to beat the weakest ones.

The difference from Rainbow Teaming: fitness is physics, not a language model. The severity
score is a formula over simulated metrics only (see `severity_score`), normalised so that
1.0 is the edge of a break as `break_reasons` in the session defines it, so the search cannot
talk its way past the judge. The model only proposes; the simulator scores.

Pure and deterministic: no I/O, no model calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from api.core.extensions import geometry as geo
from api.models import Attack, RunResult, Venue

# --- descriptor axis 1: hazard kind -------------------------------------------------------

# rows of the map, in display order (id, label)
KINDS: list[tuple[str, str]] = [
    ("exit_blocked", "Exit blocked"),
    ("surge", "Surge or late arrival"),
    ("counterflow", "Counterflow"),
    ("slowdown", "Slowdown, smoke or dark"),
    ("route_change", "Wrong route or one-way"),
    ("adaptive", "Adaptive scenario (code)"),
]
KIND_IDS = [k for k, _ in KINDS]
KIND_LABEL = dict(KINDS)

# event type -> hazard kind (deterministic; unknown types fall back to KEYWORDS)
EVENT_KIND: dict[str, str] = {
    "block_exit": "exit_blocked",
    "unblock_exit": "exit_blocked",
    "surge": "surge",
    "late_arrival": "surge",
    "staggered_release": "surge",
    "counterflow": "counterflow",
    "slowdown": "slowdown",
    "smoke": "slowdown",
    "darkness": "slowdown",
    "power_cut": "slowdown",
    "one_way": "route_change",
    "marshal_redirect": "route_change",
    "route_change": "route_change",
    "script": "adaptive",
}
KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("block", "close", "lock", "jam", "gate"), "exit_blocked"),
    (("surge", "arriv", "late", "rush", "influx", "stagger"), "surge"),
    (("counter", "against", "inflow"), "counterflow"),
    (("slow", "smoke", "dark", "power", "fire", "rain", "light"), "slowdown"),
    (("route", "redirect", "one_way", "detour", "sign", "marshal"), "route_change"),
]
# when an attack mixes events, the most specific failure names the cell
PRECEDENCE = ["adaptive", "exit_blocked", "counterflow", "route_change", "surge", "slowdown"]
# what a kind needs in a region to be possible there ("any" = exits or zones)
NEEDS: dict[str, Literal["exit", "zone", "any"]] = {
    "exit_blocked": "exit",
    "counterflow": "exit",
    "route_change": "exit",
    "surge": "zone",
    "slowdown": "zone",
    "adaptive": "any",
}
# the menu event that stages each kind (named in the red-team prompt)
KIND_EVENT = {
    "exit_blocked": "block_exit",
    "surge": "surge",
    "counterflow": "counterflow",
    "slowdown": "slowdown",
    "route_change": "marshal_redirect",
    "adaptive": "script",
}
# kinds that may hit the whole venue at once (no exit or zone named)
GLOBAL_KINDS = {"slowdown", "adaptive"}
# reference fields of an event, in the order that names its target
REF_FIELDS = ("exit_id", "to_exit_id", "zone_id", "target_zone_id", "from_exit_id")


def kind_of(event_type: str) -> str:
    """Hazard kind of one event type (unknown types by keyword, else adaptive)."""
    if event_type in EVENT_KIND:
        return EVENT_KIND[event_type]
    low = event_type.lower()
    for words, kind in KEYWORDS:
        if any(w in low for w in words):
            return kind
    return "adaptive"


# --- descriptor axis 2: where -------------------------------------------------------------

EVERYWHERE = "all"
MAX_REGIONS = 4


@dataclass(frozen=True)
class Region:
    """A column of the map: a floor, an exit's catchment, or a side of the venue."""

    id: str
    label: str
    exits: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()

    def has(self, need: str) -> bool:
        if need == "exit":
            return bool(self.exits)
        if need == "zone":
            return bool(self.zones)
        return bool(self.exits or self.zones)


def _side(cx: float, cy: float, bounds: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = bounds
    hw, hh = max((x1 - x0) / 2, 1e-6), max((y1 - y0) / 2, 1e-6)
    dx, dy = (cx - (x0 + x1) / 2) / hw, (cy - (y0 + y1) / 2) / hh
    if abs(dx) >= abs(dy):
        return "east" if dx >= 0 else "west"
    return "north" if dy >= 0 else "south"


def regions(venue: Venue) -> list[Region]:
    """At most four regions, without the whole-venue column.

    Several floors: one region per floor (floors grouped by height when there are more than
    four). One floor with one to four exits: one region per exit, holding the zones nearest to
    it. Otherwise: the west, east, north and south sides of the floor that hold something.
    """
    if len(venue.floors) > 1:
        floors = sorted(venue.floors, key=lambda f: f.elevation_m)
        groups: list[list[Any]] = [[] for _ in range(min(MAX_REGIONS, len(floors)))]
        for i, f in enumerate(floors):
            groups[i * len(groups) // len(floors)].append(f)
        out = []
        for g in groups:
            names = [f.name or f.floor_id for f in g]
            out.append(
                Region(
                    id="floor:" + "+".join(f.floor_id for f in g),
                    label=names[0] if len(names) == 1 else f"{names[0]} to {names[-1]}",
                    exits=tuple(e.id for f in g for e in f.exits),
                    zones=tuple(z.id for f in g for z in f.zones),
                )
            )
        return out
    f = venue.floors[0]
    if 1 <= len(f.exits) <= MAX_REGIONS:
        near: dict[str, list[str]] = {e.id: [] for e in f.exits}
        for z in f.zones:
            zx, zy = geo.centroid(z.polygon)
            best = min(f.exits, key=lambda e: geo.distance_to(e.polygon, zx, zy))
            near[best.id].append(z.id)
        return [
            Region(
                id=f"near:{e.id}",
                label=f"Near {e.label or e.id}",
                exits=(e.id,),
                zones=tuple(near[e.id]),
            )
            for e in f.exits
        ]
    bounds = geo.to_polygon(f.walkable).bounds
    sides: dict[str, tuple[list[str], list[str]]] = {
        s: ([], []) for s in ("west", "east", "north", "south")
    }
    for e in f.exits:
        sides[_side(*geo.centroid(e.polygon), bounds)][0].append(e.id)
    for z in f.zones:
        sides[_side(*geo.centroid(z.polygon), bounds)][1].append(z.id)
    return [
        Region(id=f"side:{s}", label=f"{s.capitalize()} side", exits=tuple(ex), zones=tuple(zs))
        for s, (ex, zs) in sides.items()
        if ex or zs
    ]


# --- fitness: physics, not a model ---------------------------------------------------------


@dataclass(frozen=True)
class BreakRule:
    """The thresholds of `break_reasons` (session.py); the score mirrors them exactly."""

    danger_ppm2: float
    min_s: float
    target_s: float | None
    safety_factor: float = 1.5


SEVERITY_CAP = 3.0  # one extreme metric must not swamp the QD-score
SOFT_DENSITY = 0.9  # peak density alone (no time above danger) never reaches a break
DANGER_SCALE_S = 300.0  # danger time that scores 2.0 when the venue has no evacuation target
INSIDE_SCALE = 0.1  # 10 % of the crowd still inside scores 2.0
TRAPPED_SCALE = 0.1  # 10 % of the crowd trapped scores 2.0
SEVERITY_FORMULA = (
    "severity = the largest of: RSET × safety factor / target; time above danger (1 at the "
    "minimum danger time, 2 at the evacuation target); people still inside (1 just past the "
    "tolerance, 2 at 10 % of the crowd); trapped people (1 for one, 2 at 10 %); for partial "
    "runs, share not out / 0.5; and 0.9 × peak density / danger density (at most 0.9). Each "
    "part is capped at 3. Severity ≥ 1 means the run breaks the plan"
)


def _graded(x: float, threshold: float, anchor: float) -> float:
    """x / threshold below the threshold; above it 1 at the threshold and 2 at `anchor`."""
    if x < threshold or anchor <= threshold:
        return x / threshold if threshold > 0 else (1.0 if x > 0 else 0.0)
    return 1.0 + (x - threshold) / (anchor - threshold)


def severity_score(r: RunResult, rule: BreakRule) -> tuple[float, dict[str, float]]:
    """Severity of a run from its simulated metrics only, and its parts.

    Each part is 1.0 at the threshold of the matching rule in `break_reasons`, so a run breaks
    the plan exactly when its score is at least 1.0 (at the evacuation-time threshold the
    break needs a strict excess, so exactly 1.0 there is the edge). Above a threshold a part
    grows linearly to 2.0 at "twice as bad" (see SEVERITY_FORMULA). Failed runs score 0.
    """
    if r.status in ("failed", "timeout", "cancelled"):
        return 0.0, {}
    m = r.metrics
    people = max(m.agents_total, 1)
    parts: dict[str, float] = {}
    rset = (
        m.evac_time_p95_s if m.evac_time_p95_s is not None else m.extra.get("rset_extrapolated_s")
    )
    if rule.target_s and rset is not None:
        parts["evacuation"] = float(rset) * rule.safety_factor / rule.target_s
    min_s = max(rule.min_s, 1e-9)
    parts["danger_time"] = _graded(
        m.time_above_danger_s, min_s, max(rule.target_s or DANGER_SCALE_S, min_s + 1)
    )
    trapped = int(m.extra.get("trapped", 0))
    if trapped:
        parts["trapped"] = 1.0 + (trapped - 1) / max(TRAPPED_SCALE * people - 1, 1)
    tol = max(5, round(m.agents_total * 0.005))
    if r.tier != 2:
        parts["people_inside"] = _graded(
            m.agents_not_evacuated, tol + 1, max(INSIDE_SCALE * people, tol + 2)
        )
    elif m.agents_not_evacuated > tol and m.evac_time_p95_s is None:
        frac = m.extra.get("evacuated_fraction")
        if frac is not None:
            parts["partial"] = (1.0 - float(frac)) / 0.5
    if rule.danger_ppm2 > 0:
        parts["density"] = SOFT_DENSITY * min(1.0, m.peak_density_ppm2 / rule.danger_ppm2)
    parts = {k: round(min(SEVERITY_CAP, max(0.0, v)), 3) for k, v in parts.items()}
    return (max(parts.values()) if parts else 0.0), parts


# --- the archive ---------------------------------------------------------------------------

Cell = tuple[str, str]  # (kind, where)


@dataclass
class Elite:
    """One attack kept in a cell, with the numbers that earned its place."""

    attack_id: str
    title: str
    run_id: str
    severity: float
    is_break: bool
    round: int
    metrics: dict[str, Any] = field(default_factory=dict)
    parts: dict[str, float] = field(default_factory=dict)
    basis: str | None = None
    generated_by: str = "ai"
    fixed_by: str | None = None
    severity_after: float | None = None
    after_run_id: str | None = None

    @property
    def current(self) -> float:
        """Severity on the plan as it stands (after a kept fix, its re-measured severity)."""
        return self.severity_after if self.severity_after is not None else self.severity

    def to_json(self) -> dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "title": self.title,
            "run_id": self.run_id,
            "severity": self.severity,
            "is_break": self.is_break,
            "round": self.round,
            "metrics": self.metrics,
            "parts": self.parts,
            "basis": self.basis,
            "generated_by": self.generated_by,
            "fixed_by": self.fixed_by,
            "severity_after": self.severity_after,
            "after_run_id": self.after_run_id,
        }


Outcome = Literal["new_cell", "added", "replaced", "kept_out", "off_map", "fixed"]


@dataclass(frozen=True)
class Insert:
    """What one insertion did to the map."""

    outcome: Outcome
    cell: Cell | None
    replaced: str | None = None


def refs_of(event: dict[str, Any]) -> list[str]:
    return [v for k in REF_FIELDS if isinstance(v := event.get(k), str) and v]


class Archive:
    """MAP-Elites grid over (hazard kind × where) with up to `per_cell` elites per cell."""

    def __init__(self, venue: Venue, per_cell: int = 2) -> None:
        self.per_cell = per_cell
        self.regions = regions(venue)
        self.where: dict[str, Region] = {r.id: r for r in self.regions}
        self.everywhere = Region(
            id=EVERYWHERE,
            label="Whole venue",
            exits=tuple(e.id for f in venue.floors for e in f.exits),
            zones=tuple(z.id for f in venue.floors for z in f.zones),
        )
        self.venue = venue
        self.region_of: dict[str, str] = {}
        for r in self.regions:
            for x in (*r.exits, *r.zones):
                self.region_of.setdefault(x, r.id)
        self.valid: list[Cell] = [
            (k, r.id) for k in KIND_IDS for r in self.regions if r.has(NEEDS[k])
        ] + [(k, EVERYWHERE) for k in KIND_IDS if k in GLOBAL_KINDS]
        self.valid.sort(key=lambda c: (KIND_IDS.index(c[0]), self._col(c[1])))
        self.cells: dict[Cell, list[Elite]] = {c: [] for c in self.valid}
        self.history: list[dict[str, Any]] = []
        self.aimed = 0
        self.hit = 0

    def learn(self, venue: Venue) -> None:
        """Place exits and zones a kept fix added (e.g. a new door) in the existing columns,
        so later attacks on them land on the map; the grid itself never changes."""
        for f in venue.floors:
            items = [(e.id, e.polygon) for e in f.exits] + [(z.id, z.polygon) for z in f.zones]
            for oid, poly in items:
                if oid in self.region_of:
                    continue
                where = self._region_for(f.floor_id, geo.centroid(poly))
                if where is not None:
                    self.region_of[oid] = where

    def _region_for(self, floor_id: str, at: tuple[float, float]) -> str | None:
        ids = [r.id for r in self.regions]
        if len(self.venue.floors) > 1:
            return next((i for i in ids if floor_id in i.split(":", 1)[1].split("+")), None)
        f = self.venue.floors[0]
        if ids and ids[0].startswith("near:"):
            near = min(f.exits, key=lambda e: geo.distance_to(e.polygon, *at))
            return f"near:{near.id}"
        side = f"side:{_side(*at, geo.to_polygon(f.walkable).bounds)}"
        return side if side in self.where else None

    def _col(self, where: str) -> int:
        ids = [r.id for r in self.regions] + [EVERYWHERE]
        return ids.index(where) if where in ids else len(ids)

    def region(self, where: str) -> Region:
        return self.everywhere if where == EVERYWHERE else self.where[where]

    # ---- descriptors
    def cell_of(self, attack: Attack) -> Cell | None:
        """The cell an attack belongs to (deterministic from its events), or None."""
        events = [e.model_dump() for e in attack.events]
        if not events:
            return None
        order = sorted(
            range(len(events)),
            key=lambda i: (PRECEDENCE.index(kind_of(str(events[i].get("type")))), i),
        )
        primary = events[order[0]]
        kind = kind_of(str(primary.get("type")))
        refs = refs_of(primary)
        if kind == "adaptive":
            code = str(primary.get("code", ""))
            refs = [x for x in self.region_of if re.search(rf"[\"']{re.escape(x)}[\"']", code)]
        elif not refs:
            refs = [r for e in events for r in refs_of(e)] if kind not in GLOBAL_KINDS else []
        if kind != "adaptive":
            refs = refs[:1]  # the event's target (e.g. where misdirection sends people)
        found = {self.region_of[x] for x in refs if x in self.region_of}
        where = found.pop() if len(found) == 1 else EVERYWHERE
        if (kind, where) in self.cells:
            return (kind, where)
        if (kind, EVERYWHERE) in self.cells:
            return (kind, EVERYWHERE)
        return None

    # ---- search state
    def filled(self) -> list[Cell]:
        return [c for c in self.valid if self.cells[c]]

    def empty(self) -> list[Cell]:
        return [c for c in self.valid if not self.cells[c]]

    def coverage(self) -> float:
        return round(len(self.filled()) / len(self.valid), 3) if self.valid else 0.0

    def qd_score(self) -> float:
        """Sum of elite severities as found (the search's progress; fixes do not lower it)."""
        return round(sum(e.severity for c in self.valid for e in self.cells[c]), 3)

    def best(self, cell: Cell) -> Elite | None:
        es = self.cells.get(cell) or []
        return max(es, key=lambda e: e.current) if es else None

    def targets(self, k: int, kinds: set[str] | None = None) -> list[Cell]:
        """Cells to aim the next attacks at: empty ones first, spread over rows and columns,
        then the weakest filled ones (lowest current severity)."""
        pool = [c for c in self.valid if kinds is None or c[0] in kinds]
        rows: dict[str, int] = {}
        cols: dict[str, int] = {}
        for c in pool:
            if self.cells[c]:
                rows[c[0]] = rows.get(c[0], 0) + 1
                cols[c[1]] = cols.get(c[1], 0) + 1
        empty = [c for c in pool if not self.cells[c]]
        out: list[Cell] = []
        while empty and len(out) < k:
            pick = min(
                empty,
                key=lambda c: (
                    rows.get(c[0], 0),
                    cols.get(c[1], 0),
                    KIND_IDS.index(c[0]),
                    self._col(c[1]),
                ),
            )
            empty.remove(pick)
            out.append(pick)
            rows[pick[0]] = rows.get(pick[0], 0) + 1
            cols[pick[1]] = cols.get(pick[1], 0) + 1
        weak = sorted(
            (c for c in pool if self.cells[c]),
            key=lambda c: (
                max(e.current for e in self.cells[c]),
                len(self.cells[c]),
                KIND_IDS.index(c[0]),
                self._col(c[1]),
            ),
        )
        out.extend(weak[: max(0, k - len(out))])
        return out

    def describe(self, cell: Cell, max_ids: int = 4) -> str:
        """One line for the red-team prompt: the gap, the event that stages it and the ids
        that reach it."""
        kind, where = cell
        r = self.region(where)
        bits = [f"event {KIND_EVENT[kind]}"] if kind != "adaptive" else []
        if where == EVERYWHERE and kind in GLOBAL_KINDS:
            bits.append("no exit or zone named: the whole venue")
        else:
            if NEEDS[kind] in ("exit", "any") and r.exits:
                bits.append("exits " + ", ".join(r.exits[:max_ids]))
            if NEEDS[kind] in ("zone", "any") and r.zones:
                bits.append("zones " + ", ".join(r.zones[:max_ids]))
        return f"{KIND_LABEL[kind]} · {r.label}: " + "; ".join(bits)

    def would_improve(self, cell: Cell | None, score: float) -> bool:
        """Whether a candidate with this (estimated) score would enter its cell."""
        if cell is None or cell not in self.cells:
            return False
        es = self.cells[cell]
        return len(es) < self.per_cell or score > min(e.current for e in es)

    def insert(self, elite: Elite, cell: Cell | None) -> Insert:
        """Higher severity wins; a cell keeps its `per_cell` strongest attacks (RainbowPlus)."""
        if cell is None or cell not in self.cells:
            return Insert("off_map", None)
        es = self.cells[cell]
        if any(e.attack_id == elite.attack_id for e in es):
            return Insert("kept_out", cell)
        if not es:
            es.append(elite)
            return Insert("new_cell", cell)
        if len(es) < self.per_cell:
            es.append(elite)
            es.sort(key=lambda e: -e.current)
            return Insert("added", cell)
        weakest = min(es, key=lambda e: e.current)
        if elite.current > weakest.current:
            es.remove(weakest)
            es.append(elite)
            es.sort(key=lambda e: -e.current)
            return Insert("replaced", cell, replaced=weakest.attack_id)
        return Insert("kept_out", cell)

    def mark_fixed(
        self, attack_id: str, fix_id: str, severity_after: float, run_id: str
    ) -> Cell | None:
        """A kept fix re-measured this elite on the improved plan."""
        for c in self.valid:
            for e in self.cells[c]:
                if e.attack_id == attack_id:
                    e.fixed_by, e.severity_after, e.after_run_id = fix_id, severity_after, run_id
                    self.cells[c].sort(key=lambda x: -x.current)
                    return c
        return None

    def contains(self, attack_id: str) -> bool:
        return any(e.attack_id == attack_id for c in self.valid for e in self.cells[c])

    def end_round(self, rnd: int) -> dict[str, Any]:
        point = {
            "round": rnd,
            "coverage": self.coverage(),
            "qd_score": self.qd_score(),
            "filled": len(self.filled()),
        }
        self.history = [h for h in self.history if h["round"] != rnd] + [point]
        return point

    def snapshot(self) -> dict[str, Any]:
        """The whole map as JSON (the `archive` session event and the session summary)."""
        breaks = sum(1 for c in self.valid if (b := self.best(c)) is not None and b.current >= 1)
        return {
            "method": "map_elites",
            "per_cell": self.per_cell,
            "kinds": [{"id": k, "label": label} for k, label in KINDS],
            "wheres": [
                {"id": r.id, "label": r.label, "exits": list(r.exits), "zones": list(r.zones)}
                for r in [*self.regions, self.everywhere]
            ],
            "cells": [
                {"kind": k, "where": w, "elites": [e.to_json() for e in self.cells[(k, w)]]}
                for k, w in self.valid
            ],
            "cells_total": len(self.valid),
            "filled": len(self.filled()),
            "coverage": self.coverage(),
            "qd_score": self.qd_score(),
            "open_breaks": breaks,
            "aim": {"targeted": self.aimed, "hit": self.hit},
            "history": list(self.history),
            "fitness": SEVERITY_FORMULA,
        }


def pick_candidates(
    candidates: list[tuple[Attack, Cell | None, float]],
    archive: Archive,
    k: int,
    aim: list[Cell] | None = None,
) -> list[int]:
    """Indices of the k candidates to simulate, in priority order: one per cell first; gaps
    the round aimed at (in aim order), then other gaps, then cells the estimate says they
    would enter, then the rest; within each, the highest estimate first."""
    aim = aim or []

    def tier(cell: Cell | None, score: float) -> tuple[int, int]:
        if cell is not None and cell in archive.cells and not archive.cells[cell]:
            return (0, aim.index(cell)) if cell in aim else (1, 0)
        return (2, 0) if archive.would_improve(cell, score) else (3, 0)

    order = sorted(
        range(len(candidates)),
        key=lambda i: (tier(candidates[i][1], candidates[i][2]), -candidates[i][2], i),
    )
    chosen: list[int] = []
    cells: set[Cell | None] = set()
    for i in order:
        c = candidates[i][1]
        if len(chosen) < k and (c is None or c not in cells):
            chosen.append(i)
            cells.add(c)
    for i in order:
        if len(chosen) < k and i not in chosen:
            chosen.append(i)
    return chosen
