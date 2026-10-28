"""Scenario catalogue: named what-ifs turned into concrete events for one venue.

Every entry picks its targets deterministically from the venue (the widest or busiest exit,
the busiest stairwell, the fire floor, the zone in front of the stage) and returns plain
scenario events (`block_exit`, `slowdown`, `counterflow`, ...) that the simulator and the
instant estimate already understand. "Busiest" uses the instant estimate's exit plan when one is
given, otherwise widths. Numbers that set a scenario's strength are listed in
docs/ASSUMPTIONS.md (section "Scenario library").
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from api.core.extensions import geometry as geo
from api.models import RunResult, ScenarioEventIn, Stair, Venue, Zone

Category = Literal["fire_smoke", "crowd", "weather", "access", "people", "operations"]
CATEGORY_LABELS: dict[str, str] = {
    "fire_smoke": "Fire and smoke",
    "crowd": "Crowd",
    "weather": "Weather",
    "access": "Access",
    "people": "People",
    "operations": "Operations",
}
# What a venue must have for a scenario to apply (all listed tags).
Tag = Literal[
    "indoor", "outdoor", "multi_storey", "has_stage", "multi_exit", "multi_stairwell", "multi_zone"
]

# Strength of each scenario (sources and reasoning in docs/ASSUMPTIONS.md).
RAIN_SPEED = 0.85
DARK_SPEED = 0.7
SMOKE_SPEED = 0.5
FAMILIES_SPEED = 0.75
# the walking-speed choices of the what-if lab and "Ask anything" (served with GET /settings)
SPEED_PRESETS: dict[str, float] = {
    "normal": 1.0,
    "rain": RAIN_SPEED,
    "families": FAMILIES_SPEED,
    "smoke": SMOKE_SPEED,
}
LATE_SURGE_SHARE = 0.25
LATE_SURGE_AT_S = 30.0
COUNTERFLOW_SHARE = 0.05
COUNTERFLOW_PEOPLE = (20, 400)
EXIT_LOST_AT_S = 60.0
PHASE_DELAY_S = 120.0
PHASE_MAX_DELAY_S = 360.0  # the last phase of a tall building starts within 6 minutes
FIREFIGHTERS_PER_FLOOR = 4
FIREFIGHTERS_AT_S = 60.0
LIFT_USER_SHARE = 0.05
WALKING_FRAME_SPEED = 0.57
MOBILITY_SHARE = 0.15
WHEELCHAIR_SPEED = 0.69
STAGGER_DELAY_S = 60.0
MARSHAL_AT_S = 20.0
MARSHAL_FRACTION = 0.5
STAIRWELL_LINK_M = 4.0
LEGACY_SWEEP = ("plan", "plus20", "gate", "rain", "rain_gate", "surge")


@dataclass(frozen=True)
class Stairwell:
    """Stair flights stacked on top of each other (one escape stair through the building)."""

    name: str
    flights: tuple[Stair, ...]  # top floor first
    width_m: float
    load: float = 0.0  # people the instant estimate sends down it


@dataclass
class VenueFacts:
    """What the catalogue needs to know about a venue, computed once."""

    venue: Venue
    tags: set[str]
    exits: list[tuple[str, str, str, float]]  # (id, name, floor_id, width) of open exits
    exit_load: dict[str, float]
    stairwells: list[Stairwell]
    floors: list[str]  # bottom to top
    floor_names: dict[str, str]
    zones: list[tuple[str, Zone]]  # (floor_id, zone)

    @property
    def total_people(self) -> int:
        return self.venue.total_people()

    def main_exit(self) -> tuple[str, str, str, float] | None:
        """The widest open exit (ties: the first listed); None with only one exit."""
        if len(self.exits) < 2:
            return None
        return max(self.exits, key=lambda e: e[3])

    def busiest_exit(self) -> tuple[str, str, str, float] | None:
        """The exit the instant estimate sends most people to (ties: widest, then id)."""
        if not self.exits:
            return None
        return max(self.exits, key=lambda e: (self.exit_load.get(e[0], 0.0), e[3], e[0]))

    def main_stairwell(self) -> Stairwell | None:
        """The stairwell carrying most people (ties: widest, then the most flights, name)."""
        if not self.stairwells:
            return None
        return max(self.stairwells, key=lambda s: (s.load, s.width_m, len(s.flights), s.name))

    def ground(self) -> str:
        """The street level: the highest floor at or below elevation 0 (basements lie below it);
        the lowest floor when every floor is raised."""
        elev = {f.floor_id: f.elevation_m for f in self.venue.floors}
        at_or_below = [f for f in self.floors if elev.get(f, 0.0) <= 0.01]
        return at_or_below[-1] if at_or_below else self.floors[0]

    def off_ground(self) -> list[str]:
        """Every floor but the street level: the storeys above and the basements below."""
        g = self.ground()
        return [f for f in self.floors if f != g]

    def fire_floor(self) -> str:
        """The most occupied floor off the street level (ties: the lowest); the ground floor in
        a single-storey building."""
        upper = self.off_ground() or self.floors[:1]
        people = {f: sum(z.people for fid, z in self.zones if fid == f) for f in upper}
        return max(upper, key=lambda f: (people[f], -self.floors.index(f)))

    def stage_zone(self) -> tuple[str, Zone] | None:
        """The occupied zone closest to the stage."""
        stages = [
            (f.floor_id, o.polygon)
            for f in self.venue.floors
            for o in f.obstacles
            if o.kind == "stage"
        ]
        cands = [(fid, z) for fid, z in self.zones if z.people > 0]
        if not stages or not cands:
            return None
        sf, spoly = stages[0]
        sx, sy = geo.centroid(spoly)

        def dist(item: tuple[str, Zone]) -> tuple[float, str]:
            zx, zy = geo.centroid(item[1].polygon)
            return (math.hypot(zx - sx, zy - sy) + (0 if item[0] == sf else 1e6), item[1].id)

        return min(cands, key=dist)

    def zone_name(self, z: Zone) -> str:
        return z.label or z.id


@dataclass
class Built:
    """A scenario made concrete for one venue."""

    events: list[ScenarioEventIn] = field(default_factory=list)
    scale: float = 1.0
    targets: list[str] = field(default_factory=list)  # what is affected, in plain words
    closed_exit: str | None = None  # name of a closed exit (sweep compatibility)


Builder = Callable[[VenueFacts], "Built | str"]  # a string says why it does not apply


@dataclass(frozen=True)
class ScenarioSpec:
    """One catalogue entry."""

    id: str
    title: str  # at most 5 words
    description: str  # at most 12 words
    icon: str  # lucide icon name
    category: Category
    applies_to: tuple[Tag, ...]
    build: Builder
    label: str | None = None  # sweep label kept from before the catalogue

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "category_label": CATEGORY_LABELS[self.category],
            "applies_to": list(self.applies_to),
        }


# --------------------------------------------------------------------------- venue facts


def _stair_name(stair_id: str) -> str:
    m = re.fullmatch(r"stairs?[_\- ]?([a-z0-9]+?)(?:_b?\d+)?", stair_id, flags=re.IGNORECASE)
    return f"Stair {m.group(1).upper()}" if m else stair_id


def _landing(stair: Stair, floor_id: str) -> tuple[float, float] | None:
    """Where a flight meets `floor_id` (its top or its bottom), or None if it does not."""
    if stair.from_floor == floor_id:
        return geo.centroid(stair.top_polygon)
    if stair.to_floor == floor_id:
        return geo.centroid(stair.bottom_polygon)
    return None


def _stairwells(venue: Venue, load: dict[str, float]) -> list[Stairwell]:
    """Flights grouped into stairwells: two flights are one core when they meet the same floor
    within STAIRWELL_LINK_M of each other, whichever way they go (a basement flight climbs to
    the street where the flights from the storeys above arrive)."""
    elev = {f.floor_id: f.elevation_m for f in venue.floors}
    flights = sorted(venue.stairs, key=lambda s: (-elev.get(s.from_floor, 0.0), s.id))
    parent = {s.id: s.id for s in flights}

    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(flights):
        for b in flights[i + 1 :]:
            for fl in {a.from_floor, a.to_floor} & {b.from_floor, b.to_floor}:
                pa, pb = _landing(a, fl), _landing(b, fl)
                if pa and pb and math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= STAIRWELL_LINK_M:
                    parent[root(a.id)] = root(b.id)
    groups: dict[str, list[Stair]] = {}
    for s in flights:  # flights keep their top-down order inside a stairwell
        groups.setdefault(root(s.id), []).append(s)
    out: list[Stairwell] = []
    for chain in groups.values():
        names = {_stair_name(f.id) for f in chain}
        name = names.pop() if len(names) == 1 else _stair_name(chain[0].id)
        out.append(
            Stairwell(
                name=name,
                flights=tuple(chain),
                width_m=min(f.width_m for f in chain),
                load=sum(load.get(f.id, 0.0) for f in chain),
            )
        )
    return out


def venue_facts(venue: Venue, baseline: RunResult | None = None) -> VenueFacts:
    """Facts about a venue; `baseline` (an instant estimate) tells which exits are busiest."""
    exit_load: dict[str, float] = {}
    stair_load: dict[str, float] = {}
    if baseline is not None:
        exit_load = {p.exit_id: float(p.people) for p in baseline.metrics.per_exit}
        plan = baseline.extensions.get("plan") or {}
        for sid, nxt in (plan.get("stairs") or {}).items():
            stair_load[sid] = float(sum(int(v) for v in nxt.values()))
    floors = sorted(venue.floors, key=lambda f: (f.elevation_m, f.floor_id))
    exits = [
        (e.id, e.label or e.id, f.floor_id, e.width_m)
        for f in venue.floors
        for e in f.exits
        if not e.blocked
    ]
    zones = [(f.floor_id, z) for f in venue.floors for z in f.zones]
    wells = _stairwells(venue, stair_load)
    tags: set[str] = {venue.mode}
    if len(venue.floors) > 1 and venue.stairs:
        tags.add("multi_storey")
    if any(o.kind == "stage" for f in venue.floors for o in f.obstacles):
        tags.add("has_stage")
    if len(exits) > 1:
        tags.add("multi_exit")
    if len(wells) > 1:
        tags.add("multi_stairwell")
    if sum(1 for _, z in zones if z.people > 0) > 1:
        tags.add("multi_zone")
    return VenueFacts(
        venue=venue,
        tags=tags,
        exits=exits,
        exit_load=exit_load,
        stairwells=wells,
        floors=[f.floor_id for f in floors],
        floor_names={f.floor_id: f.name or f.floor_id for f in venue.floors},
        zones=zones,
    )


# --------------------------------------------------------------------------- builders


def _ev(type_: str, **kw: Any) -> ScenarioEventIn:
    return ScenarioEventIn(type=type_, **kw)


def _plan(f: VenueFacts) -> Built:
    return Built(targets=["Nothing changed"])


def _plus(scale: float) -> Builder:
    def build(f: VenueFacts) -> Built:
        extra = round(f.total_people * (scale - 1))
        return Built(scale=scale, targets=[f"{extra:,} more people in every zone"])

    return build


def _slow_all(factor: float, why: str) -> Builder:
    def build(f: VenueFacts) -> Built:
        return Built(
            events=[_ev("slowdown", factor=factor, at_s=0)],
            targets=[f"{why}: everyone walks at {round(factor * 100)}% speed"],
        )

    return build


def _close_main(f: VenueFacts) -> Built | str:
    main = f.main_exit()
    if main is None:
        return "Only one exit: closing it would trap everyone."
    return Built(
        events=[_ev("block_exit", exit_id=main[0], at_s=0)],
        targets=[f"{main[1]} closed"],
        closed_exit=main[1],
    )


def _rain_gate(f: VenueFacts) -> Built | str:
    closed = _close_main(f)
    if isinstance(closed, str):
        return closed
    closed.events.append(_ev("slowdown", factor=RAIN_SPEED, at_s=0))
    closed.targets.append(f"Rain: everyone walks at {round(RAIN_SPEED * 100)}% speed")
    return closed


def _dark_surge(f: VenueFacts) -> Built:
    b = _plus(1.3)(f)
    assert isinstance(b, Built)
    b.events.append(_ev("slowdown", factor=DARK_SPEED, at_s=0))
    b.targets.append(f"In the dark: everyone walks at {round(DARK_SPEED * 100)}% speed")
    return b


def _stair_smoke(f: VenueFacts) -> Built | str:
    well = f.main_stairwell()
    if well is None or len(f.stairwells) < 2:
        return "Only one stairwell: losing it would trap everyone above the ground floor."
    return Built(
        events=[_ev("block_exit", exit_id=s.id, at_s=0) for s in well.flights],
        targets=[
            f"{well.name} blocked on every floor ({len(well.flights)} "
            f"flight{'s' if len(well.flights) != 1 else ''})"
        ],
    )


def _smoke_floor(f: VenueFacts) -> Built:
    fl = f.fire_floor()
    return Built(
        events=[_ev("slowdown", factor=SMOKE_SPEED, floor_id=fl, at_s=0)],
        targets=[f"Smoke on {f.floor_names[fl]}: walking at {round(SMOKE_SPEED * 100)}% speed"],
    )


def _phased(f: VenueFacts) -> Built | str:
    fire = f.fire_floor()
    i = f.floors.index(fire)
    first = {fire, *f.floors[i + 1 : i + 2]}
    events: list[ScenarioEventIn] = []
    later: list[str] = []
    for fl in f.floors:
        if fl in first:
            continue
        # one phase per floor of distance from the fire floor's group
        dist = min(abs(f.floors.index(fl) - f.floors.index(g)) for g in first)
        # capped: a tall building still starts its last phase within minutes (and within the
        # event's limit of 1,800 s)
        delay = min(PHASE_DELAY_S * dist, PHASE_MAX_DELAY_S)
        for fid, z in f.zones:
            if fid == fl and z.people > 0:
                events.append(_ev("staggered_release", zone_id=z.id, delay_s=delay, at_s=0))
        later.append(f"{f.floor_names[fl]} after {round(delay)} s")
    if not events:
        return "No floor to hold back: everyone is on the fire floor or the floor above."
    go = " and ".join(f.floor_names[x] for x in f.floors if x in first)
    return Built(events=events, targets=[f"{go} leave first", *later])


def _firefighters(f: VenueFacts) -> Built | str:
    well = f.main_stairwell()
    if well is None:
        return "No stairs to climb."
    elev = {fl.floor_id: fl.elevation_m for fl in f.venue.floors}
    fire = f.fire_floor()
    flights = [s for s in well.flights if elev[s.from_floor] <= elev[fire]]
    if not flights:
        return f"{well.name} does not reach the fire floor."
    events: list[ScenarioEventIn] = []
    for s in flights:
        zones = [z for fid, z in f.zones if fid == s.from_floor and z.people > 0]
        target = max(zones, key=lambda z: (z.people, z.id)).id if zones else None
        events.append(
            _ev(
                "counterflow",
                exit_id=s.id,
                people=FIREFIGHTERS_PER_FLOOR,
                target_zone_id=target,
                at_s=FIREFIGHTERS_AT_S,
            )
        )
    return Built(
        events=events,
        targets=[
            f"{len(flights) * FIREFIGHTERS_PER_FLOOR} firefighters up {well.name} from "
            f"{round(FIREFIGHTERS_AT_S)} s; its flow halves"
        ],
    )


def _lift_out(f: VenueFacts) -> Built | str:
    upper = f.off_ground()
    if not upper:
        return "Single storey: nobody needs a lift."
    return Built(
        events=[
            _ev(
                "mobility_share",
                share=LIFT_USER_SHARE,
                speed_mps=WALKING_FRAME_SPEED,
                floor_id=fl,
                at_s=0,
            )
            for fl in upper
        ],
        targets=[
            f"{round(LIFT_USER_SHARE * 100)}% of people off the street level take the stairs "
            f"at {WALKING_FRAME_SPEED} m/s"
        ],
    )


def _mobility(f: VenueFacts) -> Built:
    return Built(
        events=[_ev("mobility_share", share=MOBILITY_SHARE, speed_mps=WHEELCHAIR_SPEED, at_s=0)],
        targets=[f"{round(MOBILITY_SHARE * 100)}% of people move at {WHEELCHAIR_SPEED} m/s"],
    )


def _stage_surge(f: VenueFacts) -> Built | str:
    sz = f.stage_zone()
    if sz is None:
        return "No occupied zone near a stage."
    _, z = sz
    extra = max(10, round(z.people * LATE_SURGE_SHARE))
    return Built(
        events=[_ev("surge", zone_id=z.id, extra_people=extra, at_s=LATE_SURGE_AT_S)],
        targets=[f"{extra:,} latecomers join {f.zone_name(z)} at {round(LATE_SURGE_AT_S)} s"],
    )


def _counterflow_stage(f: VenueFacts) -> Built | str:
    sz, ex = f.stage_zone(), f.busiest_exit()
    if sz is None or ex is None:
        return "No stage zone or no exit to push in through."
    lo, hi = COUNTERFLOW_PEOPLE
    n = int(min(hi, max(lo, round(f.total_people * COUNTERFLOW_SHARE))))
    return Built(
        events=[_ev("counterflow", exit_id=ex[0], people=n, target_zone_id=sz[1].id, at_s=0)],
        targets=[f"{n:,} people push in at {ex[1]} toward {f.zone_name(sz[1])}"],
    )


def _exit_late(f: VenueFacts) -> Built | str:
    ex = f.busiest_exit()
    if ex is None or len(f.exits) < 2:
        return "Only one exit: closing it would trap everyone."
    return Built(
        events=[_ev("block_exit", exit_id=ex[0], at_s=EXIT_LOST_AT_S)],
        targets=[f"{ex[1]} closes at {round(EXIT_LOST_AT_S)} s"],
        closed_exit=ex[1],
    )


def _staggered(f: VenueFacts) -> Built | str:
    def way_out(fid: str, z: Zone) -> float:
        zx, zy = geo.centroid(z.polygon)
        pts = [
            geo.centroid(e.polygon)
            for fl in f.venue.floors
            if fl.floor_id == fid
            for e in fl.exits
            if not e.blocked
        ]
        pts += [geo.centroid(s.top_polygon) for s in f.venue.stairs if s.from_floor == fid]
        return min((math.hypot(zx - x, zy - y) for x, y in pts), default=math.inf)

    ranked = sorted(
        ((way_out(fid, z), z.id, z) for fid, z in f.zones if z.people > 0),
        key=lambda r: (r[0], r[1]),
    )
    held = ranked[len(ranked) // 2 :] if len(ranked) > 1 else []
    if not held:
        return "Only one occupied zone: nothing to stagger."
    return Built(
        events=[
            _ev("staggered_release", zone_id=z.id, delay_s=STAGGER_DELAY_S, at_s=0)
            for _, _, z in held
        ],
        targets=[
            f"{', '.join(f.zone_name(z) for _, _, z in held)} wait {round(STAGGER_DELAY_S)} s"
        ],
    )


def _marshals(f: VenueFacts) -> Built | str:
    ex = f.busiest_exit()
    if ex is None:
        return "No exit to steward."
    others = [e for e in f.exits if e[2] == ex[2] and e[0] != ex[0]]
    if not others:
        return "No second exit on the same floor to send people to."
    to = min(others, key=lambda e: (f.exit_load.get(e[0], 0.0) / max(e[3], 0.1), e[0]))
    return Built(
        events=[
            _ev(
                "marshal_redirect",
                from_exit_id=ex[0],
                to_exit_id=to[0],
                fraction=MARSHAL_FRACTION,
                at_s=MARSHAL_AT_S,
            )
        ],
        targets=[
            f"Stewards send {round(MARSHAL_FRACTION * 100)}% of {ex[1]}'s crowd to {to[1]} "
            f"at {round(MARSHAL_AT_S)} s"
        ],
    )


# --------------------------------------------------------------------------- the catalogue

CATALOGUE: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        "plan", "As planned", "The plan exactly as drawn.", "circle-check", "operations", (), _plan
    ),
    ScenarioSpec(
        "plus20",
        "20% over capacity",
        "Every zone holds a fifth more people.",
        "user-plus",
        "people",
        (),
        _plus(1.2),
        label="20% more people",
    ),
    ScenarioSpec(
        "gate",
        "Main exit closed",
        "The widest exit is shut from the start.",
        "door-closed-locked",
        "access",
        ("multi_exit",),
        _close_main,
    ),
    ScenarioSpec(
        "rain",
        "Heavy rain",
        "Wet ground slows everyone to 85% speed.",
        "cloud-rain",
        "weather",
        (),
        _slow_all(RAIN_SPEED, "Rain"),
        label="Rain: 85% walking speed",
    ),
    ScenarioSpec(
        "rain_gate",
        "Rain and main exit closed",
        "Wet ground and the widest exit shut.",
        "cloud-rain-wind",
        "weather",
        ("multi_exit",),
        _rain_gate,
    ),
    ScenarioSpec(
        "surge",
        "Late surge in the dark",
        "Thirty percent more people, walking at 70% speed.",
        "moon",
        "crowd",
        (),
        _dark_surge,
        label="Late surge in the dark: 30% more, 70% speed",
    ),
    ScenarioSpec(
        "stair_smoke",
        "Stairwell lost to smoke",
        "Smoke fills the busiest stairwell; people use the others.",
        "cloud-fog",
        "fire_smoke",
        ("multi_storey", "multi_stairwell"),
        _stair_smoke,
    ),
    ScenarioSpec(
        "smoke_floor",
        "Smoke on the fire floor",
        "Smoke halves walking speed on one floor.",
        "flame",
        "fire_smoke",
        ("indoor",),
        _smoke_floor,
    ),
    ScenarioSpec(
        "phased",
        "Phased evacuation",
        "Fire floor and floor above leave first; others wait.",
        "layers",
        "fire_smoke",
        ("multi_storey",),
        _phased,
    ),
    ScenarioSpec(
        "firefighters",
        "Firefighters climb the stairs",
        "Crews come up the main stair against the crowd.",
        "siren",
        "fire_smoke",
        ("multi_storey",),
        _firefighters,
    ),
    ScenarioSpec(
        "lift_out",
        "Lift out of service",
        "People who need the lift must use the stairs.",
        "arrow-up-down",
        "access",
        ("multi_storey",),
        _lift_out,
    ),
    ScenarioSpec(
        "mobility",
        "More mobility-impaired people",
        "One in seven people moves at wheelchair speed.",
        "accessibility",
        "people",
        (),
        _mobility,
    ),
    ScenarioSpec(
        "power_cut",
        "Night-time power cut",
        "Lights fail; everyone slows to 70% speed.",
        "zap-off",
        "operations",
        ("indoor",),
        _slow_all(DARK_SPEED, "Power cut"),
    ),
    ScenarioSpec(
        "stage_surge",
        "Late surge at the stage",
        "Latecomers pack the area in front of the stage.",
        "trending-up",
        "crowd",
        ("has_stage",),
        _stage_surge,
    ),
    ScenarioSpec(
        "counterflow_stage",
        "Counterflow toward the stage",
        "A group pushes in through the busiest exit.",
        "arrow-down-up",
        "crowd",
        ("has_stage",),
        _counterflow_stage,
    ),
    ScenarioSpec(
        "exit_late",
        "Exit blocked mid-evacuation",
        "The busiest exit closes after one minute.",
        "ban",
        "access",
        ("multi_exit",),
        _exit_late,
    ),
    ScenarioSpec(
        "staggered",
        "Staggered release",
        "Zones nearest an exit leave first; the rest wait.",
        "hourglass",
        "operations",
        ("multi_zone",),
        _staggered,
    ),
    ScenarioSpec(
        "marshals",
        "Stewards redirect the crowd",
        "Stewards send half the busiest exit's crowd elsewhere.",
        "megaphone",
        "operations",
        ("multi_exit",),
        _marshals,
    ),
)
BY_ID: dict[str, ScenarioSpec] = {s.id: s for s in CATALOGUE}


@dataclass
class Resolved:
    """A catalogue entry for one venue: applicable with events, or a reason it is not."""

    spec: ScenarioSpec
    built: Built | None
    reason: str | None = None

    @property
    def label(self) -> str:
        return self.spec.label or self.spec.title

    def public(self) -> dict[str, Any]:
        out = self.spec.public()
        if self.built is None:
            return {**out, "applicable": False, "reason": self.reason}
        return {
            **out,
            "applicable": True,
            "targets": self.built.targets,
            "people_scale": self.built.scale,
            "events": [e.model_dump() for e in self.built.events],
        }


def resolve(spec: ScenarioSpec, facts: VenueFacts) -> Resolved:
    """Make one entry concrete for a venue."""
    missing = [t for t in spec.applies_to if t not in facts.tags]
    if missing:
        return Resolved(spec, None, _why_not(missing[0]))
    built = spec.build(facts)
    if isinstance(built, str):
        return Resolved(spec, None, built)
    return Resolved(spec, built)


def _why_not(tag: str) -> str:
    return {
        "indoor": "Applies to indoor venues.",
        "outdoor": "Applies to open-air sites.",
        "multi_storey": "Applies to buildings with more than one floor.",
        "has_stage": "This venue has no stage.",
        "multi_exit": "Only one exit: closing it would trap everyone.",
        "multi_stairwell": (
            "Only one stairwell: losing it would trap everyone above the ground floor."
        ),
        "multi_zone": "Only one occupied zone.",
    }.get(tag, f"Needs {tag}.")


def catalogue_for(venue: Venue, baseline: RunResult | None = None) -> list[Resolved]:
    """Every catalogue entry resolved for this venue, in catalogue order."""
    facts = venue_facts(venue, baseline)
    return [resolve(s, facts) for s in CATALOGUE]
