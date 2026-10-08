"""M5 check: 10 scripted edit requests against the real LLM (done when ≥ 9 are valid).

Responses are recorded into api/tests/fixtures/llm_cache so test_agents_replay.py can
replay them without a model. Usage:
  uv run --project api python scripts/eval_venue_agent.py [--replay]
"""

from __future__ import annotations

import asyncio
import sys
import time

from api.adapters.llm import LLMClient
from api.agents.base import AgentEnv
from api.agents.venue import propose_edit
from api.core.plugins import load_plugins
from api.core.settings import ROOT_DIR, Settings
from api.core.templates import get_template

FIXTURES = ROOT_DIR / "api" / "tests" / "fixtures" / "llm_cache"
# (template, request, expected ops as {op: {field: value}} subsets)
REQUESTS: list[tuple[str, str, list[dict[str, object]]]] = [
    (
        "conference_hall_2f",
        "add a 2 m exit on the east wall at y = 8",
        [{"op": "add_exit", "wall": "east", "center": 8, "width_m": 2}],
    ),
    (
        "conference_hall_2f",
        "make door_s1 3 m wide",
        [{"op": "resize", "target": "door_s1", "width_m": 3}],
    ),
    (
        "conference_hall_2f",
        "set the mezzanine to 250 people",
        [{"op": "set_people", "zone_id": "mezzanine", "people": 250}],
    ),
    (
        "festival_field",
        "move the front-of-house tent 6 m west",
        [{"op": "move", "target": "foh_tent", "dx": -6}],
    ),
    (
        "festival_field",
        "add a 6 m gate in the middle of the east fence",
        [{"op": "add_exit", "wall": "east", "width_m": 6}],
    ),
    (
        "festival_field",
        "increase the stage ballast to 3000 kg per leg",
        [{"op": "set_stage_param", "param": "ballast_kg_per_leg", "value": 3000}],
    ),
    (
        "school_wing",
        "make both stairwell exits 2 m wide",
        [
            {"op": "resize", "target": "stair_w", "width_m": 2},
            {"op": "resize", "target": "stair_e", "width_m": 2},
        ],
    ),
    (
        "school_wing",
        "put 30 pupils in classroom 1 and 35 in classroom 2",
        [
            {"op": "set_people", "zone_id": "room_1", "people": 30},
            {"op": "set_people", "zone_id": "room_2", "people": 35},
        ],
    ),
    (
        "t_alley",
        "block the alley exit to the main road",
        [{"op": "block_exit", "exit_id": "alley_s"}],
    ),
    ("festival_field", "remove the east bar", [{"op": "remove_obstacle", "obstacle_id": "bar_e"}]),
    (
        "school_wing",
        "add a 2 m exit on the east side",
        [{"op": "add_exit", "wall": "east", "width_m": 2}],
    ),
    (
        "conference_hall_2f",
        "add a 3 m exit on the east wall",
        [{"op": "add_exit", "wall": "east", "width_m": 3}],
    ),
]


def matches(ops: list[dict[str, object]], expected: list[dict[str, object]]) -> bool:
    """Every expected op appears (field subset match; numbers within 0.01)."""

    def same(a: object, b: object) -> bool:
        if isinstance(a, int | float) and isinstance(b, int | float):
            return abs(float(a) - float(b)) < 0.01
        return a == b

    return all(
        any(all(k in o and same(o[k], v) for k, v in exp.items()) for o in ops) for exp in expected
    ) and len(ops) == len(expected)


async def main(replay: bool) -> int:
    st = Settings(llm_cache_mode="replay" if replay else "record_replay", cache_dir=FIXTURES)
    llm = LLMClient(st)
    reg = load_plugins(ROOT_DIR).registry
    env = AgentEnv(llm=llm, audit=False)
    ok = 0
    for tid, text, expected in REQUESTS:
        t0 = time.time()
        out = await propose_edit(env, reg, get_template(tid), text)
        ops = [o.model_dump() for o in out.patch.ops] if out.patch else []
        good = out.status == "proposed" and matches(ops, expected)
        ok += good
        print(
            f"{'PASS' if good else 'FAIL'} {time.time() - t0:5.1f}s [{tid}] {text!r} -> "
            f"{out.status}: {out.explanation} {out.questions or ''} {out.problems or ''}"
            + ("" if good else f" | got {ops}"),
            flush=True,
        )
    print(f"RESULT {ok}/{len(REQUESTS)} correct patches")
    return 0 if ok >= 0.9 * len(REQUESTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--replay" in sys.argv)))
