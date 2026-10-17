"""Who proposes attacks and fixes (S-01 evaluation arms): `config["agents"]` is "hybrid" (the
model plus the rule-based ones, the default), "rules" (no model calls for attacks or fixes) or
"model" (the model's proposals only). Scripted FakeLLM and a simulator-like runner: no Docker."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)
    yield lambda **kw: app_state(settings, **kw)
    reset_engine()


async def _session(st: Any, **cfg: Any) -> tuple[Any, list[Any]]:
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    row = st.sessions.start(
        p.id,
        {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1, **cfg},
    )
    await st.sessions.live[row.id].task
    return st.sessions.get(row.id), st.sessions.stored_events(row.id)


def _agents(events: list[Any]) -> list[str]:
    return [e.payload["agent"] for e in events if e.type == "agent_call"]


def _cards(events: list[Any], kind: str) -> list[dict[str, Any]]:
    return [e.payload[kind] for e in events if e.type == f"{kind}_card"]


async def test_hybrid_is_the_default_and_unknown_modes_fall_back_to_it(
    make_state: Callable[..., Any],
) -> None:
    row, _ = await _session(make_state())
    assert row.config["agents"] == "hybrid"
    row, _ = await _session(make_state(), agents="something else")
    assert row.config["agents"] == "hybrid"


async def test_rules_only_never_asks_the_model_for_attacks_or_fixes(
    make_state: Callable[..., Any],
) -> None:
    row, events = await _session(make_state(), agents="rules")
    assert row.status == "finished"
    called = _agents(events)
    assert "red_team" not in called and "blue_team" not in called
    assert _cards(events, "attack"), "rule-based attacks are still proposed"
    # rule-based fixes carry the R prefix
    assert all("R" in f["fix_id"] for f in _cards(events, "fix"))


async def test_model_only_adds_no_rule_based_proposals(make_state: Callable[..., Any]) -> None:
    row, events = await _session(make_state(), agents="model")
    assert row.status == "finished"
    called = _agents(events)
    assert "red_team" in called
    logs = [e.payload.get("message", "") for e in events if e.type == "log"]
    assert not any("Rule-based attacks" in m or "built-in example script" in m for m in logs)
    assert not any(m.startswith("Added standard responses") for m in logs)
    assert not any("R" in f["fix_id"].split("_", 1)[-1][:1] for f in _cards(events, "fix"))


async def test_agent_calls_report_validation_problems(make_state: Callable[..., Any]) -> None:
    _, events = await _session(make_state())
    calls = [e.payload for e in events if e.type == "agent_call"]
    assert calls
    assert all("problems" in c and "problems_first" in c for c in calls)
    assert all(c["problems_first"] >= c["problems"] or c["repaired"] for c in calls)
