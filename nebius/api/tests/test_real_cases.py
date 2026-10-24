"""Real cases: sourced descriptions → the Designer agent (scripted here) → solved venue → test.

The scripted replies in fixtures/real_cases/ stand in for what the model writes for each case
description; no live model is called. They exercise the solver's passages, narrowings, end
areas, pens and headings, and the open-a-case path end to end (designer, project, rule-based
test without the judge).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import FakeRunner
from api.agents.base import AgentEnv
from api.agents.venue_designer import check_spec, design_venue
from api.app.main import create_app
from api.app.state import build_state
from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.core.real_cases import EXTENSION_KEY, get_case, list_cases
from api.core.settings import ROOT_DIR, Settings
from api.core.tier1 import run_tier1
from api.models import Venue
from api.models.venue_spec import VenueSpec
from api.orchestrator.real_cases import CASE_TEST, open_case
from api.orchestrator.session import SessionManager
from api.tests.evidence_fakes import reset_engine, use_test_settings

S = Settings(_env_file=None)
FIXTURES = ROOT_DIR / "api" / "tests" / "fixtures" / "real_cases"
IDS = [c.id for c in list_cases()]


def _spec(case_id: str) -> dict[str, Any]:
    return dict(json.loads((FIXTURES / f"{case_id}.json").read_text())["spec"])


def _venue(case_id: str) -> Venue:
    built, problems = check_spec(VenueSpec.model_validate(_spec(case_id)))
    assert problems == [], problems
    return built.venue


def _headcount(text: str) -> int:
    m = re.search(r"([\d,]+) people:", text)
    assert m, "the description states the headcount as 'N people:'"
    return int(m.group(1).replace(",", ""))


def test_cases_are_sourced_and_respectful() -> None:
    assert len(IDS) >= 3 and len(set(IDS)) == len(IDS)
    for c in list_cases():
        assert c.sources and all(str(s.url).startswith("https://") for s in c.sources)
        assert c.deaths > 0 and str(c.deaths) in c.toll
        assert c.dimensions and c.approximations
        assert len(c.description) <= 2000  # what POST /venues/design accepts
        assert c.lesson.endswith(".") and c.what_happened.endswith(".")
        assert (FIXTURES / f"{c.id}.json").exists(), "every case has a scripted designer reply"


@pytest.mark.parametrize("case_id", IDS)
def test_scripted_design_builds_validates_and_routes_everyone(
    case_id: str, registry: Registry
) -> None:
    case = get_case(case_id)
    v = _venue(case_id)
    assert [c.message for c in validate_venue(v).checks if c.severity == "error"] == []
    assert v.total_people() == _headcount(case.description)
    labels = [e.label for e in v.floors[0].exits]
    assert len(set(labels)) == len(labels)
    t1 = run_tier1(v, [], registry, S)
    assert t1.status == "ok" and t1.metrics.agents_not_evacuated == 0


async def test_designer_turns_each_description_into_the_venue() -> None:
    for case_id in IDS:
        llm = FakeLLM({"designer": [_spec(case_id)]})
        out = await design_venue(AgentEnv(llm=llm, audit=False), get_case(case_id).description)
        assert out.status == "built" and out.problems == [] and out.venue is not None
        assert len(llm.calls) == 1, "a good reply needs no repair round"
        assert get_case(case_id).description in llm.calls[0][1][-1]["content"]


# --- the solver's new tools, as the cases use them ------------------------------------------


def test_love_parade_ramp_has_its_narrowing_staircase_and_flows() -> None:
    v = _venue("love_parade_2010")
    f = v.floors[0]
    walk = geo.to_polygon(f.walkable)
    assert walk.bounds == (0, 0, 126, 150), "126 m of tunnel plus the 130 m ramp"
    ramp_x0 = 63 - 13
    fences = [o for o in f.obstacles if o.kind == "fence"]
    west, east = sorted((geo.to_polygon(o.polygon).bounds for o in fences), key=lambda b: b[0])
    gap = east[0] - west[2]
    assert len(fences) == 2 and gap == pytest.approx(10.6, abs=0.01)
    stairs = next(e for e in f.exits if e.label == "Narrow staircase")
    sx, _ = geo.centroid(stairs.polygon)
    assert stairs.width_m == 1.5 and sx == pytest.approx(ramp_x0, abs=0.5), "west side"
    by_label = {z.label: z for z in f.zones}
    festival = next(e.id for e in f.exits if e.label == "Festival grounds")
    assert by_label["Arriving from the west"].exit_ids == [festival]
    leaving = {e.id for e in f.exits if (e.label or "").startswith("Tunnel")}
    assert set(by_label["Leaving the festival"].exit_ids) == leaving


def test_hillsborough_pens_are_split_and_the_tunnel_feeds_both() -> None:
    v = _venue("hillsborough_1989")
    f = v.floors[0]
    fence = next(o for o in f.obstacles if o.id.startswith("divider_"))
    assert geo.to_polygon(fence.polygon).bounds == pytest.approx((12.4, 0, 12.6, 15))
    gates = sorted((geo.centroid(e.polygon)[0], e.width_m) for e in f.exits)
    assert [w for _, w in gates] == [0.8, 0.82] and gates[0][0] < 12.4 < gates[1][0]
    pens = {z.label: geo.to_polygon(z.polygon) for z in f.zones}
    assert pens["Pen 4"].bounds[2] < 12.4 < pens["Pen 3"].bounds[0]
    concourse = pens["Fans from gate C"]
    assert concourse.bounds[3] < -23, "the concourse is beyond the 23 m tunnel"
    # each pen is its own room, but the tunnel mouth opens into both
    walk = geo.to_polygon(f.walkable)
    assert walk.contains(Point(11.5, -0.5)) and walk.contains(Point(13.5, -0.5))


def test_itaewon_crowds_meet_in_the_alley() -> None:
    v = _venue("itaewon_2022")
    f = v.floors[0]
    labels = {e.id: e.label or "" for e in f.exits}
    zones = {z.label: z for z in f.zones}
    down = {labels[x] for x in zones["Upper street crowd"].exit_ids}
    up = {labels[x] for x in zones["Main road crowd"].exit_ids}
    assert down == {"Itaewon-ro east", "Itaewon-ro west"}
    assert up == {"Upper street west", "Upper street east"}
    alley = geo.to_polygon(zones["Alley crowd"].polygon)
    assert alley.bounds[2] - alley.bounds[0] < 3.2 and alley.bounds[1] < -40


def test_headings_restrict_the_instant_estimate(registry: Registry) -> None:
    v = _venue("itaewon_2022")
    t1 = run_tier1(v, [], registry, S)
    plan = t1.extensions["plan"]["groups"]
    f = v.floors[0]
    for z in f.zones:
        if z.exit_ids:
            assert set(plan[z.id]) <= set(z.exit_ids), z.label


def test_unknown_area_or_heading_goes_back_to_the_model() -> None:
    spec = _spec("itaewon_2022")
    spec["zones"] = [
        {**spec["zones"][0], "heading": "Subway"},
        {**spec["zones"][1], "area": "Lane"},
    ]
    _, problems = check_spec(VenueSpec.model_validate(spec))
    assert any("heads for “Subway”" in p and "Itaewon-ro east" in p for p in problems)
    assert any("stands in “Lane”" in p and "“Alley”" in p for p in problems)


def test_a_zone_heading_for_a_missing_exit_is_an_error() -> None:
    v = _venue("itaewon_2022")
    data = v.model_dump()
    data["floors"][0]["zones"][0]["exit_ids"] = ["nowhere"]
    codes = [c.code for c in validate_venue(Venue.model_validate(data)).checks]
    assert "zone_heading_unknown" in codes


def test_passages_need_a_one_level_site() -> None:
    spec = _spec("itaewon_2022")
    spec.update(mode="indoor", building={"storeys": 2, "people_per_floor": 100})
    _, problems = check_spec(VenueSpec.model_validate(spec))
    assert any("one-level sites only" in p for p in problems)


# --- opening a case: designer → project → rule-based test, without more model calls -------


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


async def test_opening_a_case_builds_it_once_and_tests_it_without_the_model(
    case_state: Callable[..., Any],
) -> None:
    st = case_state({"designer": [_spec("love_parade_2010")]})
    out = await open_case(st, "love_parade_2010")
    assert out["status"] == "testing" and out["session_id"]
    venue = st.projects.venue(out["project_id"])
    card = venue.extensions[EXTENSION_KEY]
    assert card["id"] == "love_parade_2010" and card["deaths"] == 21 and card["sources"]
    assert venue.name == "Love Parade 2010 · Duisburg ramp" and venue.event_kind == "festival"
    assert venue.location is not None and venue.location.timezone == "Europe/Berlin"
    await st.sessions.live[out["session_id"]].task
    row = st.sessions.get(out["session_id"])
    assert row.status == "finished", row.error
    assert row.config["agents"] == "rules" and row.config["judge"] is False
    assert {k: row.config[k] for k in CASE_TEST} == CASE_TEST
    assert [agent for agent, _ in st.llm.calls] == ["designer"], "only the venue is designed"
    assert row.summary["baseline_run_id"] and row.summary["judge_text"]
    again = await open_case(st, "love_parade_2010")
    assert again == {
        "project_id": out["project_id"],
        "session_id": out["session_id"],
        "status": "existing",
    }
    assert len(st.llm.calls) == 1, "a case built before is not designed again"


async def test_a_layout_with_problems_opens_in_the_editor(case_state: Callable[..., Any]) -> None:
    bad = _spec("hillsborough_1989")
    bad["zones"] = [{**z, "people": z["people"] * 4} for z in bad["zones"]]
    st = case_state({"designer": [bad, bad]})
    out = await open_case(st, "hillsborough_1989")
    assert out["status"] == "needs_fixes" and out["session_id"] is None and out["problems"]
    assert st.sessions.list_sessions(out["project_id"]) == []


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    with TestClient(create_app(state=state, settings=settings)) as c:
        yield c
    reset_engine()


def test_api_lists_cases_and_explains_a_failed_build(client: TestClient) -> None:
    items = client.get("/api/v1/real_cases").json()
    assert [c["id"] for c in items] == IDS
    assert all(c["project_id"] is None and c["sources"] and c["lesson"] for c in items)
    assert client.post("/api/v1/real_cases/nope/open").status_code == 404
    r = client.post("/api/v1/real_cases/itaewon_2022/open")  # the scripted model has no reply
    assert r.status_code in (422, 503), r.text
    assert client.get("/api/v1/projects").json() == []
