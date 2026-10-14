"""Organizer annotations: provenance, locks and existing/proposed status (P3-01).

The `set_annotation` op writes provenance into the P2-01 scene metadata and locks plus
existing/proposed status into `plan_annotations`. Agents must never be offered it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.agents.context import op_union, ops_doc
from api.core.annotations import carry_annotations
from api.core.extensions import Registry
from api.core.scene import scene_snapshot
from api.core.venue_ops import PatchError, apply_patch
from api.models import Venue, VenuePatch
from api.orchestrator.session import StalePlan
from api.tests.conformance.suites import check_patch_op
from api.tests.test_api import client as client
from api.tests.test_redteam import state as state


def patch(registry: Registry, venue: Venue, *ops: dict[str, object]) -> Venue:
    return apply_patch(
        venue, VenuePatch.model_validate({"ops": list(ops)}), registry, organizer_edit=True
    ).venue


@pytest.mark.parametrize(
    "params",
    [
        {
            "op": "set_annotation",
            "target": "door_s1",
            "provenance": {"basis": "organizer_confirmed", "source": "Site walk"},
        },
        {"op": "set_annotation", "target": "stage", "locked": True},
        {"op": "set_annotation", "target": "door_s2", "change": "proposed"},
    ],
)
def test_set_annotation_conformance(
    registry: Registry, hall: Venue, params: dict[str, object]
) -> None:
    after = check_patch_op(registry, hall, params)
    # metadata only: what the simulator sees is unchanged
    assert after.model_dump(exclude={"extensions"}) == hall.model_dump(exclude={"extensions"})


def test_annotations_land_where_the_scene_contract_reads_them(
    registry: Registry, hall: Venue
) -> None:
    v = patch(
        registry,
        hall,
        {
            "op": "set_annotation",
            "target": "door_s1",
            "provenance": {"basis": "measured", "source": "Tape measure, 11 Oct"},
            "locked": True,
            "change": "existing",
        },
        {"op": "set_annotation", "target": "door_s2", "change": "proposed"},
    )
    snapshot = scene_snapshot(v, project_id="p", version=2)
    by_id = {o.id: o for o in snapshot.objects}
    assert by_id["door_s1"].provenance.basis == "measured"
    assert by_id["door_s1"].provenance.source == "Tape measure, 11 Oct"
    assert by_id["door_s2"].provenance.basis == "unknown"
    assert v.extensions["plan_annotations"] == {
        "schema_version": 1,
        "objects": {
            "door_s1": {"locked": True, "change": "existing"},
            "door_s2": {"change": "proposed"},
        },
    }


def test_later_annotation_keeps_earlier_fields(registry: Registry, hall: Venue) -> None:
    v = patch(registry, hall, {"op": "set_annotation", "target": "door_s1", "locked": True})
    v = patch(registry, v, {"op": "set_annotation", "target": "door_s1", "change": "existing"})
    assert v.extensions["plan_annotations"]["objects"]["door_s1"] == {
        "locked": True,
        "change": "existing",
    }
    v = patch(registry, v, {"op": "set_annotation", "target": "door_s1", "locked": False})
    assert v.extensions["plan_annotations"]["objects"]["door_s1"]["locked"] is False


@pytest.mark.parametrize(
    ("remove", "target"),
    [
        ({"op": "remove_exit", "exit_id": "door_s2"}, "door_s2"),
        ({"op": "remove_obstacle", "obstacle_id": "foh_desk"}, "foh_desk"),
        ({"op": "remove_zone", "zone_id": "mezzanine"}, "mezzanine"),
    ],
)
def test_removing_an_object_drops_and_undo_restores_its_annotations(
    registry: Registry, hall: Venue, remove: dict[str, object], target: str
) -> None:
    annotated = patch(
        registry,
        hall,
        {
            "op": "set_annotation",
            "target": target,
            "provenance": {"basis": "assumed"},
            "locked": False,
        },
    )
    res = apply_patch(annotated, VenuePatch.model_validate({"ops": [remove]}), registry)
    assert target not in str(res.venue.extensions)
    # no dangling references: the P2-01 scene snapshot still validates
    scene_snapshot(res.venue, project_id="p", version=3)
    undone = apply_patch(
        res.venue, res.inverse, registry, allow_new_errors=True, organizer_edit=True
    ).venue
    assert undone.extensions == annotated.extensions


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"target": "nope", "locked": True}, "Unknown object"),
        ({"target": "door_s1"}, "Nothing to record"),
        ({"target": "audience", "change": "proposed"}, "Only exits and obstacles"),
        ({"target": "door_s1", "provenance": {"basis": "measured"}}, "measurement source"),
    ],
)
def test_invalid_annotations_are_rejected(
    registry: Registry, hall: Venue, params: dict[str, object], message: str
) -> None:
    with pytest.raises(PatchError) as exc:
        patch(registry, hall, {"op": "set_annotation", **params})
    assert message in str(exc.value)


def test_agents_are_never_offered_the_annotation_op(registry: Registry) -> None:
    assert registry.has("PatchOp", "set_annotation")
    assert "set_annotation" not in ops_doc(registry)
    assert "set_annotation" not in str(op_union(registry))
    assert "move" in ops_doc(registry)


def _create(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json={"template_id": "conference_hall_2f"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_annotation_round_trip_through_the_api(client: TestClient) -> None:
    pid = _create(client)
    r = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={
            "patch": {
                "ops": [
                    {
                        "op": "set_annotation",
                        "target": "door_s1",
                        "provenance": {"basis": "organizer_confirmed"},
                        "locked": True,
                    }
                ]
            }
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"]["venue"]["extensions"]["plan_annotations"]["objects"] == {
        "door_s1": {"locked": True}
    }
    scene = client.get(f"/api/v1/projects/{pid}/scene").json()
    door = next(o for o in scene["objects"] if o["id"] == "door_s1")
    assert door["provenance"]["basis"] == "organizer_confirmed"
    assert scene["identity"]["venue_version"] == 2
    assert client.post(f"/api/v1/projects/{pid}/undo").status_code == 200
    scene = client.get(f"/api/v1/projects/{pid}/scene").json()
    door = next(o for o in scene["objects"] if o["id"] == "door_s1")
    assert door["provenance"]["basis"] == "unknown"


def test_preview_returns_the_patched_venue_without_saving(client: TestClient) -> None:
    pid = _create(client)
    r = client.post(
        f"/api/v1/projects/{pid}/patch/preview",
        json={"patch": {"ops": [{"op": "resize", "target": "door_s1", "width_m": 3.5}]}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["base_version"] == 1
    door = next(e for e in body["venue"]["floors"][0]["exits"] if e["id"] == "door_s1")
    assert door["width_m"] == 3.5
    assert "ok" in body["validation"]
    project = client.get(f"/api/v1/projects/{pid}").json()
    assert project["current_version"] == 1


def test_preview_reports_an_invalid_patch_as_data(client: TestClient) -> None:
    pid = _create(client)
    r = client.post(
        f"/api/v1/projects/{pid}/patch/preview",
        json={"patch": {"ops": [{"op": "remove_exit", "exit_id": "missing"}]}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["venue"] is None
    assert any("missing" in p for p in body["problems"])


# --- accepting the red team's fixed plan --------------------------------------------


def test_carry_annotations_keeps_organizer_data_and_marks_additions(
    registry: Registry, hall: Venue
) -> None:
    current = patch(
        registry,
        hall,
        {"op": "set_annotation", "target": "stage", "locked": True},
        {"op": "set_annotation", "target": "foh_desk", "provenance": {"basis": "assumed"}},
        {"op": "set_event", "duration_h": 4},
    )
    # the fixed plan was copied at session start: no annotations, desk removed, exit added
    fixed = patch(
        registry,
        hall.model_copy(update={"name": "Old name"}),
        {"op": "remove_obstacle", "obstacle_id": "foh_desk"},
        {"op": "add_exit", "floor_id": "F0", "id": "door_e1", "wall": "east", "width_m": 2.0},
    )
    out = carry_annotations(current, fixed)
    assert out.name == current.name
    assert out.extensions["event"] == {"duration_h": 4}
    assert out.extensions["plan_annotations"]["objects"] == {
        "stage": {"locked": True},
        "door_e1": {"change": "proposed"},
    }
    assert "scene_metadata" not in out.extensions  # the desk's entry went with the desk
    scene_snapshot(out, project_id="p", version=3)
    assert out.model_dump(exclude={"extensions", "name"}) == fixed.model_dump(
        exclude={"extensions", "name"}
    )


def _fake_session(
    state: Any, project_id: str, version: int, final: Venue, accepted: tuple[str, ...] = ("F1",)
) -> str:
    from api.db.models import RedTeamSession
    from api.db.session import db_session

    with db_session() as db:
        db.add(
            RedTeamSession(
                id="s_test",
                project_id=project_id,
                venue_version=version,
                status="finished",
                config={},
                summary={
                    "final_venue": final.model_dump(mode="json"),
                    "accepted_fixes": list(accepted),
                },
            )
        )
        db.commit()
    return "s_test"


def test_apply_final_refuses_constraints_changed_during_the_session(
    state: Any, registry: Registry
) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    tested = state.projects.venue(p.id)
    fixed = patch(
        registry,
        tested,
        {"op": "add_exit", "floor_id": "F0", "id": "door_e1", "wall": "east", "width_m": 2.0},
    )
    sid = _fake_session(state, p.id, 1, fixed)
    # the organizer locks the stage while the session runs (metadata only)
    state.projects.apply(
        p.id,
        VenuePatch.model_validate(
            {"ops": [{"op": "set_annotation", "target": "stage", "locked": True}]}
        ),
    )
    with pytest.raises(StalePlan):
        state.sessions.apply_final(sid)
    assert state.projects.get(p.id).current_version == 2


def test_apply_final_refuses_a_plan_for_an_older_geometry(state: Any, registry: Registry) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    sid = _fake_session(state, p.id, 1, state.projects.venue(p.id))
    state.projects.apply(
        p.id,
        VenuePatch.model_validate({"ops": [{"op": "resize", "target": "door_s1", "width_m": 3}]}),
    )
    with pytest.raises(StalePlan):
        state.sessions.apply_final(sid)
    assert state.projects.get(p.id).current_version == 2


def test_apply_final_refuses_a_session_without_kept_fixes(state: Any) -> None:
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    sid = _fake_session(state, p.id, 1, state.projects.venue(p.id), accepted=())
    with pytest.raises(ValueError, match="nothing to apply"):
        state.sessions.apply_final(sid)
    assert state.projects.get(p.id).current_version == 1  # no identical version is saved


def test_text_edit_reports_an_unavailable_model_as_503(client: TestClient) -> None:
    # the fake LLM has no venue script: the agent is unavailable, not a server crash
    pid = _create(client)
    r = client.post(
        f"/api/v1/projects/{pid}/edit", json={"text": "widen the doors", "apply": False}
    )
    assert r.status_code == 503, r.text
    assert r.json()["code"] == "llm_unavailable"
