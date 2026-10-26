"""The red team searches the web for real incidents like this venue's (when search is live), cites
only what came back or the dataset, and labels each source's origin; without a key it says web
search is off and uses the incident dataset, never an error (steps 4b, 4f)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.adapters.search import TavilySearch
from api.tests.test_redteam import _run_session, state  # noqa: F401
from api.tests.test_search_adapter import FakeTavily


def _project(st: Any) -> str:
    return str(st.projects.create("Hall", template_id="conference_hall_2f").id)


def _search_calls(st: Any, sid: str) -> list[dict[str, Any]]:
    return [
        e.payload
        for e in st.sessions.stored_events(sid)
        if e.type == "tool_call" and e.payload.get("tool") == "search"
    ]


async def test_live_search_feeds_the_red_team_and_its_sources_are_labelled(
    state: Any,  # noqa: F811
    tmp_path: Path,
) -> None:
    fake = FakeTavily()
    state.search = TavilySearch("tv", tmp_path / "tavily", client=fake)
    row = await _run_session(state, _project(state), max_rounds=1)
    calls = _search_calls(state, row.id)
    assert len(calls) == 1
    call = calls[0]
    assert call["summary"] == "Red team searched the web: 1 source"
    assert call["sources"] == [
        {
            "title": "Crowd crush at a stadium gate",
            "url": "https://example.org/crush",
            "published": "2023-05-01",
        }
    ]
    assert 1 <= len(fake.calls) <= state.settings.search_queries_per_session
    web = [a for a in row.summary["attacks"] if a["inspired_by"]["origin"] == "tavily"]
    assert web, "an attack cites the web hit"
    assert web[0]["inspired_by"]["source_url"] == "https://example.org/crush"
    assert web[0]["inspired_by"]["dataset_row"] is None


async def test_without_a_key_web_search_is_off_and_the_dataset_is_used(state: Any) -> None:  # noqa: F811
    row = await _run_session(state, _project(state), max_rounds=1)
    calls = _search_calls(state, row.id)
    assert [c["summary"] for c in calls] == [
        "Web search is off (add a Tavily key to switch on): the red team uses the incident dataset."
    ]
    origins = {a["inspired_by"]["origin"] for a in row.summary["attacks"]}
    assert origins == {"dataset"}
    assert row.status == "finished"


def test_web_rows_are_labelled_and_never_claim_a_death_count() -> None:
    from api.adapters.search import SearchHit
    from api.agents.red_team import _incident_lines, web_records

    rows = web_records(
        [
            SearchHit(
                title="Gate crush",
                url="https://e.org/a",
                snippet="Fans crushed.",
                published="2023-05-01",
            )
        ]
    )
    line = _incident_lines(rows)
    assert line.startswith("row 100000: [web search result] Gate crush (2023). Fans crushed.")
    assert "deaths" not in line


def test_the_ai_team_lists_search_with_its_state_and_the_real_dataset_size(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from fastapi.testclient import TestClient

    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app
    from api.app.state import build_state
    from api.tests.evidence_fakes import reset_engine, use_test_settings

    s = use_test_settings(tmp_path, monkeypatch)
    st = build_state(s, llm=FakeLLM({}, s), runner=FakeRunner(s.runs_dir))
    try:
        with TestClient(create_app(state=st, settings=s)) as c:
            team = c.get("/api/v1/agents").json()
        red = next(a for a in team["agents"] if a["name"] == "red_team")
        assert "search" in red["tools"]
        assert team["tools"]["search"] == "Tavily web search: off (add a key to switch on)"
        n = sum(src.count() for src in st.registry.all("IncidentSource"))
        if n:
            assert team["tools"]["incidents"] == f"{n:,} real crowd accidents (incident dataset)"
    finally:
        reset_engine()


async def test_the_report_and_ask_label_where_each_source_came_from(
    state: Any,  # noqa: F811
    tmp_path: Path,
) -> None:
    from fastapi.testclient import TestClient

    from api.app.main import create_app

    state.search = TavilySearch("tv", tmp_path / "tavily", client=FakeTavily())
    row = await _run_session(state, _project(state), max_rounds=1)
    with TestClient(create_app(state=state, settings=state.settings)) as c:
        html = c.get(f"/api/v1/sessions/{row.id}/report").text
    assert "Crowd crush at a stadium gate (2023) · live web search" in html
    assert "Web search results: Tavily" in html
    assert "zenodo.19483010" in html  # the dataset cites itself through its plugin


def test_every_listed_tool_is_one_the_agent_really_uses() -> None:
    """The AI team page lists, per agent, the tools its work goes through (step 4g)."""
    from api.agents.team import TEAM
    from api.app.routes_agents import TOOL_LABELS

    tools = {m.agent.name: set(m.tools) for m in TEAM}
    assert tools["analyst"] == {"code_sandbox"}  # its code runs as a sandbox code job
    assert "solver" not in tools["venue"]  # the editor makes validated edits only
    assert {"map", "search"} <= tools["brief"]  # the evidence desk searches for it
    assert {"incidents", "search"} <= tools["red_team"]
    texts = {"judge", "officer", "explainer", "analyst_answer"}  # agents whose prose is shown
    assert all("number_check" in tools[n] for n in texts)
    assert all(t in TOOL_LABELS for ts in tools.values() for t in ts)
