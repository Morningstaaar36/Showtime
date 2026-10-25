"""The evidence desk: cited web suggestions about the briefed place and event, shown to the
organizer and never applied (step 4c)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from api.adapters.search import TavilySearch
from api.orchestrator.evidence_desk import desk_queries
from api.tests.test_autopilot import SENTENCE, _plan, state  # noqa: F401
from api.tests.test_search_adapter import FakeTavily


def test_queries_follow_the_brief() -> None:
    named = SimpleNamespace(kind="concert", place="Ramna Park, Dhaka")
    assert desk_queries(named, 3) == [
        ("capacity", "Ramna Park, Dhaka capacity"),
        ("attendance", "Ramna Park, Dhaka concert attendance crowd"),
        ("rules", "concert crowd safety guidance Ramna Park, Dhaka"),
    ]
    assert desk_queries(SimpleNamespace(kind="market", place=None), 3) == [
        ("rules", "market crowd safety guidance")
    ]
    assert desk_queries(named, 0) == []


async def test_live_search_gives_cited_suggestions_and_changes_no_number(
    state: Any,  # noqa: F811
    tmp_path: Path,
) -> None:
    state.search = TavilySearch("tv", tmp_path / "tavily", client=FakeTavily())
    run = await _plan(state, text=SENTENCE)
    assert run.status == "finished", run.error
    assert [(e.topic, e.url) for e in run.evidence] == [("rules", "https://example.org/crush")]
    assert run.evidence[0].sentence.startswith("Fans were crushed at gate C")
    # the brief and the venue keep their numbers: a suggestion is never applied
    assert state.projects.venue(run.project_id).total_people() == 400


async def test_without_web_search_there_are_no_suggestions(state: Any) -> None:  # noqa: F811
    run = await _plan(state, text=SENTENCE)
    assert run.evidence == []
