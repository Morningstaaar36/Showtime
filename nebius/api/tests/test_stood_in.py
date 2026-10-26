"""When the model doesn't answer during an AI test, the rules stand in, and the test says so:
the session summary names each agent that rules replaced and why, so the plan never passes rule
output off as the AI's (step 7, flow 8: a bad key)."""

from __future__ import annotations

from typing import Any

from api.tests.test_redteam import _run_session, state  # noqa: F401


async def test_rules_standing_in_for_the_ai_are_recorded(state: Any) -> None:  # noqa: F811
    state.llm.script.clear()  # every agent call fails, as with a rejected key
    p = state.projects.create("Hall", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1, attacks_per_round=2)
    assert row.status == "finished"
    stood = row.summary["stood_in"]
    assert {"red_team", "judge"} <= set(stood), stood
    assert all("FakeLLM has no script" in why for why in stood.values())


async def test_an_ai_test_that_answered_has_no_stand_ins(state: Any) -> None:  # noqa: F811
    p = state.projects.create("Hall", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1, attacks_per_round=2)
    assert row.summary["stood_in"] == {}


async def test_a_built_in_script_is_never_called_ai_written(state: Any) -> None:  # noqa: F811
    state.llm.script.clear()  # the rules stand in, with their built-in scenario script
    p = state.projects.create("Hall", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1, attacks_per_round=2)
    logs = [e.payload["message"] for e in state.sessions.stored_events(row.id) if e.type == "log"]
    scripted = [m for m in logs if "written as code" in m]
    assert scripted and all("built-in example" in m for m in scripted), scripted


async def test_the_report_says_when_rules_stood_in(state: Any) -> None:  # noqa: F811
    from fastapi.testclient import TestClient

    from api.app.main import create_app

    state.llm.script.clear()
    p = state.projects.create("Hall", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1, attacks_per_round=2)
    with TestClient(create_app(state=state, settings=state.settings)) as c:
        html = c.get(f"/api/v1/sessions/{row.id}/report").text
    assert "The AI didn&#x27;t answer, so built-in rules wrote the attacks" in html or (
        "The AI didn't answer, so built-in rules wrote the attacks" in html
    )
