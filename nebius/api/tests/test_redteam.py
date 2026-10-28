"""Red/blue agents, judge number check, Red Team Night sessions, exporters and chaos cases.

Uses FakeLLM (scripted replies) and FakeRunner (scaled instant estimates): no GPU, no Docker.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from api.adapters.llm import Budget, FakeLLM, LLMError
from api.adapters.sandbox import FakeRunner
from api.agents.base import AgentEnv
from api.agents.blue_team import blue_team, check_fix
from api.agents.judge import judge
from api.agents.red_team import red_team
from api.app.state import build_state
from api.core.extensions import IncidentRecord, Registry
from api.core.extensions.breaks import BreakRule, break_reasons
from api.core.settings import Settings
from api.core.templates import get_template
from api.models import Attack, Venue
from api.orchestrator.reports import build_bundle
from api.orchestrator.session import SessionManager
from api.tests.conformance.suites import check_exporter

ROW = re.compile(r"row (\d+):")


def _incidents() -> list[IncidentRecord]:
    return [
        IncidentRecord(
            row_id=7,
            year=2003,
            country="USA",
            event_type="Nightclub",
            description="A crowd surged towards one exit. Many were crushed.",
            source_url="https://en.wikipedia.org/wiki/E2_nightclub_stampede",
            keywords=["exit", "crush"],
        ),
        IncidentRecord(
            row_id=9,
            year=1911,
            country="USA",
            event_type="Entertainment",
            description="",
            source_url="",
            keywords=["stairs"],
        ),
    ]


def red_reply(messages: list[dict[str, str]]) -> dict[str, Any]:
    rows = [int(x) for x in ROW.findall(messages[0]["content"])]
    row = rows[0] if rows else 7
    return {
        "attacks": [
            {
                "title": "South door lost",
                "incident_row": row,
                "events": [{"type": "block_exit", "exit_id": "door_s1", "at_s": 30}],
                "rationale": "door_s1 carries half the hall.",
            },
            {
                "title": "Same again",
                "incident_row": row,
                "events": [{"type": "block_exit", "exit_id": "door_s1", "at_s": 40}],
                "rationale": "dup",
            },
            {
                "title": "Ghost exit",
                "incident_row": row,
                "events": [{"type": "block_exit", "exit_id": "ghost", "at_s": 10}],
                "rationale": "bad",
            },
        ]
    }


BLUE = {
    "fixes": [
        {
            "title": "East door with marshals",
            "cost_label": "medium",
            "rationale": "adds width",
            "ops": [
                {
                    "op": "add_exit",
                    "floor_id": "F0",
                    "id": "door_e1",
                    "wall": "east",
                    "center": 8,
                    "width_m": 2.5,
                }
            ],
            "operational": [
                {
                    "type": "marshal_redirect",
                    "to_exit_id": "door_e1",
                    "from_exit_id": "door_s2",
                    "fraction": 0.4,
                    "at_s": 20,
                }
            ],
        },
        {
            "title": "Narrow door 2",
            "cost_label": "low",
            "rationale": "bad idea",
            "ops": [{"op": "resize", "target": "door_s2", "width_m": 1.0}],
            "operational": [],
        },
    ]
}


@pytest.fixture
def hall() -> Venue:
    return get_template("conference_hall_2f")


async def test_red_team_cites_dataset_and_discards_bad_attacks(
    registry: Registry, hall: Venue
) -> None:
    llm = FakeLLM({"red_team": red_reply})
    attacks = await red_team(
        AgentEnv(llm=llm, audit=False), registry, hall, None, _incidents(), 3, set()
    )
    assert [a.title for a in attacks] == ["South door lost"]  # duplicate and unknown id dropped
    a = attacks[0]
    assert str(a.inspired_by.source_url).startswith("https://en.wikipedia.org/")
    assert a.inspired_by.dataset_row == 7 and a.inspired_by.evidence


async def test_red_team_falls_back_to_doi_when_row_has_no_link(
    registry: Registry, hall: Venue
) -> None:
    llm = FakeLLM(
        {
            "red_team": lambda m: {
                "attacks": [
                    {
                        "title": "Stair rush",
                        "incident_row": 9,
                        "rationale": "x",
                        "events": [
                            {"type": "surge", "zone_id": "mezzanine", "extra_people": 50, "at_s": 0}
                        ],
                    }
                ]
            }
        }
    )
    attacks = await red_team(
        AgentEnv(llm=llm, audit=False), registry, hall, None, _incidents(), 2, set()
    )
    assert str(attacks[0].inspired_by.source_url).startswith(
        "https://doi.org/10.5281/zenodo.19483010#row=9"
    )


async def test_red_team_invalid_json_returns_nothing(registry: Registry, hall: Venue) -> None:
    llm = FakeLLM({"red_team": "this is not json at all"})
    attacks = await red_team(
        AgentEnv(llm=llm, audit=False), registry, hall, None, _incidents(), 2, set()
    )
    assert attacks == []


async def test_blue_team_validates_on_patched_venue(registry: Registry, hall: Venue) -> None:
    attack = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "x",
            "events": [{"type": "block_exit", "exit_id": "door_s1"}],
            "inspired_by": {"incident": "x", "source_url": "https://example.org"},
        }
    )
    from api.core.tier1 import run_tier1

    res = run_tier1(hall, attack.events, registry, Settings(_env_file=None))
    fixes = await blue_team(
        AgentEnv(llm=FakeLLM({"blue_team": BLUE}), audit=False), registry, hall, attack, res, 3, "F"
    )
    assert [f.title for f in fixes] == ["East door with marshals"]  # narrowing an exit is refused
    assert fixes[0].operational[0].type == "marshal_redirect"


def test_check_fix_rules(registry: Registry, hall: Venue) -> None:
    assert check_fix(registry, hall, [], []) != []
    assert check_fix(registry, hall, [{"op": "remove_obstacle", "obstacle_id": "stage"}], [])
    assert check_fix(registry, hall, [{"op": "resize", "target": "door_s1", "width_m": 1.0}], [])
    assert (
        check_fix(registry, hall, [], [{"type": "one_way", "exit_id": "door_s1", "at_s": 0}]) == []
    )


async def test_judge_number_check_falls_back_to_template() -> None:
    facts = {"baseline": {"evac_time_p95_s": 162.0, "peak_density_ppm2": 4.58}}
    bad = FakeLLM(
        {
            "judge": [
                {"summary": "Everyone is out in 999 seconds.", "recommendations": []},
                {"summary": "Still 999 seconds.", "recommendations": []},
            ]
        }
    )
    text, _, checked = await judge(AgentEnv(llm=bad, audit=False), facts, "TEMPLATE")
    assert text == "TEMPLATE" and not checked
    good = FakeLLM(
        {
            "judge": {
                "summary": "95% are out in 162 seconds; peak density 4.58.",
                "recommendations": ["Keep door_s1 clear."],
            }
        }
    )
    text, recs, checked = await judge(AgentEnv(llm=good, audit=False), facts, "TEMPLATE")
    assert checked and "162" in text and recs


RULE = BreakRule.of(Settings(_env_file=None), 300)


def test_break_reasons() -> None:
    from api.models import RunMetrics, RunResult

    ok = RunResult(
        run_id="r",
        tier=3,
        status="ok",
        metrics=RunMetrics(evac_time_p95_s=100, peak_density_ppm2=4, agents_total=100),
    )
    assert break_reasons(ok, RULE) == []
    slow = ok.model_copy(update={"metrics": ok.metrics.model_copy(update={"evac_time_p95_s": 250})})
    assert any("target" in r for r in break_reasons(slow, RULE))
    dense = ok.model_copy(
        update={"metrics": ok.metrics.model_copy(update={"time_above_danger_s": 30})}
    )
    assert any("density" in r for r in break_reasons(dense, RULE))


def test_break_rules_come_from_the_settings() -> None:
    """The tolerance for people still inside and the quick-run share are settings, not code."""
    from api.models import RunMetrics, RunResult

    left = RunResult(
        run_id="r",
        tier=3,
        status="ok",
        metrics=RunMetrics(evac_time_p95_s=100, agents_total=100, agents_not_evacuated=3),
    )
    assert break_reasons(left, RULE) == []  # 3 is within the default tolerance of 5
    strict = BreakRule.of(Settings(_env_file=None, stuck_tolerance_people=0), 300)
    assert any("still inside" in r for r in break_reasons(left, strict))
    quick = left.model_copy(
        update={
            "tier": 2,
            "metrics": RunMetrics(
                agents_total=100, agents_not_evacuated=40, extra={"evacuated_fraction": 0.6}
            ),
        }
    )
    assert break_reasons(quick, RULE) == []  # 60% out beats the default 50%
    demanding = BreakRule.of(Settings(_env_file=None, quick_min_out_fraction=0.8), 300)
    assert any("out after" in r for r in break_reasons(quick, demanding))
    public = Settings(_env_file=None).public_dict()
    for key in ("danger_min_duration_s", "stuck_tolerance_people", "at_risk_warning_s"):
        assert key in public  # the web verdict reads the same rules


# --- full sessions with fakes ----------------------------------------------------------------


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    db = f"sqlite:///{tmp_path / 's.sqlite'}"
    settings = Settings(
        _env_file=None,
        db_url=db,
        runs_dir=tmp_path / "runs",
        cache_dir=tmp_path / "c",
        llm_provider="fake",
        sandbox_provider="fake",
        offline=True,
        target_evac_indoor_s=120,
    )
    monkeypatch.setattr("api.core.settings.get_settings", lambda: settings)
    monkeypatch.setattr("api.db.session.get_settings", lambda: settings)
    monkeypatch.setattr("api.orchestrator.demos.DEMO_DIR", tmp_path / "no-demos")
    from api.db import session as dbs

    dbs.get_engine.cache_clear()
    script: dict[str, Any] = {
        "red_team": red_reply,
        "blue_team": BLUE,
        "judge": {"summary": "The plan was tested.", "recommendations": []},
    }
    st = build_state(settings, llm=FakeLLM(script, settings), runner=FakeRunner(settings.runs_dir))
    st.sessions = SessionManager(st)
    yield st
    dbs.get_engine.cache_clear()


async def _run_session(st: Any, project_id: str, **cfg: Any) -> Any:
    row = st.sessions.start(
        project_id,
        {"max_rounds": 2, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1, **cfg},
    )
    await st.sessions.live[row.id].task
    return st.sessions.get(row.id)


async def test_session_runs_to_completion_and_streams(state: Any) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = await _run_session(state, p.id)
    assert row.status == "finished"
    s = row.summary
    assert s["baseline_run_id"] and s["attacks"] and s["scoreboard"]
    types = {e.type for e in state.sessions.stored_events(row.id)}
    assert {"status", "agent_call", "attack_card", "branch_node", "run_finished", "score"} <= types
    replay = [e async for e in state.sessions.stream(row.id, after=3)]
    assert replay and replay[0].seq == 4
    bundle = build_bundle(state, p.id, row.id)
    for exp in state.registry.all("Exporter"):
        check_exporter(exp, bundle)
    if s["accepted_fixes"]:
        v = state.sessions.apply_final(row.id)
        assert v.version == 2


async def test_session_survives_llm_outage(state: Any) -> None:
    def down(_: Any) -> Any:
        raise LLMError("connection refused")

    state.llm.script["red_team"] = down
    state.llm.script["blue_team"] = down
    state.llm.script["judge"] = down
    p = state.projects.create("School", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1)
    assert row.status == "finished"
    assert row.summary["attacks"], "rule-based attacks should be used"
    assert all(a["extensions"].get("generated_by") == "rules" for a in row.summary["attacks"])
    assert "Planning aid" in row.summary["judge_text"]


async def test_session_budget_exhausted_finishes_gracefully(state: Any) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = state.sessions.start(p.id, {"max_rounds": 3, "max_tokens": 10})
    await state.sessions.live[row.id].task
    row = state.sessions.get(row.id)
    assert row.status == "finished"
    assert row.summary["stopped_reason"].startswith("budget")


async def test_session_sandbox_failures_fall_back_to_estimates(state: Any) -> None:
    state.runs.runner.fail_ids = {"r_"}  # every simulation fails
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = await _run_session(state, p.id, max_rounds=1)
    assert row.status == "finished"
    logs = [e for e in state.sessions.stored_events(row.id) if e.type == "log"]
    assert any("instant estimate" in e.payload["message"] for e in logs)


def test_budget_object() -> None:
    from api.adapters.llm import BudgetExceeded
    from api.models import Usage

    b = Budget(max_tokens=100)
    b.add(Usage(role="fast", model="m", prompt_tokens=80, completion_tokens=30))
    with pytest.raises(BudgetExceeded):
        b.check()
    assert json.dumps(b.by_role)


async def test_reimporting_an_export_keeps_its_history(state: Any) -> None:
    """Run ids are content-addressed: a second copy must still list the runs its sessions used."""
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = await _run_session(state, p.id, max_rounds=1)
    owned = {r.id for r in state.runs.list(p.id)}
    assert owned
    data = state.projects.export_zip(p.id)
    copy = state.projects.import_zip(data)
    copy_runs = {r.id for r in state.runs.list(copy.id)}
    assert {
        e.payload["run_id"]
        for e in state.sessions.stored_events(row.id)
        if e.type == "run_finished"
    } <= copy_runs
    assert state.sessions.list_sessions(copy.id)
    # deleting the original keeps the runs the copy's session still needs
    state.projects.delete(p.id)
    assert copy_runs == {r.id for r in state.runs.list(copy.id)}
    # and a re-export of the copy is complete
    again = state.projects.import_zip(state.projects.export_zip(copy.id))
    assert {r.id for r in state.runs.list(again.id)} == copy_runs


def test_attack_titles_cannot_name_missing_features(registry: Registry, field: Venue) -> None:
    from api.agents.red_team import grounded_title
    from api.models import Attack

    exit_id = field.floors[0].exits[0].id
    a = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Staircase congestion at front barrier",
            "events": [
                {"type": "slowdown", "factor": 0.5, "at_s": 0},
                {"type": "block_exit", "exit_id": exit_id, "at_s": 60},
            ],
            "inspired_by": {
                "incident": "x",
                "year": 1989,
                "source_url": "https://doi.org/x",
                "evidence": "y",
            },
            "rationale": "z",
        }
    )
    title = grounded_title(a.title, field, a, registry)
    assert "stair" not in title.lower()
    assert title.startswith("Slowdown and exit blocked at ")
    assert (
        grounded_title("Gate blocked at peak exit", field, a, registry)
        == "Gate blocked at peak exit"
    )


def test_sample_packs_install_once_update_and_respect_deletes(
    state: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.orchestrator import demos

    src = state.projects.create("Demo", template_id="school_wing")
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    monkeypatch.setattr(demos, "DEMO_DIR", pack_dir)
    (pack_dir / "a.showtime.zip").write_bytes(state.projects.export_zip(src.id))
    state.projects.delete(src.id)

    def samples() -> list[Any]:
        return [p for p in state.projects.list_projects() if p.sample]

    assert demos.install_demos(state) == 1 and len(samples()) == 1
    assert demos.install_demos(state) == 0  # unchanged pack
    first = samples()[0]
    # an updated pack replaces the unedited sample
    upd = state.projects.create("Demo", template_id="school_wing")
    state.projects.rename(upd.id, "Demo")
    (pack_dir / "a.showtime.zip").write_bytes(state.projects.export_zip(upd.id))
    state.projects.delete(upd.id)
    data = (pack_dir / "a.showtime.zip").read_bytes()
    assert demos.install_demos(state) == 1
    assert [p.id for p in samples()] != [first.id] and len(samples()) == 1
    # a sample the user deleted stays deleted
    state.projects.delete(samples()[0].id)
    assert demos.install_demos(state) == 0 and not samples()
    assert (pack_dir / "a.showtime.zip").read_bytes() == data


async def test_numbers_in_an_attack_must_come_from_the_venue_events_or_incident(
    registry: Registry, hall: Venue
) -> None:
    def invents(messages: list[dict[str, str]]) -> dict[str, Any]:
        out = red_reply(messages)
        out["attacks"] = [
            {
                **out["attacks"][0],
                "title": "South door lost at 30 s",  # 30 is the event's own at_s: allowed
                "rationale": "door_s1 carries 612 people out of the hall.",  # 612 is invented
            }
        ]
        return out

    llm = FakeLLM({"red_team": invents})
    attacks = await red_team(
        AgentEnv(llm=llm, audit=False), registry, hall, None, _incidents(), 3, set()
    )
    assert len(llm.calls) > 1 and "quotes 612" in str(llm.calls[1])  # sent back once
    assert attacks[0].title == "South door lost at 30 s"
    assert attacks[0].rationale == ""  # still unchecked after the repair: removed


def test_strip_numbers_removes_only_the_failed_ones() -> None:
    from api.agents.red_team import strip_numbers

    assert strip_numbers("Surge of 640 people at 30 s", ["640"]) == "Surge of people at 30 s"
