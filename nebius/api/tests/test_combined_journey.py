"""Regression checks at the P2 constrained-plan / P3 editor boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.core.plan import PlanError, plan_data, with_plan
from api.core.venue_ops import PatchError, apply_patch
from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import VenuePatch
from api.models.plan import ObjectConstraint
from api.orchestrator.session import StalePlan
from api.tests.test_api import client as client
from api.tests.test_plan import action
from api.tests.test_plan_api import new


def annotate(client: TestClient, pid: str, target: str, **fields: object):
    return client.post(
        f"/api/v1/projects/{pid}/patch",
        json={"patch": {"ops": [{"op": "set_annotation", "target": target, **fields}]}},
    )


def test_legacy_editor_lock_is_enforced_on_preview_and_direct_patch(client: TestClient) -> None:
    pid = new(client, configure=False)
    assert annotate(client, pid, "E1", locked=True).status_code == 200
    body = {"patch": {"ops": [{"op": "resize", "target": "E1", "width_m": 3}]}}
    preview = client.post(f"/api/v1/projects/{pid}/patch/preview", json=body)
    assert preview.status_code == 200 and not preview.json()["ok"]
    assert "locked" in " ".join(preview.json()["problems"])
    assert client.post(f"/api/v1/projects/{pid}/patch", json=body).status_code == 422
    assert client.get(f"/api/v1/projects/{pid}").json()["current_version"] == 2
    assert annotate(client, pid, "E1", locked=False).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/patch", json=body).status_code == 200


def test_editor_lock_updates_typed_policy_and_preserves_actions(client: TestClient) -> None:
    pid = new(client)
    client.post(
        f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 2, "actions": [action()]}
    )
    before = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert annotate(client, pid, "Z1", locked=True).status_code == 200
    saved = client.get(f"/api/v1/projects/{pid}/plan").json()
    assert saved["plan"]["constraints"]["objects"]["Z1"]["locked"]
    assert saved["plan"]["actions"] == before["plan"]["actions"]
    assert saved["plan_hash"] != before["plan_hash"]
    body = {"patch": {"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]}}
    assert client.post(f"/api/v1/projects/{pid}/patch", json=body).status_code == 422
    assert annotate(client, pid, "Z1", locked=False).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/patch", json=body).status_code == 200
    assert len(client.get(f"/api/v1/projects/{pid}/plan").json()["plan"]["actions"]) == 1


def test_agents_cannot_call_organizer_annotation_ops(client: TestClient) -> None:
    pid = new(client, configure=False)
    annotate(client, pid, "E1", locked=True)
    st = client.app.state.showtime
    patch = VenuePatch.model_validate(
        {"ops": [{"op": "set_annotation", "target": "E1", "locked": False}]}
    )
    with pytest.raises(PatchError, match="organizer"):
        st.projects.apply(pid, patch, author="agent")
    with pytest.raises(PatchError, match="organizer"):
        apply_patch(st.projects.venue(pid), patch, st.registry)
    assert st.projects.get(pid).current_version == 2


def test_legacy_lock_cannot_be_removed_by_whole_venue_replacement(client: TestClient) -> None:
    pid = new(client, configure=False)
    annotate(client, pid, "E1", locked=True)
    st = client.app.state.showtime
    changed = st.projects.venue(pid)
    changed.extensions.pop("plan_annotations")
    changed.floors[0].exits[0].width_m = 3
    with pytest.raises(PlanError):
        st.projects.replace_venue(pid, changed, "Attempt to bypass lock", author="agent")
    assert st.projects.get(pid).current_version == 2


def test_annotation_and_failed_geometry_rollback_together(client: TestClient) -> None:
    pid = new(client)
    original = client.get(f"/api/v1/projects/{pid}/plan").json()
    result = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={
            "patch": {
                "ops": [
                    {"op": "set_annotation", "target": "Z1", "locked": True},
                    {"op": "move", "target": "ghost", "dx": 1},
                ]
            }
        },
    )
    assert result.status_code == 422
    assert client.get(f"/api/v1/projects/{pid}/plan").json() == original


def test_old_preview_cannot_be_applied_to_a_new_version(client: TestClient) -> None:
    pid = new(client, configure=False)
    body = {"patch": {"ops": [{"op": "set_people", "zone_id": "Z1", "people": 10}]}}
    preview = client.post(f"/api/v1/projects/{pid}/patch/preview", json=body).json()
    annotate(client, pid, "E1", provenance={"basis": "measured", "source": "Tape measure"})
    response = client.post(
        f"/api/v1/projects/{pid}/patch", json={**body, "expected_version": preview["base_version"]}
    )
    assert response.status_code == 409 and response.json()["code"] == "plan_version_conflict"
    assert client.get(f"/api/v1/projects/{pid}").json()["current_version"] == 2


def session(st, pid: str, version: int, final):
    with db_session(st.projects.db_url) as db:
        db.add(
            RedTeamSession(
                id="s_combined",
                project_id=pid,
                venue_version=version,
                status="finished",
                summary={"final_venue": final.model_dump(mode="json"), "accepted_fixes": ["F1"]},
            )
        )
        db.commit()
    return "s_combined"


def test_saved_actions_make_session_stale_without_geometry_change(client: TestClient) -> None:
    pid = new(client)
    st = client.app.state.showtime
    sid = session(st, pid, 2, st.projects.venue(pid))
    geo = st.projects.version(pid).venue_hash
    client.post(
        f"/api/v1/projects/{pid}/plan/bundles", json={"expected_version": 2, "actions": [action()]}
    )
    assert st.projects.version(pid).venue_hash == geo
    with pytest.raises(StalePlan):
        st.sessions.apply_final(sid)
    assert st.projects.get(pid).current_version == 3


def test_final_plan_preserves_policy_pruning_for_removed_objects(client: TestClient) -> None:
    pid = new(client)
    st = client.app.state.showtime
    venue = st.projects.venue(pid)
    data = plan_data(venue)
    data.constraints.objects["Z1"] = ObjectConstraint()
    st.projects.replace_venue(pid, with_plan(venue, data), "Add policy")
    final = apply_patch(
        st.projects.venue(pid),
        VenuePatch.model_validate({"ops": [{"op": "remove_zone", "zone_id": "Z1"}]}),
        st.registry,
    ).venue
    sid = session(st, pid, 3, final)
    st.sessions.apply_final(sid)
    saved = st.projects.plan(pid)
    assert "Z1" not in saved.plan.constraints.objects
    assert saved.venue.floors[0].zones == []


@pytest.mark.parametrize("annotations", [[], {"objects": []}, {"objects": {"E1": None}}])
def test_malformed_legacy_annotations_return_validation_error(
    client: TestClient, annotations
) -> None:
    from api.tests.test_scene import room

    venue = room()
    venue.extensions["plan_annotations"] = annotations
    response = client.post("/api/v1/projects", json={"venue": venue.model_dump(mode="json")})
    assert response.status_code == 422
