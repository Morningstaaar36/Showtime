"""Handover checklist (P3-06): the selected plan in plain English.

Gates, staffed actions, the measures of the accepted fixes, open conditions, key numbers
with what they are based on, assumptions and the disclaimer. It never claims the plan is
confirmed unless the session's evaluation is.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.core.plan import apply_fix_bundle
from api.db.models import RedTeamSession
from api.db.session import db_session
from api.models import Fix
from api.orchestrator.reports import build_bundle, plan_state
from api.orchestrator.session import NOT_TESTED_TOGETHER
from api.tests.conformance.suites import check_exporter
from api.tests.evidence_fakes import app_state, reset_engine, use_test_settings
from api.tests.test_api import client as client
from api.tests.test_apply_subset import EAST_DOOR, MARSHALS, WIDER_DOOR
from api.tests.test_plan import action, organizer_plan
from api.tests.test_plan_api import new

DISCLAIMER = "Planning aid, not a safety certification."
APPROVAL = "Human approval records the chosen plan; it does not certify safety."


def claims_confirmed(text: str) -> bool:
    """Does the text say the plan is confirmed? Negations and partial labels don't count."""
    plain = re.sub(r"<style>.*?</style>", " ", text, flags=re.S)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"\b(?:not|Not|Partly)\s+confirmed\b", "", plain)
    return bool(re.search(r"\bconfirmed\b", plain, re.IGNORECASE))


def _evaluation(status: str) -> dict[str, Any]:
    reasons = {
        "confirmed": "The before and after full simulations of the worst attack both ran to "
        "the end, with no one left inside.",
        "partially_confirmed": "The after run is a full simulation that stopped before "
        "everyone was out: 12 people were still inside when it stopped.",
        "unconfirmed": "The kept fixes were not confirmed with full simulations.",
        "failed": "The after simulation (run r_after) did not finish (timeout).",
    }[status]
    basis = {"confirmed": "completed_simulation", "partially_confirmed": "partial_simulation"}
    return {
        "status": status,
        "before_basis": "completed_simulation",
        "after_basis": basis.get(status, "unknown"),
        "reasons": [reasons],
        "before_run_id": "r_before",
        "after_run_id": "r_after",
        "fallback_run_ids": {"after": "r_after-est"} if status == "failed" else {},
    }


def _session(client: TestClient, evaluation: dict[str, Any] | None = None) -> tuple[str, str]:
    """A finished hall session that kept three fixes, with headline numbers per side."""
    st = client.app.state.showtime  # type: ignore[attr-defined]
    pid = client.post("/api/v1/projects", json={"template_id": "conference_hall_2f"}).json()["id"]
    kept = [Fix.model_validate(f) for f in (EAST_DOOR, WIDER_DOOR, MARSHALS)]
    final = st.projects.venue(pid)
    for fx in kept:
        final = apply_fix_bundle(final, fx, st.registry)
    numbers = {
        "evac_time_p95_s": 241.0,
        "peak_density_ppm2": 5.6,
        "time_above_danger_s": 42.0,
        "agents_not_evacuated": 0,
        "agents_total": 1200,
    }
    with db_session(st.projects.db_url) as db:
        db.add(
            RedTeamSession(
                id="s_hand",
                project_id=pid,
                venue_version=1,
                status="finished",
                config={},
                summary={
                    "final_venue": final.model_dump(mode="json"),
                    "accepted_fixes": [f.fix_id for f in kept],
                    "fixes": [f.model_dump(mode="json") for f in kept],
                    "measures": [e.model_dump() for f in kept for e in f.operational],
                    "before": numbers,
                    "after": {**numbers, "evac_time_p95_s": None, "evac_time_estimate_s": 180.0},
                    "evaluation": evaluation or _evaluation("unconfirmed"),
                },
            )
        )
        db.commit()
    return pid, "s_hand"


def _checklist(client: TestClient, path: str) -> str:
    r = client.get(f"/api/v1{path}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-disposition"].startswith("inline")
    return r.text


def test_checklist_of_an_untested_plan_lists_actions_permissions_and_gates(
    client: TestClient,
) -> None:
    pid = new(client, configure=False)
    plan = organizer_plan().model_dump(mode="json")
    plan["constraints"]["approvals"] = {"fire_marshal": {"status": "pending"}}
    r = client.put(f"/api/v1/projects/{pid}/plan", json={"expected_version": 1, "plan": plan})
    assert r.status_code == 200, r.text
    bundle = {"expected_version": 2, "actions": [action(label="Hold the audience")]}
    r = client.post(f"/api/v1/projects/{pid}/plan/bundles", json=bundle)
    assert r.status_code == 200, r.text
    html = _checklist(client, f"/projects/{pid}/checklist")
    assert "version 3 (the selected plan)" in html
    # the saved staff action, with its time window and allocation
    assert "Hold the audience" in html and "Hold Z1 for 10 s, then release it" in html
    assert "0:10–0:30" in html and "1 × stewards (staff)" in html
    assert "radios" in html  # inventory
    # gates: width, open, existing, where the width comes from
    gate = re.search(r"<tr><td><span class=\"box\"[^>]*></span></td><td><b>E1</b>.*?</tr>", html)
    assert gate, html
    row = gate.group(0)
    assert "2.0 m" in row and "Open" in row and "Existing" in row and "Not stated" in row
    # open conditions
    assert "This plan has not been tested by the AI red team yet" in html
    assert "Permission “fire_marshal” is pending" in html
    assert "Exit widths nobody has measured or checked: E1." in html
    assert DISCLAIMER in html and APPROVAL in html
    assert not claims_confirmed(html)


def test_checklist_before_acceptance_lists_suggestions_not_in_the_plan(
    client: TestClient,
) -> None:
    _, sid = _session(client)
    html = _checklist(client, f"/sessions/{sid}/checklist")
    assert "version 1 (the selected plan)" in html
    assert "The AI suggested 3 changes that are not part of this plan yet" in html
    assert "Changes the AI suggested (not accepted yet)" in html
    assert "Open a 2 m exit on the east side" in html and "Standard rule" in html
    # gates of the current plan: nothing changed yet, and the new door is not in it
    gates = html.split("<h2>Gates and doors</h2>")[1].split("</table>")[0]
    assert "No change" in gates and "East door" not in gates
    # key numbers keep their basis; the 95% time sits next to people still inside
    assert "Without the changes (this plan)" in html
    assert "Full simulation, run r_before" in html
    assert "Unknown: the simulation didn&#x27;t finish, run r_after" in html
    assert "about 3 min 00 s (estimated)" in html
    assert "People still inside at the end" in html
    assert "Evaluation: Not confirmed." in html
    assert not claims_confirmed(html)


def test_checklist_after_a_subset_shows_only_its_changes_and_the_untested_note(
    client: TestClient,
) -> None:
    pid, sid = _session(client)
    r = client.post(f"/api/v1/sessions/{sid}/apply", json={"fix_ids": ["F1_R1", "F3"]})
    assert r.status_code == 200, r.text
    html = _checklist(client, f"/projects/{pid}/checklist")
    assert "version 2 (the selected plan)" in html
    assert "Changes in this plan" in html and "not accepted yet" not in html
    assert "Marshals send people to the east door" in html
    assert "Widen South door 2" not in html
    assert NOT_TESTED_TOGETHER in html and "This plan has 2 of the 3 changes" in html
    # the new door is listed as new, proposed construction, and the staff gap is visible
    assert re.search(r"<b>East door</b>.*?Proposed</td><td>New</td>", html)
    assert "Proposed construction: East door must be built and approved" in html
    assert "No staff assigned to “Stewards send 40% of people from South door 1" in html
    assert "neither column describes it exactly" in html
    assert '<div class="map"><svg' in html  # the map of this plan


def test_checklist_marks_a_plan_changed_after_the_test(client: TestClient) -> None:
    pid, sid = _session(client)
    edit = {"patch": {"ops": [{"op": "resize", "target": "door_s1", "width_m": 3}]}}
    assert client.post(f"/api/v1/projects/{pid}/patch", json=edit).status_code == 200
    html = _checklist(client, f"/sessions/{sid}/checklist")
    assert "changed after the last test of version 1" in html
    assert "Widened from 2.5 m" in html  # compared with the tested venue
    assert "3.0 m" in html


@pytest.mark.parametrize("status", ["confirmed", "partially_confirmed", "unconfirmed", "failed"])
def test_checklist_says_confirmed_only_when_the_evaluation_is(
    client: TestClient, status: str
) -> None:
    _, sid = _session(client, _evaluation(status))
    client.post(f"/api/v1/sessions/{sid}/apply")  # every kept fix: tested together
    html = _checklist(client, f"/sessions/{sid}/checklist")
    assert ("Confirmed by full simulations" in html) is (status == "confirmed")
    assert claims_confirmed(html) is (status == "confirmed")
    assert "With all the changes the AI kept (this plan)" in html
    if status == "failed":
        assert "Some simulations did not finish (after)" in html
        assert "Instant estimate (the simulation didn&#x27;t finish), run r_after-est" in html
    if status != "confirmed":
        assert "The tests do not confirm this plan yet" in html


def test_plan_state_follows_the_plan_identity() -> None:
    applied = [{"plan_hash": "h2", "tested_together": False, "fix_ids": ["F2"]}]
    assert plan_state("h1", None, 2, []) == ("untested", None)
    assert plan_state("h1", "h1", 2, applied) == ("pending", None)
    assert plan_state("h1", "h1", 0, []) == ("tested", None)
    assert plan_state("h2", "h1", 2, applied) == ("accepted_subset", applied[0])
    assert plan_state("h3", "h1", 2, applied) == ("stale", None)


@pytest.fixture
def make_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    settings = use_test_settings(tmp_path, monkeypatch)
    yield lambda **kw: app_state(settings, **kw)
    reset_engine()


async def test_checklist_of_a_real_session_carries_each_fix_test(
    make_state: Callable[..., Any],
) -> None:
    st = make_state()  # simulation-like runs: the confirmation completes
    p = st.projects.create("Hall", template_id="conference_hall_2f")
    config = {"max_rounds": 1, "attacks_per_round": 3, "fixes_per_attack": 2, "fix_targets": 1}
    row = st.sessions.start(p.id, config)
    await st.sessions.live[row.id].task
    row = st.sessions.get(row.id)
    kept = row.summary["accepted_fixes"]
    assert kept and row.summary["evaluation"]["status"] == "confirmed"
    st.sessions.apply_final(row.id)
    bundle = build_bundle(st, p.id, row.id)
    assert bundle.extras["handover"]["state"] == "accepted"
    evidence = bundle.extras["fix_evidence"]
    for fid in kept:
        before, after = evidence[fid]["before"], evidence[fid]["after"]
        assert before["run_id"] != after["run_id"]
        assert after["tier"] == 2
        assert after["basis"] in ("partial_simulation", "completed_simulation")
    exporter = st.registry.get("Exporter", "export_checklist")
    html = check_exporter(exporter, bundle).decode()
    assert "Tested on its own under" in html and "Quick simulation" in html
    assert "With all the changes the AI kept (this plan)" in html
    assert "Evaluation: Confirmed by full simulations." in html and claims_confirmed(html)
    assert "Under the worst case found:" in html
