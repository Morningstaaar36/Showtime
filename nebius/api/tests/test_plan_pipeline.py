"""Complete typed fixes use the same validation in agents, API, runs and acceptance."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.agents.blue_team import blue_team, check_fix
from api.core.extensions import Registry
from api.core.plan import (
    PlanError,
    apply_fix_bundle,
    plan_data,
    plan_hash,
    validate_plan,
    with_plan,
)
from api.models import Attack, Fix
from api.models.plan import PlanAction
from api.tests.test_api import client as client
from api.tests.test_plan import action, configured
from api.tests.test_plan_api import new


def incident() -> Attack:
    return Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Incoming crowd",
            "events": [{"type": "counterflow", "at_s": 0, "exit_id": "E1", "extra_people": 10}],
            "inspired_by": {
                "incident": "Synthetic software fixture",
                "source_url": "https://example.org/fixture",
            },
        }
    )


def typed_fix(**fields: object) -> Fix:
    return Fix.model_validate(
        {
            "fix_id": "F1",
            "for_attack": "A1",
            "title": "Staffed response",
            "actions": [action()],
            **fields,
        }
    )


def test_agent_api_and_run_share_exact_bundle(client: TestClient) -> None:
    pid = new(client)
    st = client.app.state.showtime
    before = st.projects.venue(pid)
    fix = typed_fix()
    expected = apply_fix_bundle(before, fix, st.registry)
    response = client.post(
        f"/api/v1/projects/{pid}/plan/bundles/preview",
        json={"expected_version": 2, "actions": [action()], "source": "agent"},
    )
    assert response.status_code == 200 and response.json()["valid"], response.text
    assert response.json()["candidate"]["plan_hash"] == plan_hash(expected)
    assert st.projects.plan(pid).version == 2
    candidate_job = st.runs.build_job(before, tier=2, fix=fix)
    assert candidate_job.request.extensions["plan_hash"] == plan_hash(expected)
    assert len(candidate_job.events) == 1
    saved = client.post(
        f"/api/v1/projects/{pid}/plan/bundles",
        json={"expected_version": 2, "actions": [action()], "source": "agent"},
    )
    assert saved.status_code == 200, saved.text
    final_job = st.runs.build_job(st.projects.venue(pid), tier=2)
    assert final_job.events == candidate_job.events
    assert (
        final_job.request.extensions["plan_hash"] == candidate_job.request.extensions["plan_hash"]
    )


async def test_blue_team_produces_staffed_actions(registry: Registry) -> None:
    from api.core.settings import Settings
    from api.core.tier1 import run_tier1

    venue = configured()
    draft = {
        "title": "Hold zone",
        "actions": [action()],
        "ops": [],
        "operational": [],
        "rationale": "A staffed test.",
    }
    fixes = await blue_team(
        AgentEnv(llm=FakeLLM({"blue_team": {"fixes": [draft]}}), audit=False),
        registry,
        venue,
        incident(),
        run_tier1(venue, [], registry, Settings()),
        1,
        "F",
    )
    assert len(fixes) == 1
    assert fixes[0].actions[0].resources[0].resource_id == "stewards"
    assert plan_data(apply_fix_bundle(venue, fixes[0], registry)).actions[0].source == "agent"


async def test_blue_team_can_report_no_feasible_fix(registry: Registry) -> None:
    from api.core.settings import Settings
    from api.core.tier1 import run_tier1

    venue = configured()
    fixes = await blue_team(
        AgentEnv(llm=FakeLLM({"blue_team": {"fixes": []}}), audit=False),
        registry,
        venue,
        incident(),
        run_tier1(venue, [], registry, Settings()),
        1,
        "F",
    )
    assert fixes == []


@pytest.mark.parametrize(
    "changes, code",
    [
        ({"quantity": 3}, "resource_overallocated"),
        ({"depends_on": ["missing"]}, "missing_dependency"),
        ({"required_approvals": ["missing"]}, "approval_required"),
        ({"resources": []}, "staff_required"),
    ],
)
def test_agent_bundle_cannot_bypass_organizer_policy(
    registry: Registry, changes: dict, code: str
) -> None:
    venue = configured()
    with pytest.raises(PlanError) as exc:
        apply_fix_bundle(venue, typed_fix(actions=[action(**changes)]), registry)
    assert code in {i.code for i in exc.value.issues}
    assert not plan_data(venue).actions
    assert check_fix(registry, venue, [], [], actions=[action(**changes)])


def test_agent_cannot_annotate_or_unlock_in_bundle(client: TestClient) -> None:
    pid = new(client)
    body = {
        "expected_version": 2,
        "source": "agent",
        "patch": {"ops": [{"op": "set_annotation", "target": "E1", "locked": False}]},
    }
    result = client.post(f"/api/v1/projects/{pid}/plan/bundles/preview", json=body)
    assert result.status_code == 200
    assert not result.json()["valid"]
    assert result.json()["issues"][0]["code"] == "organizer_only"
    assert client.get(f"/api/v1/projects/{pid}/plan").json()["version"] == 2


def test_replaced_action_is_simulated_once(client: TestClient) -> None:
    pid = new(client)
    st = client.app.state.showtime
    assert (
        client.post(
            f"/api/v1/projects/{pid}/plan/bundles",
            json={"expected_version": 2, "actions": [action()]},
        ).status_code
        == 200
    )
    fix = typed_fix(
        actions=[],
        replace_actions=[
            action(
                start=0,
                end=40,
                event={"type": "staggered_release", "zone_id": "Z1", "at_s": 0, "delay_s": 40},
            )
        ],
    )
    job = st.runs.build_job(st.projects.venue(pid), tier=2, fix=fix)
    assert len(job.events) == 1 and job.events[0]["delay_s"] == 40
    assert plan_data(st.projects.venue(pid)).actions[0].event.model_dump()["delay_s"] == 10


def test_budget_requires_costs_and_rejects_excess(registry: Registry) -> None:
    venue = configured()
    data = plan_data(venue)
    data.constraints.budget_limit = 10
    data.actions = [PlanAction.model_validate(action())]
    with pytest.raises(PlanError, match="declared costs"):
        validate_plan(with_plan(venue, data), registry)
    data.actions[0].estimated_cost = 11
    with pytest.raises(PlanError, match="exceeds"):
        validate_plan(with_plan(venue, data), registry)
    data.actions[0].estimated_cost = 10
    validate_plan(with_plan(venue, data), registry)


def test_fixed_bundle_is_preserved_by_session_acceptance(client: TestClient) -> None:
    from api.db.models import RedTeamSession
    from api.db.session import db_session
    from api.orchestrator.session import SessionManager

    pid = new(client)
    st = client.app.state.showtime
    fixed = apply_fix_bundle(st.projects.venue(pid), typed_fix(), st.registry)
    with db_session(st.settings.db_url) as db:
        db.add(
            RedTeamSession(
                id="typed_accept",
                project_id=pid,
                venue_version=2,
                status="finished",
                summary={
                    "final_venue": fixed.model_dump(mode="json"),
                    "accepted_fixes": ["F1"],
                    "measures": [],
                },
            )
        )
        db.commit()
    SessionManager(st).apply_final("typed_accept")
    accepted = st.projects.venue(pid)
    assert plan_hash(accepted) == plan_hash(fixed)
    assert plan_data(accepted).actions[0].resources[0].quantity == 1
    assert st.runs.build_job(accepted, tier=2).events[0]["type"] == "staggered_release"


def test_provenance_does_not_change_physical_identity_but_policy_does() -> None:
    venue = configured()
    original = plan_hash(venue)
    venue.extensions["scene_metadata"] = {
        "schema_version": 1,
        "objects": {"E1": {"status": "measured", "source": "site survey"}},
    }
    venue.extensions["plan_annotations"] = {
        "schema_version": 1,
        "objects": {"E1": {"change": "existing"}},
    }
    assert plan_hash(venue) == original
    data = plan_data(venue)
    data.constraints.objects["E1"].locked = True
    assert plan_hash(with_plan(venue, data)) != original


def test_structured_actions_cannot_run_before_intervention(client: TestClient) -> None:
    pid = new(client)
    st = client.app.state.showtime
    with pytest.raises(PlanError, match="before the intervention"):
        st.runs.build_job(st.projects.venue(pid), tier=2, fix=typed_fix(), intervention_at_s=20)
