"""Rule-based attacks and fixes, used when the language model is unavailable or returns
nothing valid. They follow the same contracts and cite real incidents."""

from __future__ import annotations

from typing import Any

from api.agents.red_team import _evidence, _source_url, signature
from api.core.extensions import IncidentRecord, Registry
from api.core.extensions import geometry as geo
from api.models import Attack, Fix, RunResult, Venue

PREFERRED_KEYWORDS = {
    "block_exit": ["locked", "exit", "gate", "blocked"],
    "surge": ["surge", "crush", "rush", "density"],
    "counterflow": ["counterflow", "alley", "narrow", "crush"],
    "slowdown": ["fire", "smoke", "power", "stairs"],
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
    return out


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
        if check_fix(registry, venue, ops, opn):
            continue
        out.append(
            Fix.model_validate(
                {
                    "fix_id": f"{id_prefix}{len(out) + 1}",
                    "for_attack": attack.attack_id,
                    "title": title,
                    "patch": {"ops": ops},
                    "operational": opn,
                    "rationale": why,
                    "cost_label": "medium" if ops else "low",
                    "extensions": {"generated_by": "rules"},
                }
            )
        )
    return out
