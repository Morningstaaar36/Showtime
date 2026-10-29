"""Real cases an organizer writes and saves: they are data next to the shipped examples, open
the same way (the Designer agent builds them from their text) and can be changed and deleted;
the shipped examples cannot."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import FakeRunner
from api.app.main import create_app
from api.app.state import build_state
from api.core.real_cases import EXTENSION_KEY, case_id_for, list_cases
from api.core.settings import ROOT_DIR
from api.orchestrator.real_cases import open_case
from api.orchestrator.session import SessionManager
from api.tests.evidence_fakes import reset_engine, use_test_settings
from api.tests.http import api_client

SPEC = json.loads(
    (ROOT_DIR / "api" / "tests" / "fixtures" / "real_cases" / "love_parade_2010.json").read_text()
)["spec"]
PEOPLE = sum(int(z["people"]) for z in SPEC["zones"])


def _facts(**change: Any) -> dict[str, Any]:
    """A case as the form sends it (the scripted designer reply fits its headcount)."""
    return {
        "title": "Ramp festival 2010 · test copy",
        "incident": "Crowd crush on a festival access ramp",
        "date": "2010-07-24",
        "place": "A festival ground reached through one ramp",
        "deaths": 21,
        "people": PEOPLE,
        "toll": "21 people died and more than 500 were injured.",
        "event_kind": "festival",
        "location": {"lat": 51.43, "lon": 6.78, "timezone": "Europe/Berlin"},
        "description": (
            f"{PEOPLE} people: a single access ramp about 26 m wide leads from two tunnels up "
            "to a fenced festival ground; people enter and leave by the same ramp."
        ),
        "what_happened": "Inflow and outflow met on the one ramp and the crowd became too dense.",
        "lesson": "Never let one passage carry both directions at peak times.",
        "sources": [
            {
                "label": "Love Parade disaster (Wikipedia)",
                "url": "https://en.wikipedia.org/wiki/Love_Parade_disaster",
            }
        ],
        "dimensions": ["Ramp about 26 m wide (sources differ)."],
        "approximations": ["The tunnels are drawn as two straight passages."],
        **change,
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    with api_client(create_app(state=state, settings=settings)) as c:
        yield c
    reset_engine()


def test_a_saved_case_is_listed_changed_and_deleted(client: TestClient) -> None:
    shipped = [c.id for c in list_cases()]
    r = client.post("/api/v1/real_cases", json=_facts())
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["id"] == "ramp_festival_2010_test_copy" and saved["origin"] == "saved"
    listed = client.get("/api/v1/real_cases").json()
    assert [c["id"] for c in listed] == [*shipped, saved["id"]]
    assert {c["origin"] for c in listed[: len(shipped)]} == {"example"}
    # the same title again gets its own id
    assert client.post("/api/v1/real_cases", json=_facts()).json()["id"].endswith("_2")

    r = client.put(f"/api/v1/real_cases/{saved['id']}", json=_facts(deaths=22))
    assert r.status_code == 200 and r.json()["deaths"] == 22
    assert client.delete(f"/api/v1/real_cases/{saved['id']}").status_code == 204
    assert saved["id"] not in [c["id"] for c in client.get("/api/v1/real_cases").json()]
    assert client.delete(f"/api/v1/real_cases/{saved['id']}").status_code == 404
    assert client.put("/api/v1/real_cases/nope", json=_facts()).status_code == 404


def test_the_shipped_examples_cannot_be_changed(client: TestClient) -> None:
    example = list_cases()[0].id
    r = client.put(f"/api/v1/real_cases/{example}", json=_facts())
    assert r.status_code == 409 and r.json()["code"] == "read_only" and r.json()["hint"]
    assert client.delete(f"/api/v1/real_cases/{example}").status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"sources": []},  # every case cites where it comes from
        {"sources": [{"label": "A source", "url": "not a link"}]},
        {"description": "too short"},
        {"date": "24 July 2010"},
        {"people": 0},
        {"event_kind": "picnic"},
        {"id": "chosen_id"},  # the id comes from the title
    ],
)
def test_a_case_without_what_it_needs_is_refused(
    client: TestClient, change: dict[str, Any]
) -> None:
    r = client.post("/api/v1/real_cases", json=_facts(**change))
    assert r.status_code == 422, r.text


def test_ids_come_from_the_title_and_stay_unique() -> None:
    assert case_id_for("Astroworld 2021 · Houston", set()) == "astroworld_2021_houston"
    assert case_id_for("Astroworld 2021 · Houston", {"astroworld_2021_houston"}).endswith("_2")
    assert case_id_for("···", set()) == "case"


@pytest.fixture
def case_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)

    def make(script: dict[str, Any]) -> Any:
        st = build_state(
            settings, llm=FakeLLM(script, settings), runner=FakeRunner(settings.runs_dir)
        )
        st.sessions = SessionManager(st)
        return st

    yield make
    reset_engine()


async def test_a_saved_case_opens_like_an_example_and_an_edit_builds_it_again(
    case_state: Callable[..., Any],
) -> None:
    from api.core.real_cases import CaseFacts
    from api.orchestrator.case_library import save_case

    st = case_state({"designer": [SPEC, SPEC, SPEC]})
    case = save_case(st, CaseFacts.model_validate(_facts()))
    first = await open_case(st, case.id)
    assert first["status"] == "testing"
    card = st.projects.venue(first["project_id"]).extensions[EXTENSION_KEY]
    assert card["id"] == case.id and card["sources"][0]["url"].startswith("https://")
    await st.sessions.live[first["session_id"]].task
    assert (await open_case(st, case.id))["project_id"] == first["project_id"]  # built once

    save_case(st, CaseFacts.model_validate(_facts(deaths=22)), case.id)
    again = await open_case(st, case.id)
    assert again["project_id"] != first["project_id"], "the edited text is built again"
    assert st.projects.get(first["project_id"]) is not None, "the earlier project stays"
    await st.sessions.live[again["session_id"]].task
    # a corrected location is an edit too: the venue keeps where it is
    moved = _facts(deaths=22, location={"lat": 51.4, "lon": 6.7, "timezone": "Europe/Berlin"})
    save_case(st, CaseFacts.model_validate(moved), case.id)
    third = await open_case(st, case.id)
    assert third["project_id"] != again["project_id"]
    assert st.projects.venue(third["project_id"]).location.lat == 51.4
    await st.sessions.live[third["session_id"]].task
