"""Failure map (quality-diversity archive): descriptors, physics fitness, elites, targets,
rule-based fills, and the archive in a full session (FakeLLM, FakeRunner)."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from api.adapters.llm import LLMError
from api.core.extensions import IncidentRecord
from api.core.scripts import check_script
from api.core.settings import Settings
from api.core.templates import get_template
from api.models import Attack, RunMetrics, RunResult
from api.models.failure_map import FailureMap
from api.orchestrator.archive import (
    EVERYWHERE,
    KIND_IDS,
    Archive,
    BreakRule,
    Elite,
    kind_of,
    pick_candidates,
    regions,
    severity_score,
)
from api.orchestrator.fallbacks import rule_attacks_for_cells
from api.orchestrator.session import break_reasons
from api.tests.test_redteam import _run_session, state  # noqa: F401  (fixture)

INC = [
    IncidentRecord(
        row_id=7,
        year=2003,
        country="USA",
        event_type="Nightclub",
        description="A crowd surged towards one exit. Many were crushed.",
        source_url="https://en.wikipedia.org/wiki/E2_nightclub_stampede",
        keywords=["exit", "crush"],
    )
]
SRC = {"incident": "x", "source_url": "https://example.org", "evidence": "e"}


def _attack(events: list[dict[str, Any]], aid: str = "A1") -> Attack:
    return Attack.model_validate(
        {
            "attack_id": aid,
            "title": "t",
            "events": events or [{"type": "slowdown", "factor": 0.5}],
            "inspired_by": SRC,
        }
    )


def _run(tier: int = 2, status: str = "ok", **m: Any) -> RunResult:
    extra = m.pop("extra", {})
    return RunResult(run_id="r", tier=tier, status=status, metrics=RunMetrics(extra=extra, **m))  # type: ignore[arg-type]


def test_exits_added_by_a_fix_land_in_an_existing_column(registry: Any) -> None:
    from api.core.venue_ops import apply_patch
    from api.models import VenuePatch

    hall = get_template("conference_hall_2f")
    a = Archive(hall)
    op = {"op": "add_exit", "floor_id": "F0", "id": "door_e1", "wall": "east", "center": 8}
    fixed = apply_patch(
        hall, VenuePatch.model_validate({"ops": [{**op, "width_m": 2.5}]}), registry
    ).venue
    atk = _attack([{"type": "block_exit", "exit_id": "door_e1", "at_s": 30}])
    assert a.cell_of(atk) is None
    a.learn(fixed)
    assert a.cell_of(atk) == ("exit_blocked", "floor:F0")


def test_event_types_map_to_hazard_kinds() -> None:
    assert kind_of("block_exit") == "exit_blocked"
    assert kind_of("marshal_redirect") == kind_of("one_way") == "route_change"
    assert kind_of("script") == "adaptive"
    # types other plugins may add are placed by keyword, never dropped
    assert kind_of("smoke_spread") == "slowdown"
    assert kind_of("late_arrivals") == "surge"
    assert kind_of("something_new") == "adaptive"


def test_regions_follow_floors_or_exits() -> None:
    hall = regions(get_template("conference_hall_2f"))
    assert [r.id for r in hall] == ["floor:F0", "floor:F1"]
    school = regions(get_template("school_wing"))
    assert [r.id for r in school] == ["near:stair_w", "near:stair_e"]
    assert {z for r in school for z in r.zones} == {f"room_{i}" for i in range(1, 9)}
    for t in ("festival_field", "t_alley", "stadium_concourse"):
        try:
            v = get_template(t)
        except Exception:
            continue
        a = Archive(v)
        assert len(a.regions) <= 4 and len(KIND_IDS) <= 6
        assert len({w for _, w in a.valid}) <= 5


def test_cells_are_deterministic_from_events() -> None:
    a = Archive(get_template("school_wing"))
    blk = _attack([{"type": "block_exit", "exit_id": "stair_e", "at_s": 30}])
    assert a.cell_of(blk) == ("exit_blocked", "near:stair_e")
    # a mixed attack is named by its most specific failure
    mix = _attack(
        [
            {"type": "slowdown", "factor": 0.5, "at_s": 0},
            {"type": "surge", "zone_id": "room_3", "extra_people": 20, "at_s": 0},
            {"type": "block_exit", "exit_id": "stair_w", "at_s": 60},
        ]
    )
    assert a.cell_of(mix) == ("exit_blocked", "near:stair_w")
    assert a.cell_of(_attack([{"type": "slowdown", "factor": 0.6, "at_s": 0}])) == (
        "slowdown",
        EVERYWHERE,
    )
    wrong = _attack(
        [
            {
                "type": "marshal_redirect",
                "from_exit_id": "stair_w",
                "to_exit_id": "stair_e",
                "fraction": 0.5,
                "at_s": 10,
            }
        ]
    )
    assert a.cell_of(wrong) == ("route_change", "near:stair_e")
    code = 'X = "stair_w"\n\ndef on_step(view, act):\n    act.close_exit(X)\n'
    scr = _attack([{"type": "script", "title": "s", "code": code, "at_s": 0}])
    assert a.cell_of(scr) == ("adaptive", "near:stair_w")


def test_severity_reaches_one_exactly_when_the_run_breaks() -> None:
    rule = BreakRule.of(Settings(_env_file=None), 120.0)
    grid = itertools.product(
        (2, 3),
        (None, 40.0, 79.0, 81.0, 200.0),
        (0.0, 3.0, 4.9, 5.0, 30.0),
        (0, 4, 5, 6, 40),
        (1.0, 4.0, 6.5),
        (None, 0.3, 0.7),
    )
    for tier, p95, danger_t, inside, peak, frac in grid:
        extra = {} if frac is None else {"evacuated_fraction": frac}
        r = _run(
            tier=tier,
            evac_time_p95_s=p95,
            time_above_danger_s=danger_t,
            agents_not_evacuated=inside,
            agents_total=400,
            peak_density_ppm2=peak,
            extra=extra,
        )
        score, parts = severity_score(r, rule)
        broke = bool(break_reasons(r, rule))
        assert (score >= 1.0) == broke, (tier, p95, danger_t, inside, peak, frac, parts)
    # density alone never counts as a break
    assert severity_score(_run(peak_density_ppm2=9.0), rule)[0] < 1.0
    assert severity_score(_run(status="failed", time_above_danger_s=99), rule)[0] == 0.0
    trapped = _run(tier=3, agents_total=100, extra={"trapped": 10.0})
    assert severity_score(trapped, rule)[0] == pytest.approx(2.0)
    # above a break the score grades how bad: 2.0 = danger for the whole evacuation target
    long = _run(time_above_danger_s=120.0, agents_total=400)
    assert severity_score(long, rule)[1]["danger_time"] == pytest.approx(2.0)
    half = _run(time_above_danger_s=62.5, agents_total=400)
    assert severity_score(half, rule)[1]["danger_time"] == pytest.approx(1.5)
    inside = _run(tier=3, agents_not_evacuated=40, agents_total=400)
    assert severity_score(inside, rule)[1]["people_inside"] == pytest.approx(2.0)


def _elite(aid: str, sev: float) -> Elite:
    return Elite(aid, aid, f"r_{aid}", sev, sev >= 1, 1)


def test_cells_keep_their_two_strongest_attacks() -> None:
    a = Archive(get_template("school_wing"))
    cell = ("exit_blocked", "near:stair_w")
    assert a.insert(_elite("A1", 0.5), cell).outcome == "new_cell"
    assert a.insert(_elite("A2", 0.3), cell).outcome == "added"
    assert a.insert(_elite("A3", 0.2), cell).outcome == "kept_out"
    ins = a.insert(_elite("A4", 1.4), cell)
    assert ins.outcome == "replaced" and ins.replaced == "A2"
    assert [e.attack_id for e in a.cells[cell]] == ["A4", "A1"]
    assert a.insert(_elite("A5", 9), None).outcome == "off_map"
    assert a.coverage() == round(1 / len(a.valid), 3)
    assert a.qd_score() == pytest.approx(1.9)
    snap = a.snapshot()
    assert snap["filled"] == 1 and snap["open_breaks"] == 1
    # a kept fix re-measures the elite; the search's QD-score keeps what was found
    a.mark_fixed("A4", "F1", 0.4, "r_f")
    assert a.best(cell) is not None and a.best(cell).attack_id == "A1"  # type: ignore[union-attr]
    assert a.qd_score() == pytest.approx(1.9)
    assert a.snapshot()["open_breaks"] == 0


def test_targets_spread_over_empty_cells_then_the_weakest() -> None:
    a = Archive(get_template("school_wing"))
    first = a.targets(3)
    assert len({k for k, _ in first}) == 3, "different hazard kinds"
    assert len({w for _, w in first}) >= 2, "different places"
    for c in a.valid:
        a.insert(_elite(f"{c[0]}{c[1]}", 0.9), c)
    weak = ("surge", "near:stair_e")
    a.cells[weak][0].severity = 0.1
    assert a.targets(1) == [weak]
    assert not a.empty()


def test_screening_prefers_empty_cells_over_raw_estimates() -> None:
    a = Archive(get_template("school_wing"))
    full = ("exit_blocked", "near:stair_w")
    a.insert(_elite("A0", 2.0), full)
    a.insert(_elite("A9", 2.0), full)
    c = [
        (_attack([], "A1"), full, 1.5),  # strong, but would not enter its full cell
        (_attack([], "A2"), ("surge", "near:stair_e"), 0.4),
        (_attack([], "A3"), ("surge", "near:stair_e"), 0.3),
        (_attack([], "A4"), ("counterflow", "near:stair_w"), 0.2),
    ]
    assert pick_candidates(c, a, 2) == [1, 3]
    assert pick_candidates(c, a, 4)[:2] == [1, 3]
    # a gap the round aimed at goes first, even with a lower estimate
    assert pick_candidates(c, a, 1, aim=[("counterflow", "near:stair_w")]) == [3]


@pytest.mark.parametrize("template", ["school_wing", "conference_hall_2f"])
def test_rule_fills_land_in_the_cells_they_target(template: str) -> None:
    v = get_template(template)
    a = Archive(v)
    seen: set[str] = set()
    for cell in a.valid:
        out = rule_attacks_for_cells(v, None, INC, [(cell[0], a.region(cell[1]))], seen)
        for atk in out:
            assert a.cell_of(atk) == cell, (cell, atk.events)
            if atk.events[0].type == "script":
                assert check_script(atk.events[0].model_dump()["code"]) == []
    hit = {
        a.cell_of(x)
        for x in rule_attacks_for_cells(v, None, INC, [(k, a.region(w)) for k, w in a.valid], set())
    }
    assert len(hit) >= len(a.valid) - 1


async def test_session_streams_and_keeps_the_failure_map(state: Any) -> None:  # noqa: F811
    def down(_: Any) -> Any:
        raise LLMError("connection refused")

    state.llm.script["red_team"] = down
    p = state.projects.create("School", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=2)
    assert row.status == "finished"
    arch = row.summary["archive"]
    filled = [c for c in arch["cells"] if c["elites"]]
    assert arch["filled"] == len(filled) >= 4
    assert len({c["kind"] for c in filled}) >= 3, "the search covers different hazard kinds"
    assert 0 < arch["coverage"] <= 1 and arch["qd_score"] > 0
    assert [h["round"] for h in arch["history"]][: len(row.summary["scoreboard"])] == [
        r["round"] for r in row.summary["scoreboard"]
    ]
    assert all("coverage" in r and "qd_score" in r for r in row.summary["scoreboard"])
    events = state.sessions.stored_events(row.id)
    changes = [e.payload["change"] for e in events if e.type == "archive" and e.payload["change"]]
    assert any(c["outcome"] == "new_cell" for c in changes)
    cards = [e.payload for e in events if e.type == "attack_card"]
    assert all("cell" in c for c in cards)
    # every elite is a simulated attack of this session
    ids = {a["attack_id"] for a in row.summary["attacks"]}
    assert {e["attack_id"] for c in filled for e in c["elites"]} <= ids

    from api.app.routes_agents import session_archive

    out = session_archive(row.id, state)
    assert out["session_id"] == row.id and out["cells_total"] == arch["cells_total"]
    assert FailureMap.of(arch).filled == arch["filled"]
