"""Choosing among tested fixes (P3-03): accept every kept fix, or only the chosen ones.

A subset is rebuilt from the tested venue with only the chosen fix bundles. It was never
tested as a whole, so the version message and the session's `applied` record say so.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.core.plan import apply_fix_bundle, plan_data, plan_hash
from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import Fix, Venue
from api.orchestrator.session import NOT_TESTED_TOGETHER
from api.tests.test_api import client as client

EAST_DOOR = {
    "fix_id": "F1_R1",
    "for_attack": "A1",
    "title": "Open a 2 m exit on the east side",
    "patch": {
        "ops": [
            {
                "op": "add_exit",
                "floor_id": "F0",
                "id": "door_e1",
                "wall": "east",
                "center": 8,
                "width_m": 2.0,
            }
        ]
    },
    "extensions": {"generated_by": "rules"},
}
WIDER_DOOR = {
    "fix_id": "F2",
    "for_attack": "A2",
    "title": "Widen South door 2",
    "patch": {"ops": [{"op": "resize", "target": "door_s2", "width_m": 3.0}]},
}
MARSHALS = {
    "fix_id": "F3",
    "for_attack": "A3",
    "title": "Marshals send people to the east door",
    "operational": [
        {
            "type": "marshal_redirect",
            "from_exit_id": "door_s1",
            "to_exit_id": "door_e1",
            "fraction": 0.4,
            "at_s": 20,
        }
    ],
}
REJECTED = {
    "fix_id": "F4",
    "for_attack": "A1",
    "title": "Narrow South door 1",
    "patch": {"ops": [{"op": "resize", "target": "door_s1", "width_m": 1.0}]},
}


def _session(client: TestClient) -> tuple[str, str]:
    """A finished session that kept three fixes (applied in order, as the session does)."""
    st = client.app.state.showtime  # type: ignore[attr-defined]
    pid = client.post("/api/v1/projects", json={"template_id": "conference_hall_2f"}).json()["id"]
    venue = st.projects.venue(pid)
    kept = [Fix.model_validate(f) for f in (EAST_DOOR, WIDER_DOOR, MARSHALS)]
    final = venue
    for fx in kept:
        final = apply_fix_bundle(final, fx, st.registry)
    with db_session(st.projects.db_url) as db:
        db.add(
            RedTeamSession(
                id="s_choose",
                project_id=pid,
                venue_version=1,
                status="finished",
                config={},
                summary={
                    "final_venue": final.model_dump(mode="json"),
                    "accepted_fixes": [f.fix_id for f in kept],
                    "fixes": [
                        Fix.model_validate(f).model_dump(mode="json")
                        for f in (EAST_DOOR, REJECTED, WIDER_DOOR, MARSHALS)
                    ],
                    "measures": [e.model_dump() for f in kept for e in f.operational],
                },
            )
        )
        db.commit()
    return pid, "s_choose"


def _venue(client: TestClient, pid: str) -> Venue:
    return client.app.state.showtime.projects.venue(pid)  # type: ignore[attr-defined, no-any-return]


def _exit(v: Venue, exit_id: str) -> Any:
    return next((e for f in v.floors for e in f.exits if e.id == exit_id), None)


def test_all_kept_fixes_save_the_venue_that_was_tested_together(client: TestClient) -> None:
    pid, sid = _session(client)
    r = client.post(f"/api/v1/sessions/{sid}/apply")  # no body: every kept fix
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"]["version"] == 2
    assert out["applied"]["fix_ids"] == ["F1_R1", "F2", "F3"]
    assert out["applied"]["tested_together"] is True and out["applied"]["note"] is None
    assert out["version"]["message"].startswith("Applied red-team plan (3 fixes): F1_R1")
    v = _venue(client, pid)
    assert _exit(v, "door_e1") is not None and _exit(v, "door_s2").width_m == 3.0
    assert [a.event.type for a in plan_data(v).actions if a.event] == ["marshal_redirect"]
    assert out["applied"]["plan_hash"] == plan_hash(v)
    # the record stays with the session for Your plan and the exports
    applied = client.get(f"/api/v1/sessions/{sid}").json()["summary"]["applied"]
    assert applied == [out["applied"]]


def test_a_subset_saves_only_the_chosen_fixes_and_says_it_was_not_tested(
    client: TestClient,
) -> None:
    pid, sid = _session(client)
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": ["F2"]})
    assert r.status_code == 200, r.text
    out = r.json()
    v = _venue(client, pid)
    assert _exit(v, "door_s2").width_m == 3.0
    assert _exit(v, "door_e1") is None  # the east door was left out
    assert plan_data(v).actions == []  # so were the marshals
    assert out["applied"] == {
        **out["applied"],
        "fix_ids": ["F2"],
        "tested_together": False,
        "note": NOT_TESTED_TOGETHER,
        "plan_hash": plan_hash(v),
    }
    message = out["version"]["message"]
    assert message.startswith("Applied 1 of 3 red-team fixes: F2 (Widen South door 2).")
    assert message.endswith(NOT_TESTED_TOGETHER)


def test_a_subset_is_applied_in_the_order_the_session_kept_it(client: TestClient) -> None:
    pid, sid = _session(client)
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": ["F3", "F1_R1"]})
    assert r.status_code == 200, r.text
    assert r.json()["applied"]["fix_ids"] == ["F1_R1", "F3"]
    v = _venue(client, pid)
    assert _exit(v, "door_e1") is not None and _exit(v, "door_s2").width_m == 2.5
    assert [a.event.to_exit_id for a in plan_data(v).actions if a.event] == ["door_e1"]  # type: ignore[attr-defined]
    # the new opening stays marked as proposed construction
    assert v.extensions["plan_annotations"]["objects"]["door_e1"]["change"] == "proposed"


@pytest.mark.parametrize(
    ("fix_ids", "words"),
    [
        ([], "Choose at least one change"),
        (["  "], "Choose at least one change"),
        (["F9"], "not among the changes this test kept: F9"),
        (["F2", "F4"], "not among the changes this test kept: F4"),  # proposed, not kept
    ],
)
def test_an_empty_or_unknown_choice_is_refused_in_plain_words(
    client: TestClient, fix_ids: list[str], words: str
) -> None:
    pid, sid = _session(client)
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": fix_ids})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "invalid_fix_selection"
    assert words in r.json()["message"]
    assert client.get(f"/api/v1/projects/{pid}").json()["current_version"] == 1


def test_a_fix_that_needs_a_left_out_fix_is_a_conflict(client: TestClient) -> None:
    pid, sid = _session(client)
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": ["F3"]})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "fixes_conflict"
    assert "Marshals send people to the east door" in body["message"]
    assert client.get(f"/api/v1/projects/{pid}").json()["current_version"] == 1


def test_a_subset_of_a_stale_plan_is_refused(client: TestClient) -> None:
    pid, sid = _session(client)
    edit = {"patch": {"ops": [{"op": "resize", "target": "door_s1", "width_m": 3}]}}
    assert client.post(f"/api/v1/projects/{pid}/patch", json=edit).status_code == 200
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": ["F2"]})
    assert r.status_code == 409 and r.json()["code"] == "stale_plan"
    assert client.get(f"/api/v1/projects/{pid}").json()["current_version"] == 2


def test_a_subset_keeps_the_organizer_annotations_of_the_current_version(
    client: TestClient,
) -> None:
    pid, sid = _session(client)
    note = {
        "op": "set_annotation",
        "target": "door_s1",
        "provenance": {"basis": "measured", "source": "Tape measure, 12 Oct"},
    }
    r = client.post(f"/api/v1/projects/{pid}/patch", json={"patch": {"ops": [note]}})
    assert r.status_code == 200, r.text  # provenance only: the tested plan still applies
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": ["F2"]})
    assert r.status_code == 200, r.text
    meta = _venue(client, pid).extensions["scene_metadata"]["objects"]["door_s1"]
    assert meta["basis"] == "measured" and meta["source"] == "Tape measure, 12 Oct"
