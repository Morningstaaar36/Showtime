"""Persistence, bundle rollback, concurrency, runs and exact selected plan tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.core.plan import PlanConflict, PlanError, transition_issues
from api.core.venue_ops import PatchError
from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import Attack
from api.models.plan import PlanSnapshot
from api.orchestrator.projects import ProjectService
from api.tests.test_api import client as client
from api.tests.test_plan import action, organizer_plan
from api.tests.test_scene import room


def new(client: TestClient, *, configure: bool = True) -> str:
    response = client.post("/api/v1/projects", json={"venue": room().model_dump(mode="json")})
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    if configure:
        result = client.put(
            f"/api/v1/projects/{pid}/plan",
            json={"expected_version": 1, "plan": organizer_plan().model_dump(mode="json")},
        )
        assert result.status_code == 200, result.text
    return pid


def test_plan_history_legacy_and_schemas(client: TestClient) -> None:
    pid = new(client)
    current = PlanSnapshot.model_validate(client.get(f"/api/v1/projects/{pid}/plan").json())
    assert current.version == 2 and current.configured
    old = client.get(f"/api/v1/projects/{pid}/plan?version=1").json()
    assert not old["configured"] and old["plan"]["actions"] == []
    assert client.get(f"/api/v1/projects/{pid}/plan?version=0").status_code == 422
    assert client.get("/api/v1/projects/missing/plan").status_code == 404
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert {"PlanSnapshot", "PlanBundle", "PlanUpdate", "PlanEvidence"} <= schemas.keys()


def test_atomic_bundle_rejection_and_preview(client: TestClient) -> None:
    pid = new(client)
    before = client.get(f"/api/v1/projects/{pid}").json()
    bundle = {
        "expected_version": 2,
        "patch": {
            "ops": [
                {"op": "set_people", "zone_id": "Z1", "people": 10},
                {"op": "move", "target": "ghost", "dx": 1},
            ]
        },
        "actions": [action()],
    }
    preview = client.post(f"/api/v1/projects/{pid}/plan/bundles/preview", json=bundle)
    assert preview.status_code == 200 and not preview.json()["valid"]
    assert preview.json()["candidate"] is None
    assert client.post(f"/api/v1/projects/{pid}/plan/bundles", json=bundle).status_code == 422
    assert client.get(f"/api/v1/projects/{pid}").json()["version"] == before["version"]
    assert len(client.get(f"/api/v1/projects/{pid}/versions").json()) == 2


def test_failed_resource_allocation_rolls_back_geometry(client: TestClient) -> None:
    pid = new(client)
    bundle = {
        "expected_version": 2,
        "patch": {"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]},
        "actions": [action(quantity=3)],
    }
    response = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=bundle)
    assert response.status_code == 422
    assert response.json()["details"]["issues"][0]["code"] == "resource_overallocated"
    snapshot = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert snapshot["version"] == 2 and snapshot["plan"]["actions"] == []
    assert snapshot["venue"]["floors"][0]["zones"][0]["people"] == 20


def test_save_reload_undo_redo_export_and_rerun(client: TestClient) -> None:
    pid = new(client)
    st = client.app.state.showtime
    original_job = st.runs.build_job(st.projects.venue(pid), tier=2, seed=7)
    body = {"expected_version": 2, "actions": [action()]}
    preview = client.post(f"/api/v1/projects/{pid}/plan/bundles/preview", json=body).json()
    assert preview["valid"]
    response = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=body)
    assert response.status_code == 200, response.text
    saved = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert saved["version"] == 3
    assert saved["plan_hash"] == preview["candidate"]["plan_hash"]
    again = ProjectService(st.registry, st.projects.db_url)
    assert again.plan(pid).plan == PlanSnapshot.model_validate(saved).plan
    job = st.runs.build_job(again.venue(pid), tier=2, seed=7)
    assert job.request.venue_hash == original_job.request.venue_hash
    assert job.request.run_id != original_job.request.run_id
    assert len(job.events) == 1 and job.events[0]["delay_s"] == 10
    assert job.request.extensions["plan_hash"] == saved["plan_hash"]
    client.post(f"/api/v1/projects/{pid}/undo")
    assert client.get(f"/api/v1/projects/{pid}/plan").json()["plan"]["actions"] == []
    client.post(f"/api/v1/projects/{pid}/redo")
    assert client.get(f"/api/v1/projects/{pid}/plan").json()["plan_hash"] == saved["plan_hash"]
    imported = again.import_zip(again.export_zip(pid))
    assert again.plan(imported.id).plan_hash == saved["plan_hash"]
    assert len(st.runs.build_job(again.venue(imported.id), tier=2).events) == 1


def test_version_conflict_and_commit_guard(client: TestClient) -> None:
    pid = new(client)
    bundle = {"expected_version": 1, "actions": [action()]}
    for endpoint in ["bundles", "bundles/preview"]:
        assert (
            client.post(f"/api/v1/projects/{pid}/plan/{endpoint}", json=bundle).status_code == 409
        )
    response = client.put(f"/api/v1/projects/{pid}/plan", json={"expected_version": 1, "plan": {}})
    assert response.status_code == 409
    projects = client.app.state.showtime.projects
    candidate = projects.venue(pid)
    with pytest.raises(PlanConflict):
        projects._save_plan(pid, candidate, 1, "stale write", "agent")
    assert projects.get(pid).current_version == 2


def test_new_exit_requires_status_permission_and_construction(client: TestClient) -> None:
    pid = new(client)
    patch = {
        "ops": [
            {
                "op": "add_exit",
                "floor_id": "F0",
                "id": "E2",
                "wall": "west",
                "center": 4,
                "width_m": 2,
            }
        ]
    }
    plain = client.post(f"/api/v1/projects/{pid}/patch", json={"patch": patch})
    assert plain.status_code == 422
    data = organizer_plan().model_dump(mode="json")
    data["constraints"]["allow_construction"] = True
    data["constraints"]["approvals"] = {"build": {"status": "pending"}}
    client.put(f"/api/v1/projects/{pid}/plan", json={"expected_version": 2, "plan": data})
    bundle = {
        "expected_version": 3,
        "patch": patch,
        "new_objects": {
            "E2": {
                "origin": "proposed",
                "placement": "fixed",
                "locked": True,
                "required_approvals": ["build"],
            }
        },
    }
    denied = client.post(f"/api/v1/projects/{pid}/plan/bundles/preview", json=bundle)
    assert not denied.json()["valid"]
    assert any(i["code"] == "approval_required" for i in denied.json()["issues"])
    data["constraints"]["approvals"]["build"] = {
        "status": "approved",
        "source": "Organizer supplied permit record",
        "recorded_by": "test organizer",
    }
    response = client.put(
        f"/api/v1/projects/{pid}/plan", json={"expected_version": 3, "plan": data}
    )
    assert response.status_code == 200, response.text
    bundle["expected_version"] = 4
    applied = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=bundle)
    assert applied.status_code == 200, applied.text
    assert len(applied.json()["version"]["venue"]["floors"][0]["exits"]) == 2


def test_direct_edits_and_replacements_cannot_bypass_locks(client: TestClient) -> None:
    pid = new(client)
    data = organizer_plan().model_dump(mode="json")
    data["constraints"]["objects"]["Z1"] = {"locked": True}
    client.put(f"/api/v1/projects/{pid}/plan", json={"expected_version": 2, "plan": data})
    response = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={
            "patch": {"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]},
            "allow_new_errors": True,
        },
    )
    assert response.status_code == 422
    projects = client.app.state.showtime.projects
    changed = projects.venue(pid).model_copy(deep=True)
    changed.floors[0].zones[0].people = 10
    with pytest.raises(PlanError):
        projects.replace_venue(pid, changed, "bypass", author="agent")
    original = projects.venue(pid)
    changed = original.model_copy(deep=True)
    changed.extensions.pop("organizer_plan")
    assert any(i.code == "policy_changed" for i in transition_issues(original, changed))


def test_new_object_policy_cannot_unlock_existing_object(client: TestClient) -> None:
    pid = new(client)
    response = client.post(
        f"/api/v1/projects/{pid}/plan/bundles",
        json={
            "expected_version": 2,
            "new_objects": {"E1": {"placement": "movable"}},
            "actions": [action()],
        },
    )
    assert response.status_code == 422
    assert response.json()["details"]["issues"][0]["code"] == "policy_changed"


def test_runs_use_saved_actions_and_mark_evidence_stale(client: TestClient) -> None:
    pid = new(client)
    client.post(
        f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 2, "actions": [action()]}
    )
    response = client.post("/api/v1/runs", json={"project_id": pid, "tier": 2, "seed": 42})
    assert response.status_code == 202, response.text
    run = response.json()
    assert run["request"]["extensions"]["events"][0]["type"] == "staggered_release"
    evidence = client.get(f"/api/v1/projects/{pid}/plan/evidence").json()
    assert evidence["runs"][0]["applicability"] == "current"
    client.post(
        f"/api/v1/projects/{pid}/patch",
        json={"patch": {"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]}},
    )
    evidence = client.get(f"/api/v1/projects/{pid}/plan/evidence").json()
    assert evidence["runs"][0]["applicability"] == "stale"
    client.post(f"/api/v1/projects/{pid}/undo")
    assert (
        client.get(f"/api/v1/projects/{pid}/plan/evidence").json()["runs"][0]["applicability"]
        == "current"
    )


def test_unallocated_operations_and_short_coverage_cannot_start_runs(client: TestClient) -> None:
    pid = new(client)
    response = client.post(
        "/api/v1/runs",
        json={"project_id": pid, "tier": 2, "events": [{"type": "one_way", "exit_id": "E1"}]},
    )
    assert response.status_code == 422 and response.json()["code"] == "invalid_plan"
    short = action(event={"type": "one_way", "exit_id": "E1", "at_s": 10})
    response = client.post(
        f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 2, "actions": [short]}
    )
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/runs", json={"project_id": pid, "tier": 2})
    assert response.status_code == 422
    assert response.json()["details"]["issues"][0]["code"] == "action_coverage_too_short"


def test_agent_applies_ops_atomically_and_persists_legacy_measures(client: TestClient) -> None:
    pid = new(client, configure=False)
    st = client.app.state.showtime
    venue = st.projects.venue(pid)
    with pytest.raises(PatchError):
        st.sessions._apply_ops(
            venue,
            [
                {"op": "set_people", "zone_id": "Z1", "people": 10},
                {"op": "move", "target": "ghost", "dx": 1},
            ],
            None,
        )
    assert venue.total_people() == 20
    row = RedTeamSession(
        id="session_test",
        project_id=pid,
        venue_version=1,
        status="finished",
        summary={
            "final_venue": venue.model_dump(mode="json"),
            "accepted_fixes": ["F1"],
            "measures": [{"type": "staggered_release", "zone_id": "Z1", "delay_s": 10}],
        },
    )
    with db_session(st.projects.db_url) as db:
        db.add(row)
        db.commit()
    st.sessions.apply_final(row.id)
    saved = st.projects.plan(pid)
    assert not saved.plan.enforce_constraints  # legacy measures make no staff feasibility claim
    assert saved.plan.actions[0].event.type == "staggered_release"
    assert len(st.runs.build_job(saved.venue, tier=2).events) == 1
    with pytest.raises(PlanConflict):
        st.sessions.apply_final(row.id)


def test_whole_replacement_respects_allowed_operations(client: TestClient) -> None:
    pid = new(client)
    data = organizer_plan().model_dump(mode="json")
    data["constraints"]["allowed_ops"] = ["set_people"]
    client.put(f"/api/v1/projects/{pid}/plan", json={"expected_version": 2, "plan": data})
    st = client.app.state.showtime
    candidate = st.projects.venue(pid).model_copy(deep=True)
    candidate.floors[0].zones[0].polygon = [
        (x + 0.5, y) for x, y in candidate.floors[0].zones[0].polygon
    ]
    with pytest.raises(PlanError):
        st.projects.replace_venue(pid, candidate, "bypass operation policy")


def test_attacks_cannot_smuggle_unallocated_plan_actions(client: TestClient) -> None:
    pid = new(client)
    attack = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Unallocated marshal",
            "events": [{"type": "one_way", "exit_id": "E1"}],
            "inspired_by": {
                "incident": "synthetic test",
                "source_url": "https://example.test/incident",
            },
        }
    )
    response = client.post(
        "/api/v1/runs",
        json={"project_id": pid, "tier": 2, "attack": attack.model_dump(mode="json")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["issues"][0]["code"] == "structured_actions_required"


def test_atomic_action_replacement_changes_evidence_without_geometry_change(
    client: TestClient,
) -> None:
    pid = new(client)
    client.post(
        f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 2, "actions": [action()]}
    )
    before = client.get(f"/api/v1/projects/{pid}/plan").json()
    response = client.post("/api/v1/runs", json={"project_id": pid, "tier": 2})
    assert response.status_code == 202, response.text
    body = {"expected_version": 3, "source": "rules", "replace_actions": [action(start=30, end=50)]}
    response = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=body)
    assert response.status_code == 200, response.text
    after = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert after["venue"]["floors"] == before["venue"]["floors"]
    assert after["plan_hash"] != before["plan_hash"]
    assert len(after["plan"]["actions"]) == 1
    assert after["plan"]["actions"][0]["source"] == "rules"
    assert (
        client.get(f"/api/v1/projects/{pid}/plan/evidence").json()["runs"][0]["applicability"]
        == "stale"
    )
    st = client.app.state.showtime
    assert st.runs.build_job(st.projects.venue(pid), tier=2).events[0]["at_s"] == 30


def test_remove_geometry_and_its_action_in_one_bundle(client: TestClient) -> None:
    pid = new(client, configure=False)
    response = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={
            "patch": {
                "ops": [
                    {
                        "op": "add_obstacle",
                        "floor_id": "F0",
                        "id": "B1",
                        "kind": "barrier",
                        "polygon": [[4, 2], [4.2, 2], [4.2, 4], [4, 4]],
                    }
                ]
            }
        },
    )
    assert response.status_code == 200, response.text
    data = organizer_plan(
        actions=[
            {
                "action_id": "monitor_B1",
                "target_ids": ["B1"],
                "resources": [{"resource_id": "radios", "quantity": 1}],
            }
        ]
    ).model_dump(mode="json")
    data["constraints"]["objects"]["B1"] = {"placement": "movable"}
    response = client.put(
        f"/api/v1/projects/{pid}/plan", json={"expected_version": 2, "plan": data}
    )
    assert response.status_code == 200, response.text
    body = {
        "expected_version": 3,
        "patch": {"ops": [{"op": "remove_obstacle", "obstacle_id": "B1"}]},
    }
    rejected = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=body)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "invalid_plan"
    assert client.get(f"/api/v1/projects/{pid}/plan").json()["version"] == 3
    body["remove_action_ids"] = ["monitor_B1"]
    applied = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=body)
    assert applied.status_code == 200, applied.text
    saved = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert saved["plan"]["actions"] == []
    assert saved["venue"]["floors"][0]["obstacles"] == []
    assert "B1" not in saved["plan"]["constraints"]["objects"]


def test_conflicting_or_missing_action_edits_do_not_save(client: TestClient) -> None:
    pid = new(client)
    client.post(
        f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 2, "actions": [action()]}
    )
    invalid = [
        {"remove_action_ids": ["ghost"]},
        {"replace_actions": [action("ghost")]},
        {"replace_actions": [action()], "remove_action_ids": ["hold"]},
    ]
    for changes in invalid:
        response = client.post(
            f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 3, **changes}
        )
        assert response.status_code == 422, response.text
    snapshot = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert snapshot["version"] == 3 and len(snapshot["plan"]["actions"]) == 1
