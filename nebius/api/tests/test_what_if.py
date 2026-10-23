"""The AI chooses and composes the what-if sweep; the standard six only without a model."""

from __future__ import annotations

from typing import Any

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.agents.what_if import design_what_ifs
from api.core.extensions import Registry
from api.core.scenarios import catalogue_for
from api.core.templates import get_template
from api.tests.test_api import client  # noqa: F401 - shared fixture


async def test_the_ai_picks_library_scenarios_and_composes_its_own(registry: Registry) -> None:
    venue = get_template("conference_hall_2f")
    exit_id = venue.floors[0].exits[0].id
    zone_id = venue.floors[0].zones[0].id
    llm = FakeLLM(
        {
            "what_if": {
                "scenarios": [
                    {"use": "plan"},
                    {"use": "gate"},
                    {"use": "plan"},  # a repeat is dropped
                    {
                        "use": None,
                        "title": f"Late crowd at {zone_id}",
                        "why": f"{zone_id} fills late and {exit_id} is its nearest door.",
                        "category": "crowd",
                        "events": [
                            {"type": "surge", "zone_id": zone_id, "extra_people": 80, "at_s": 30}
                        ],
                    },
                ]
            }
        }
    )
    library = catalogue_for(venue)
    plan = await design_what_ifs(AgentEnv(llm=llm, project_id=None), registry, venue, library)
    ids = [r.spec.id for r in plan.scenarios]
    assert ids[:2] == ["plan", "gate"] and len(ids) == 3
    own = plan.scenarios[2]
    assert own.spec.id.startswith("ai_") and own.built is not None
    assert own.built.events[0].type == "surge"
    assert own.spec.title.startswith("Late crowd") and own.spec.category == "crowd"


async def test_wrong_references_are_sent_back_and_then_left_out(registry: Registry) -> None:
    venue = get_template("school_wing")
    bad = {
        "use": None,
        "title": "Ghost door",
        "why": "x",
        "category": "access",
        "events": [{"type": "block_exit", "exit_id": "no_such_exit", "at_s": 0}],
    }
    answers: list[Any] = [
        {"scenarios": [{"use": "plan"}, bad]},
        {"scenarios": [{"use": "plan"}, bad]},  # still wrong after the repair round
    ]
    llm = FakeLLM({"what_if": answers})
    plan = await design_what_ifs(
        AgentEnv(llm=llm, project_id=None), registry, venue, catalogue_for(venue)
    )
    assert [r.spec.id for r in plan.scenarios] == ["plan"]
    repair = llm.calls[-1][1][-1]["content"]
    assert "no_such_exit" in repair or len(llm.calls) >= 2


def test_the_sweep_route_lets_the_ai_choose(client: Any) -> None:  # noqa: F811
    st = client.app.state.showtime
    st.llm.script["what_if"] = {"scenarios": [{"use": "plan"}, {"use": "plus20"}]}
    pid = client.post("/api/v1/projects", json={"template_id": "school_wing"}).json()["id"]
    rec = client.post(f"/api/v1/projects/{pid}/sweep").json()
    assert rec["chosen_by"] == "ai" and rec["scenarios"] == ["plan", "plus20"]
    st.llm.script.pop("what_if")
    rec = client.post(f"/api/v1/projects/{pid}/sweep").json()
    assert rec["chosen_by"] == "standard" and len(rec["scenarios"]) == 6
    rec = client.post(f"/api/v1/projects/{pid}/sweep", json={"scenarios": ["gate"]}).json()
    assert rec["chosen_by"] == "you" and rec["scenarios"] == ["gate"]
