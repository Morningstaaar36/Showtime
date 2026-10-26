"""Designer probe: venue descriptions → the real model → solver → checks and instant estimate.

Runs in-process (no API server). Each line shows what was built: levels, people per level,
stairs, exits and whether everyone gets out. Responses are cached (LLM_CACHE_MODE), so a
second run is free. Usage:
  uv run --project api python scripts/design_probe.py [index ...] [--fixtures]
--fixtures writes each final spec to api/tests/fixtures/designer/ for the offline tests.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

from api.adapters.llm import LLMClient
from api.agents.base import AgentEnv
from api.agents.venue_designer import DesignOutcome, design_venue
from api.core.geometry import validate_venue
from api.core.plugins import load_plugins
from api.core.settings import ROOT_DIR, Settings
from api.core.tier1 import run_tier1

FIXTURES = ROOT_DIR / "api" / "tests" / "fixtures" / "designer"
PROMPTS: list[tuple[str, str]] = [
    ("office", "A 5-storey office building, 40 by 20 m, 150 people per floor, two stairwells at "
     "each end, main exit on the south."),
    ("hospital", "Hospital with 4 floors, 60 x 25 m, wards along a central corridor, 30 patients "
     "and 10 staff per floor, two stairs and one main entrance."),
    ("convocation", "University convocation in an indoor hall for 2,000 seated graduates and "
     "guests, stage on the north, four doors on the south and two fire exits on the east and "
     "west."),
    ("concert", "Rock concert in an open field 120 by 80 m, 8,000 standing fans, big stage on the "
     "north with a crowd barrier, three gates in the south fence, two bars and toilets on the "
     "east side."),
    ("mall", "A shopping mall with 3 levels, an atrium, 600 shoppers per level, escalators in the "
     "middle and exits on all four sides."),
    ("nightclub", "Nightclub in a basement 25 x 15 m, 300 people, one narrow stair up to the "
     "street and a fire exit at the back."),
    ("pandal", "Durga Puja pandal in Dhaka, open ground 50 by 40 m, 3,000 visitors, entry gate on "
     "the west and exit gate on the east, idol stage in the centre."),
    ("school", "School with 3 floors, each floor has 8 classrooms of 40 students off a corridor, "
     "stairs at both ends, two exits on the ground floor."),
    ("hotel", "A 10-storey hotel 45 by 18 m: a lobby on the ground floor with 120 guests, 60 "
     "guests on each upper floor in rooms off a central corridor, stairs at both ends, main "
     "entrance on the south and a service exit on the north."),
    ("concourse", "A stadium concourse on the first floor, 150 by 15 m, 2,500 fans at half-time, "
     "food kiosks along the north wall, four wide stairs down to the street-level gates on the "
     "south."),
    ("mosque", "A mosque 40 x 30 m with a main prayer hall for 1,200 men and a women's gallery "
     "upstairs for 300, entrances on the east and north."),
    ("metro", "Metro station: underground platform level 120 x 14 m with 800 waiting passengers, "
     "three stairs up to the street-level ticket hall, which has exits on the west and east."),
    ("market", "A street market on a square 60 by 40 m with 1,800 shoppers, rows of stalls, a 5 m "
     "lane leading north to the bus stop and two wide openings to the main road on the south."),
]  # fmt: skip


def describe(out: DesignOutcome, reg: Any, st: Settings) -> list[str]:
    """What was built, one line per floor."""
    call = out.call
    lines = [f"  status {out.status} | repaired {bool(call and call.repaired)}"]
    v = out.venue
    if v is None:
        return [*lines, f"  PROBLEMS: {out.problems}"]
    errors = [c.message for c in validate_venue(v).checks if c.severity == "error"]
    t1 = run_tier1(v, [], reg, st)
    lines.append(
        f"  {v.mode} | {len(v.floors)} floors | {len(v.stairs)} stair flights | "
        f"{v.total_people():,} people | geometry errors {len(errors)} | instant estimate: "
        f"{t1.metrics.agents_evacuated:,}/{t1.metrics.agents_total:,} out, "
        f"p95 {t1.metrics.evac_time_p95_s:.0f} s"
    )
    for f in v.floors:
        xs, ys = [p[0] for p in f.walkable], [p[1] for p in f.walkable]
        obstacles = [o.label or o.kind for o in f.obstacles if o.kind != "wall"]
        walls = sum(o.kind == "wall" for o in f.obstacles)
        lines.append(
            f"   {f.floor_id} {f.name} ({f.elevation_m:g} m) {max(xs) - min(xs):.0f}×"
            f"{max(ys) - min(ys):.0f} m: {sum(z.people for z in f.zones):,} people in "
            f"{len(f.zones)} zones; exits {[(e.label, e.width_m) for e in f.exits]}; "
            f"obstacles {obstacles[:6]}" + (f"; {walls} wall segments" if walls else "")
        )
    cores: dict[str, list[Any]] = {}
    for s in v.stairs:
        cores.setdefault(s.id.split("_")[1], []).append(s)
    if cores:
        lines.append(
            "   stairs: "
            + "; ".join(
                f"{len(ss)} × {ss[0].width_m:g} m ({', '.join(f'{s.from_floor}→{s.to_floor}' for s in ss[:3])}"
                + (" …" if len(ss) > 3 else "")
                + ")"
                for ss in cores.values()
            )
        )
    if out.problems:
        lines.append(f"  PROBLEMS: {out.problems[:4]}")
    if out.notes:
        lines.append(f"  notes: {out.notes[:3]}")
    lines.append(f"  assumptions: {out.assumptions[:4]}")
    return lines


def _labels(v: Any) -> str:
    parts = [f.name or "" for f in v.floors]
    for f in v.floors:
        parts += [o.label or o.kind for o in f.obstacles] + [z.label or "" for z in f.zones]
        parts += [e.label or "" for e in f.exits]
    if v.stage is not None:
        parts.append("stage")
    return " ".join(parts).lower()


def _people_on(v: Any, level_name: str) -> int:
    return sum(
        sum(z.people for z in f.zones) for f in v.floors if level_name in (f.name or "").lower()
    )


# what each description asks for, checked on the built venue (fidelity, not just "it built")
EXPECT: dict[str, list[tuple[str, Any]]] = {
    "convocation": [("2,000 people", lambda v: v.total_people() == 2000), ("6 exits", lambda v: sum(len(f.exits) for f in v.floors) >= 6), ("a stage", lambda v: "stage" in _labels(v))],
    "concert": [("8,000 people", lambda v: v.total_people() == 8000), ("open-air", lambda v: v.mode == "outdoor"), ("3 gates", lambda v: sum(len(f.exits) for f in v.floors) >= 3), ("stage", lambda v: "stage" in _labels(v)), ("barrier", lambda v: "barrier" in _labels(v))],
    "mall": [("1,800 people", lambda v: v.total_people() == 1800), ("3 levels", lambda v: len(v.floors) == 3), ("4 exits", lambda v: sum(len(f.exits) for f in v.floors) >= 4), ("atrium", lambda v: "atrium" in _labels(v))],
    "pandal": [("3,000 people", lambda v: v.total_people() == 3000), ("2 gates", lambda v: sum(len(f.exits) for f in v.floors) >= 2), ("idol stage", lambda v: "stage" in _labels(v) or "idol" in _labels(v))],
    "concourse": [("2,500 people", lambda v: v.total_people() == 2500), ("upper level", lambda v: len(v.floors) >= 2), ("4 wide stairs", lambda v: len(v.stairs) >= 4 or sum(len(f.exits) for f in v.floors) >= 4), ("kiosks", lambda v: "kiosk" in _labels(v))],
    "mosque": [("1,500 people", lambda v: v.total_people() == 1500), ("gallery upstairs", lambda v: len(v.floors) == 2), ("300 in the gallery", lambda v: _people_on(v, "gallery") == 300), ("2 entrances", lambda v: sum(len(f.exits) for f in v.floors) >= 2)],
    "metro": [("800 people", lambda v: v.total_people() == 800), ("underground platform", lambda v: any(f.elevation_m < 0 for f in v.floors)), ("3 stairs", lambda v: len(v.stairs) >= 3), ("2 exits", lambda v: sum(len(f.exits) for f in v.floors) >= 2)],
    "market": [("1,800 people", lambda v: v.total_people() == 1800), ("open-air", lambda v: v.mode == "outdoor"), ("stalls", lambda v: "stall" in _labels(v)), ("lane to the bus stop", lambda v: "bus" in _labels(v) or "lane" in _labels(v)), ("2 openings south", lambda v: sum(len(f.exits) for f in v.floors) >= 2)],
}  # fmt: skip


def fidelity(name: str, out: DesignOutcome) -> tuple[int, int, list[str]]:
    """(checks passed, checks, the ones missed) for what the description asked."""
    checks = EXPECT.get(name, [])
    if out.venue is None:
        return 0, len(checks), [c for c, _ in checks]
    missed = [c for c, ok in checks if not ok(out.venue)]
    return len(checks) - len(missed), len(checks), missed


def clean(out: DesignOutcome, reg: Any, st: Settings) -> bool:
    """Built cleanly: a venue with no geometry error in which everyone gets out (instant
    estimate), and the status says nothing is left to fix."""
    v = out.venue
    if v is None or out.status != "built":
        return False
    if any(c.severity == "error" for c in validate_venue(v).checks):
        return False
    m = run_tier1(v, [], reg, st).metrics
    return m.agents_total > 0 and m.agents_evacuated == m.agents_total


async def main(picks: list[int], fixtures: bool) -> None:
    st = Settings()
    reg = load_plugins(ROOT_DIR).registry
    llm = LLMClient(st)
    print(f"model {llm.model_for('main')}, cache {st.llm_cache_mode}")
    score: list[tuple[str, bool, int, tuple[int, int, list[str]]]] = []
    for i in picks or range(len(PROMPTS)):
        name, text = PROMPTS[i]
        t0, before = time.time(), llm.calls
        out = await design_venue(AgentEnv(llm=llm, audit=False), text)
        print(f"\n### [{i}] {name}: {text}  ({time.time() - t0:.0f} s, {llm.calls - before} live)")
        print("\n".join(describe(out, reg, st)), flush=True)
        score.append((name, clean(out, reg, st), llm.calls - before, fidelity(name, out)))
        if fixtures and out.spec is not None:
            FIXTURES.mkdir(parents=True, exist_ok=True)
            data = {"description": text, "spec": out.spec.model_dump(mode="json")}
            (FIXTURES / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")
    print("\n| venue | built cleanly | asked for | missed | live calls |")
    print("| --- | --- | --- | --- | --- |")
    for name, ok, calls, (got, of, missed) in score:
        miss = ", ".join(missed) or "—"
        print(f"| {name} | {'yes' if ok else 'no'} | {got}/{of} | {miss} | {calls} |")
    built = sum(ok for _, ok, _, _ in score)
    got = sum(f[0] for *_, f in score)
    of = sum(f[1] for *_, f in score)
    print(
        f"\nbuilt cleanly {built}/{len(score)}; asked for {got}/{of}; live model calls: {llm.calls}"
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main([int(a) for a in args if a.isdigit()], "--fixtures" in args))
