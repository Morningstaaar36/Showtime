"""Rule-based attacks and fixes, used when the language model is unavailable or returns
nothing valid. They follow the same contracts and cite real incidents."""

from __future__ import annotations

from typing import Any

from api.agents.red_team import inspired_by, script_attack, signature
from api.core.extensions import IncidentRecord, Registry
from api.core.extensions import geometry as geo
from api.core.scenarios import (
    COUNTERFLOW_PEOPLE,
    DARK_SPEED,
    FIREFIGHTERS_AT_S,
    FIREFIGHTERS_PER_FLOOR,
    SMOKE_SPEED,
)
from api.core.scripts import EXAMPLE_SCRIPT
from api.models import Attack, Fix, RunResult, Venue
from api.orchestrator.archive import EVERYWHERE, Region

# strengths of the rule-written attacks and fixes (speeds are the scenario library's, see
# docs/ASSUMPTIONS.md): an attack takes the worst plausible case, a fix a moderate one
BLOCK_AT_S = 60  # an exit lost a minute in
COUNTERFLOW_SHARE = 1 / 8  # a group pushing back in, as a share of the crowd
COUNTERFLOW_AT_S = 30
SLOWDOWN_AT_S = 20
WRONG_WAY_FRACTION = 0.6  # people sent the wrong way by bad directions
WRONG_WAY_AT_S = 15
REDIRECT_FRACTION = 0.4  # people stewards move to the quietest exit (a fix)
REDIRECT_AT_S = 20
STAGGER_DELAY_S = 60
STAIR_FIX_STEP_M = 0.8  # a narrow stairwell widened by this much...
STAIR_FIX_MAX_WIDTH_M = 2.4  # ...up to this width
NEW_EXIT_MIN_WIDTH_M = 2.5  # an added exit is as wide as the widest one, within these bounds
NEW_EXIT_MAX_WIDTH_M = 8.0


def _counterflow_people(total: int) -> int:
    lo, hi = COUNTERFLOW_PEOPLE
    return max(lo, min(int(total * COUNTERFLOW_SHARE), hi))


PREFERRED_KEYWORDS = {
    "block_exit": ["locked", "exit", "gate", "blocked"],
    "surge": ["surge", "crush", "rush", "density"],
    "counterflow": ["counterflow", "alley", "narrow", "crush"],
    "slowdown": ["fire", "smoke", "power", "stairs"],
    "marshal_redirect": ["panic", "exit", "gate", "crush"],
}
# hazard kind (archive row) -> the incident keywords of the event that stages it
KIND_CITE = {
    "exit_blocked": "block_exit",
    "surge": "surge",
    "counterflow": "counterflow",
    "slowdown": "slowdown",
    "route_change": "marshal_redirect",
    "adaptive": "block_exit",
}


def _cite(incidents: list[IncidentRecord], kind: str, used: set[int]) -> IncidentRecord | None:
    words = PREFERRED_KEYWORDS.get(kind, [])
    ranked = sorted(
        incidents, key=lambda r: (-sum(w in r.keywords for w in words), r.row_id in used)
    )
    return ranked[0] if ranked else None


def rule_attacks(
    venue: Venue,
    baseline: RunResult | None,
    incidents: list[IncidentRecord],
    n: int,
    seen: set[str],
    id_offset: int = 0,
) -> list[Attack]:
    """Deterministic attacks on the busiest exit, the biggest zone, and the stairs/doors."""
    exits = [e for f in venue.floors for e in f.exits if not e.blocked]
    zones = sorted((z for f in venue.floors for z in f.zones), key=lambda z: -z.people)
    loads = {p.exit_id: p.people for p in (baseline.metrics.per_exit if baseline else [])}
    busiest = max(exits, key=lambda e: (loads.get(e.id, 0), e.width_m)) if exits else None
    total = venue.total_people()
    drafts: list[tuple[str, str, list[dict[str, Any]], str]] = []
    if busiest is not None and len(exits) > 1:
        drafts.append(
            (
                "block_exit",
                f"{busiest.label or busiest.id} lost one minute into the exit",
                [{"type": "block_exit", "exit_id": busiest.id, "at_s": BLOCK_AT_S}],
                f"{busiest.id} carries the most people, so losing it overloads the others.",
            )
        )
    if zones:
        z = zones[0]
        drafts.append(
            (
                "surge",
                f"Late surge into {z.label or z.id}",
                [
                    {
                        "type": "surge",
                        "zone_id": z.id,
                        "extra_people": max(20, z.people // 4),
                        "at_s": 0,
                    }
                ],
                f"{z.id} is the largest zone; a quarter more people arrive as it empties.",
            )
        )
    if busiest is not None:
        drafts.append(
            (
                "counterflow",
                f"People push in through {busiest.label or busiest.id}",
                [
                    {
                        "type": "counterflow",
                        "exit_id": busiest.id,
                        "people": _counterflow_people(total),
                        "at_s": COUNTERFLOW_AT_S,
                    }
                ],
                f"A group entering through {busiest.id} meets the outgoing crowd head-on.",
            )
        )
    drafts.append(
        (
            "slowdown",
            "Power cut slows everyone down",
            [{"type": "slowdown", "factor": DARK_SPEED, "at_s": SLOWDOWN_AT_S}],
            f"With lights out people walk at about {DARK_SPEED:.0%} of normal speed.",
        )
    )
    out: list[Attack] = []
    used: set[int] = set()
    for kind, title, events, why in drafts:
        if len(out) >= n:
            break
        sig = signature(events)
        if sig in seen:
            continue
        r = _cite(incidents, kind, used)
        if r is None:
            continue
        used.add(r.row_id)
        seen.add(sig)
        out.append(
            Attack.model_validate(
                {
                    "attack_id": f"A{id_offset + len(out) + 1}",
                    "title": title,
                    "events": events,
                    "inspired_by": inspired_by(r),
                    "rationale": why,
                    "extensions": {"generated_by": "rules"},
                }
            )
        )
    # one hand-written scenario script, so AI-written scenarios show without a model
    if out and len(exits) > 1:
        ex = script_attack(
            "Busiest gate jams 20 seconds in",
            EXAMPLE_SCRIPT,
            _cite(incidents, "block_exit", used) or incidents[0],
            f"A{id_offset + len(out) + 1}",
            "A gate that reacts to the crowd: whichever exit has the most people heading "
            "to it fails at 20 s.",
            generated_by="rules",
        )
        sig = signature([e.model_dump() for e in ex.events])
        if sig not in seen:
            seen.add(sig)
            out.append(ex)
    return out


def _exit_script(exit_id: str) -> str:
    """A gate that fails when its queue peaks (adaptive: it watches the crowd)."""
    return (
        f"TARGET = {exit_id!r}\n"
        'state = {"best": 0, "done": False}\n\n\n'
        "def on_step(view, act):\n"
        '    if state["done"] or TARGET not in view.exit_ids:\n'
        "        return\n"
        '    q = view.exits[TARGET]["queue"]\n'
        '    if q > state["best"]:\n'
        '        state["best"] = q\n'
        '    elif view.t >= 15 and q > 0 and q < 0.9 * state["best"]:\n'
        "        act.close_exit(TARGET)\n"
        '        act.note(TARGET + " jams as its queue peaks")\n'
        '        state["done"] = True\n'
    )


def _zone_script(zone_id: str, n: int) -> str:
    """A late group pushes into a zone while it is still crowded (adaptive)."""
    return (
        f"TARGET = {zone_id!r}\n"
        'state = {"done": False}\n\n\n'
        "def on_step(view, act):\n"
        '    if state["done"] or TARGET not in view.zone_ids or view.t < 10:\n'
        "        return\n"
        '    if view.zones[TARGET]["people"] > 0:\n'
        f"        act.add_people(TARGET, {n})\n"
        '        act.note("A late group pushes into " + TARGET)\n'
        '        state["done"] = True\n'
    )


def rule_attacks_for_cells(
    venue: Venue,
    baseline: RunResult | None,
    incidents: list[IncidentRecord],
    targets: list[tuple[str, Region]],
    seen: set[str],
    id_offset: int = 0,
) -> list[Attack]:
    """One deterministic attack per failure-map cell (hazard kind × region) when it can be
    staged there; cells it cannot stage are skipped."""
    exits = {e.id: e for f in venue.floors for e in f.exits}
    zones = {z.id: z for f in venue.floors for z in f.zones}
    open_exits = [e for e in exits.values() if not e.blocked]
    loads = {p.exit_id: p.people for p in (baseline.metrics.per_exit if baseline else [])}
    total = venue.total_people()

    def name(x: str) -> str:
        obj = exits.get(x) or zones.get(x)
        return (obj.label if obj is not None else None) or x

    out: list[Attack] = []
    used: set[int] = set()
    for kind, region in targets:
        r_exits = sorted(
            (exits[x] for x in region.exits if x in exits and not exits[x].blocked),
            key=lambda e: (-loads.get(e.id, 0), -e.width_m, e.id),
        )
        r_zones = sorted((zones[x] for x in region.zones if x in zones), key=lambda z: -z.people)
        # an upper floor's ways out are its stair flights: lose one (when the floor has another)
        # or meet people coming up it
        r_stairs = [s for s in venue.stairs if s.id in region.exits]
        ways_from = {
            f: sum(1 for s in venue.stairs if s.from_floor == f)
            for f in {s.from_floor for s in r_stairs}
        }
        options: list[tuple[str, list[dict[str, Any]], str]] = []
        if kind == "exit_blocked" and r_stairs and not r_exits:
            options = [
                (
                    f"{s.id} lost to smoke one minute in",
                    [{"type": "block_exit", "exit_id": s.id, "at_s": BLOCK_AT_S}],
                    f"With {s.id} gone, its floor has to use its other stairs.",
                )
                for s in r_stairs
                if ways_from[s.from_floor] > 1
            ]
        elif kind == "counterflow" and r_stairs and not r_exits:
            options = [
                (
                    f"People come up {s.id} against the crowd",
                    [
                        {
                            "type": "counterflow",
                            "exit_id": s.id,
                            "people": FIREFIGHTERS_PER_FLOOR,
                            "at_s": FIREFIGHTERS_AT_S,
                        }
                    ],
                    f"A group climbing {s.id} halves its flow down.",
                )
                for s in r_stairs
            ]
        elif kind == "exit_blocked" and len(open_exits) > 1:
            options = [
                (
                    f"{name(e.id)} lost one minute into the exit",
                    [{"type": "block_exit", "exit_id": e.id, "at_s": BLOCK_AT_S}],
                    f"Losing {e.id} sends its share of the crowd to the other exits.",
                )
                for e in r_exits
            ]
        elif kind == "surge":
            options = [
                (
                    f"Late surge into {name(z.id)}",
                    [
                        {
                            "type": "surge",
                            "zone_id": z.id,
                            "extra_people": max(20, min(z.people // 4, total // 2)),
                            "at_s": 0 if i == 0 else 90,
                        }
                    ],
                    f"{z.id} holds {z.people} people; a quarter more arrive as it empties.",
                )
                for i, z in enumerate(r_zones)
                if z.people > 0
            ]
        elif kind == "counterflow":
            options = [
                (
                    f"People push in through {name(e.id)}",
                    [
                        {
                            "type": "counterflow",
                            "exit_id": e.id,
                            "people": _counterflow_people(total),
                            "at_s": COUNTERFLOW_AT_S,
                        }
                    ],
                    f"A group entering through {e.id} meets the outgoing crowd head-on.",
                )
                for e in r_exits
            ]
        elif kind == "slowdown":
            if region.id == EVERYWHERE:
                options = [
                    (
                        "Power cut slows everyone down",
                        [{"type": "slowdown", "factor": DARK_SPEED, "at_s": SLOWDOWN_AT_S}],
                        f"With lights out people walk at about {DARK_SPEED:.0%} of normal speed.",
                    )
                ]
            else:
                options = [
                    (
                        f"Smoke slows people in {name(z.id)}",
                        [
                            {
                                "type": "slowdown",
                                "zone_id": z.id,
                                "factor": SMOKE_SPEED,
                                "at_s": SLOWDOWN_AT_S,
                            }
                        ],
                        f"Smoke in {z.id} cuts walking speed to {SMOKE_SPEED:.0%} where the "
                        "crowd starts.",
                    )
                    for z in r_zones
                ]
        elif kind == "route_change":
            others = sorted(
                (e for e in open_exits if e.id not in region.exits),
                key=lambda e: (-loads.get(e.id, 0), e.id),
            )
            if r_exits and len(r_exits) > 1 and not others:
                others = r_exits[1:]
            options = [
                (
                    f"Wrong directions send people to {name(e.id)}",
                    [
                        {
                            "type": "marshal_redirect",
                            "from_exit_id": others[0].id,
                            "to_exit_id": e.id,
                            "fraction": WRONG_WAY_FRACTION,
                            "at_s": WRONG_WAY_AT_S,
                            "speech": f"Everyone use {name(e.id)}!",
                        }
                    ],
                    f"Misdirection piles people from {others[0].id} onto {e.id}.",
                )
                for e in r_exits
                if others and others[0].id != e.id
            ]
        elif kind == "adaptive":
            if region.id == EVERYWHERE and len(open_exits) > 1:
                options = [
                    (
                        "Busiest gate jams 20 seconds in",
                        [{"script": EXAMPLE_SCRIPT}],
                        "A gate that reacts to the crowd: whichever exit has the most people "
                        "heading to it fails at 20 s.",
                    )
                ]
            elif r_exits and len(open_exits) > 1:
                e = r_exits[0]
                options = [
                    (
                        f"{name(e.id)} jams as its queue peaks",
                        [{"script": _exit_script(e.id)}],
                        f"{e.id} fails at the worst moment: when its queue is longest.",
                    )
                ]
            elif r_zones and r_zones[0].people > 0:
                z = r_zones[0]
                n = max(20, min(z.people // 4, total // 2))
                options = [
                    (
                        f"Late group pushes into {name(z.id)}",
                        [{"script": _zone_script(z.id, n)}],
                        f"{n} more people join {z.id} while it is still crowded.",
                    )
                ]
        for title, events, why in options:
            cite = _cite(incidents, KIND_CITE[kind], used)
            if cite is None:
                break
            aid = f"A{id_offset + len(out) + 1}"
            if "script" in events[0]:
                a = script_attack(
                    title, str(events[0]["script"]), cite, aid, why, generated_by="rules"
                )
            else:
                a = _rule_attack(aid, title, events, why, cite)
            sig = signature([e.model_dump() for e in a.events])
            if sig in seen:
                continue
            seen.add(sig)
            used.add(cite.row_id)
            out.append(a)
            break
    return out


def _rule_attack(
    attack_id: str, title: str, events: list[dict[str, Any]], why: str, r: IncidentRecord
) -> Attack:
    return Attack.model_validate(
        {
            "attack_id": attack_id,
            "title": title,
            "events": events,
            "inspired_by": inspired_by(r),
            "rationale": why,
            "extensions": {"generated_by": "rules"},
        }
    )


def _wall_for_new_exit(venue: Venue, floor_id: str) -> tuple[str, float] | None:
    f = venue.floor(floor_id)
    x0, y0, x1, y1 = geo.to_polygon(f.walkable).bounds
    counts = {"north": 0, "south": 0, "east": 0, "west": 0}
    for e in f.exits:
        cx, cy = geo.centroid(e.polygon)
        d = {
            "north": abs(y1 - cy),
            "south": abs(cy - y0),
            "east": abs(x1 - cx),
            "west": abs(cx - x0),
        }
        counts[min(d, key=lambda k: d[k])] += 1
    zones = [z for z in f.zones if z.people > 0]
    if not zones:
        return None
    zx = sum(geo.centroid(z.polygon)[0] * z.people for z in zones) / sum(z.people for z in zones)
    zy = sum(geo.centroid(z.polygon)[1] * z.people for z in zones) / sum(z.people for z in zones)
    order = sorted(
        counts,
        key=lambda k: (
            counts[k],
            {"north": y1 - zy, "south": zy - y0, "east": x1 - zx, "west": zx - x0}[k],
        ),
    )
    for wall in order:
        center = zy if wall in ("east", "west") else zx
        return wall, round(center, 1)
    return None


def _stair_fixes(
    registry: Registry, venue: Venue, attack: Attack, check_fix: Any
) -> list[tuple[str, list[dict[str, Any]], list[dict[str, Any]], str, str]]:
    """Wider stairwells and a phased evacuation, for buildings with stairs."""
    out: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]], str, str]] = []
    if not venue.stairs:
        return out
    # the street level (a basement lies below it): the highest floor at or below elevation 0
    at_or_below = [f for f in venue.floors if f.elevation_m <= 0.01]
    ground = (
        max(at_or_below, key=lambda f: f.elevation_m)
        if at_or_below
        else min(venue.floors, key=lambda f: f.elevation_m)
    ).floor_id
    # stairs into the street level carry everyone (down from above, or up from a basement)
    into_ground = [s for s in venue.stairs if s.to_floor == ground or s.from_floor == ground]
    seen: set[str] = set()
    # the flights into the ground floor, narrowest first: each one is a stairwell to widen
    for st in sorted(into_ground, key=lambda s: s.width_m):
        if st.id in seen or st.width_m >= STAIR_FIX_MAX_WIDTH_M:
            continue
        seen.update(geo.stairwell(venue, st.id))
        width = round(min(st.width_m + STAIR_FIX_STEP_M, STAIR_FIX_MAX_WIDTH_M), 1)
        ops = [{"op": "widen_stair", "stair_id": st.id, "width_m": width}]
        if not check_fix(registry, venue, ops, []):
            out.append(
                (
                    "layout",
                    ops,
                    [],
                    f"Widen {st.id} to {width:g} m on every floor",
                    f"A {width:g} m stair carries about {width / st.width_m:.1f} times as many "
                    "people per second down the building.",
                )
            )
        if len(out) >= 2:
            break
    # one stairwell for everyone above the street: a second one, with its own street door
    wells = {tuple(sorted(geo.stairwell(venue, s.id))) for s in into_ground}
    if len(wells) == 1:
        ops = [{"op": "add_stairwell", "width_m": STAIR_FIX_MAX_WIDTH_M / 2}]
        if not check_fix(registry, venue, ops, []):
            out.insert(
                0,
                (
                    "layout",
                    ops,
                    [],
                    "Add a second stairwell with its own street door",
                    "Everyone above the street depends on one stair; a second, enclosed one "
                    "away from it keeps a way down when the first is lost.",
                ),
            )
    # phased evacuation: the floor in trouble leaves first, the floors above wait a minute
    floors = {f.floor_id: f for f in venue.floors}
    hit: str | None = None
    for e in attack.events:
        d = e.model_dump()
        if d.get("floor_id") in floors:
            hit = str(d["floor_id"])
        elif d.get("zone_id"):
            hit = next(
                (f.floor_id for f in venue.floors for z in f.zones if z.id == d["zone_id"]), hit
            )
    if hit is not None and hit != ground:
        level = floors[hit].elevation_m
        wait = [
            z.id for f in venue.floors if f.elevation_m > level for z in f.zones if z.people > 0
        ]
        if wait:
            name = floors[hit].name or hit
            out.append(
                (
                    "ops",
                    [],
                    [
                        {
                            "type": "staggered_release",
                            "zone_id": zid,
                            "delay_s": STAGGER_DELAY_S,
                            "at_s": 0,
                        }
                        for zid in wait
                    ],
                    f"Phased evacuation: the {name.lower()} goes first",
                    "The floors above wait a minute, so the stairs are clear for the floor at "
                    "risk.",
                )
            )
    return out


def rule_fixes(
    registry: Registry, venue: Venue, attack: Attack, result: RunResult, n: int, id_prefix: str
) -> list[Fix]:
    """New exit near the crowd, staggered release, one-way flow, marshals."""
    from api.agents.blue_team import check_fix

    candidates: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]], str, str]] = []
    floor = (
        venue.floors[0]
        if len(venue.floors) == 1
        else min(venue.floors, key=lambda f: f.elevation_m)
    )
    per = sorted(result.metrics.per_exit, key=lambda p: -p.people)
    # In a building the way down is usually the bottleneck, so those fixes come first.
    candidates += _stair_fixes(registry, venue, attack, check_fix)
    widest = max((e.width_m for e in floor.exits), default=2.0)
    spot = _wall_for_new_exit(venue, floor.floor_id)
    if spot is not None:
        wall, center = spot
        width = round(min(max(widest, NEW_EXIT_MIN_WIDTH_M), NEW_EXIT_MAX_WIDTH_M), 1)
        for shift in (0.0, -6.0, 6.0, -12.0, 12.0):
            ops = [
                {
                    "op": "add_exit",
                    "floor_id": floor.floor_id,
                    "id": f"exit_{wall[0]}_{id_prefix.lower()}",
                    "wall": wall,
                    "center": center + shift,
                    "width_m": width,
                }
            ]
            if not check_fix(registry, venue, ops, []):
                candidates.append(
                    (
                        "layout",
                        ops,
                        [],
                        f"Open a {width:g} m exit on the {wall} side",
                        f"Adds {width:g} m of exit width close to where most people stand.",
                    )
                )
                break
    for e in attack.events:
        if e.type == "counterflow":
            ex = e.model_dump().get("exit_id")
            candidates.append(
                (
                    "ops",
                    [],
                    [{"type": "one_way", "exit_id": ex, "at_s": 0}],
                    f"Enforce one-way flow at {ex}",
                    "Stewards stop people entering against the outgoing crowd.",
                )
            )
    zones = sorted((z for f in venue.floors for z in f.zones), key=lambda z: -z.people)
    if zones:
        z = zones[0]
        candidates.append(
            (
                "ops",
                [],
                [
                    {
                        "type": "staggered_release",
                        "zone_id": z.id,
                        "delay_s": STAGGER_DELAY_S,
                        "at_s": 0,
                    }
                ],
                f"Stagger the release of {z.label or z.id}",
                "Holding the largest zone for a minute spreads the load on the exits.",
            )
        )
    if len(per) >= 2 and per[0].people > 0:
        candidates.append(
            (
                "ops",
                [],
                [
                    {
                        "type": "marshal_redirect",
                        "from_exit_id": per[0].exit_id,
                        "to_exit_id": per[-1].exit_id,
                        "fraction": REDIRECT_FRACTION,
                        "at_s": REDIRECT_AT_S,
                        "speech": f"This way to {per[-1].exit_id}!",
                    }
                ],
                f"Marshals send people from {per[0].exit_id} to {per[-1].exit_id}",
                f"{per[0].exit_id} is the busiest exit while {per[-1].exit_id} has room.",
            )
        )
    out: list[Fix] = []
    for _, ops, opn, title, why in candidates:
        if len(out) >= n:
            break
        actions = []
        from api.core.plan import PLAN_KEY, plan_data

        data = plan_data(venue)
        if PLAN_KEY in venue.extensions and data.enforce_constraints and opn:
            # Standard fixes use the same inventory and validator as model proposals.
            for j, event in enumerate(opn):
                start = float(event.get("at_s", 0))
                end = (
                    max(start + float(event.get("delay_s", 0)), start + 1)
                    if event["type"] == "staggered_release"
                    else 3600
                )
                pool = next(
                    (
                        rid
                        for rid, r in data.constraints.resources.items()
                        if r.kind == "staff"
                        and r.count >= 1
                        and r.available_from_s <= start
                        and r.available_until_s >= end
                    ),
                    None,
                )
                if pool is None:
                    break
                actions.append(
                    {
                        "action_id": f"{id_prefix}{len(out) + 1}_measure_{j + 1}",
                        "label": title,
                        "event": event,
                        "start_s": start,
                        "end_s": end,
                        "resources": [{"resource_id": pool, "quantity": 1}],
                        "source": "rules",
                    }
                )
            if len(actions) != len(opn):
                continue
            opn = []
        if check_fix(registry, venue, ops, opn, actions=actions):
            continue
        out.append(
            Fix.model_validate(
                {
                    "fix_id": f"{id_prefix}{len(out) + 1}",
                    "for_attack": attack.attack_id,
                    "title": title,
                    "patch": {"ops": ops},
                    "operational": opn,
                    "actions": actions,
                    "rationale": why,
                    "cost_label": "medium" if ops else "low",
                    "extensions": {"generated_by": "rules"},
                }
            )
        )
    return out
