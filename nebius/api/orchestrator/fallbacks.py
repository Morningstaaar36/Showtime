"""Rule-based attacks and fixes, used when the language model is unavailable or returns
nothing valid. They follow the same contracts and cite real incidents."""

from __future__ import annotations

from typing import Any

from api.agents.red_team import _evidence, _source_url, script_attack, signature
from api.core.extensions import IncidentRecord, Registry
from api.core.extensions import geometry as geo
from api.core.scripts import EXAMPLE_SCRIPT
from api.models import Attack, Fix, RunResult, Venue
from api.orchestrator.archive import EVERYWHERE, Region

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
                [{"type": "block_exit", "exit_id": busiest.id, "at_s": 60}],
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
                        "people": max(20, min(total // 8, 400)),
                        "at_s": 30,
                    }
                ],
                f"A group entering through {busiest.id} meets the outgoing crowd head-on.",
            )
        )
    drafts.append(
        (
            "slowdown",
            "Power cut slows everyone down",
            [{"type": "slowdown", "factor": 0.6, "at_s": 20}],
            "With lights out people walk at about 60% of normal speed.",
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
        name = getattr(r, "name", "") or f"{r.event_type} crowd accident, {r.country}"
        out.append(
            Attack.model_validate(
                {
                    "attack_id": f"A{id_offset + len(out) + 1}",
                    "title": title,
                    "events": events,
                    "inspired_by": {
                        "incident": name,
                        "year": r.year,
                        "source_url": _source_url(r),
                        "evidence": _evidence(r),
                        "dataset_row": r.row_id,
                    },
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
        options: list[tuple[str, list[dict[str, Any]], str]] = []
        if kind == "exit_blocked" and len(open_exits) > 1:
            options = [
                (
                    f"{name(e.id)} lost one minute into the exit",
                    [{"type": "block_exit", "exit_id": e.id, "at_s": 60}],
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
                            "people": max(20, min(total // 8, 400)),
                            "at_s": 30,
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
                        [{"type": "slowdown", "factor": 0.6, "at_s": 20}],
                        "With lights out people walk at about 60% of normal speed.",
                    )
                ]
            else:
                options = [
                    (
                        f"Smoke slows people in {name(z.id)}",
                        [{"type": "slowdown", "zone_id": z.id, "factor": 0.5, "at_s": 20}],
                        f"Smoke in {z.id} halves walking speed where the crowd starts.",
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
                            "fraction": 0.6,
                            "at_s": 15,
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
    name = getattr(r, "name", "") or f"{r.event_type} crowd accident, {r.country}"
    return Attack.model_validate(
        {
            "attack_id": attack_id,
            "title": title,
            "events": events,
            "inspired_by": {
                "incident": name,
                "year": r.year,
                "source_url": _source_url(r),
                "evidence": _evidence(r),
                "dataset_row": r.row_id,
            },
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
    widest = max((e.width_m for e in floor.exits), default=2.0)
    spot = _wall_for_new_exit(venue, floor.floor_id)
    if spot is not None:
        wall, center = spot
        width = round(min(max(widest, 2.5), 8.0), 1)
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
                [{"type": "staggered_release", "zone_id": z.id, "delay_s": 60, "at_s": 0}],
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
                        "fraction": 0.4,
                        "at_s": 20,
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
