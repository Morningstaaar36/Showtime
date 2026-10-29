"""HTTP API integration tests (FastAPI TestClient, fake LLM and fake sandbox)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import FakeRunner
from api.app.main import create_app
from api.app.state import build_state
from api.core.settings import Settings, get_settings
from api.tests.http import api_client


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db = tmp_path / "api.sqlite"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    get_settings.cache_clear()
    from api.db import session as dbs

    dbs.get_engine.cache_clear()
    settings = Settings(
        _env_file=None,
        db_url=f"sqlite:///{db}",
        runs_dir=tmp_path / "runs",
        cache_dir=tmp_path / "cache",
        llm_provider="fake",
        sandbox_provider="fake",
        offline=True,
    )
    monkeypatch.setattr("api.core.settings.get_settings", lambda: settings)
    monkeypatch.setattr("api.db.session.get_settings", lambda: settings)
    monkeypatch.setattr("api.orchestrator.demos.DEMO_DIR", tmp_path / "no-demos")
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    app = create_app(state=state, settings=settings)
    with api_client(app) as c:
        yield c
    get_settings.cache_clear()
    dbs.get_engine.cache_clear()


def _new(client: TestClient, template: str = "conference_hall_2f") -> str:
    r = client.post("/api/v1/projects", json={"template_id": template, "name": "Test"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_health_and_features(client: TestClient) -> None:
    h = client.get("/api/v1/health").json()
    assert h["providers"]["llm"]["ok"] and h["providers"]["sandbox"]["ok"]
    assert any(p["id"] == "ops_core" and p["healthy"] for p in h["plugins"])
    f = client.get("/api/v1/features").json()
    assert "add_exit" in f["patch_ops"]
    assert {e["type"] for e in f["events"]} >= {"block_exit", "surge"}


def test_templates(client: TestClient) -> None:
    items = client.get("/api/v1/templates").json()
    assert {t["id"] for t in items} == {
        "festival_field",
        "conference_hall_2f",
        "school_wing",
        "t_alley",
    }


def test_project_lifecycle(client: TestClient) -> None:
    pid = _new(client)
    assert any(p["id"] == pid for p in client.get("/api/v1/projects").json())
    proj = client.get(f"/api/v1/projects/{pid}").json()
    assert proj["validation"]["ok"] and proj["current_version"] == 1
    r = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={
            "patch": {
                "ops": [
                    {
                        "op": "add_exit",
                        "floor_id": "F0",
                        "id": "door_e1",
                        "wall": "east",
                        "center": 8,
                        "width_m": 2,
                    }
                ]
            }
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["project"]["can_undo"]
    assert client.post(f"/api/v1/projects/{pid}/undo").status_code == 200
    venue = client.get(f"/api/v1/venues/{pid}").json()
    assert "door_e1" not in {e["id"] for f in venue["floors"] for e in f["exits"]}
    assert client.post(f"/api/v1/projects/{pid}/redo").status_code == 200
    assert len(client.get(f"/api/v1/projects/{pid}/versions").json()) == 4
    r = client.patch(f"/api/v1/projects/{pid}", json={"name": "Renamed"})
    assert r.json()["name"] == "Renamed"
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404


def test_invalid_edit_has_designed_error(client: TestClient) -> None:
    pid = _new(client)
    r = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={"patch": {"ops": [{"op": "remove_exit", "exit_id": "nope"}]}},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_edit" and "nope" in body["message"] and body["hint"]


def test_tier1_and_break_it_yourself(client: TestClient) -> None:
    pid = _new(client)
    base = client.post(f"/api/v1/venues/{pid}/tier1", json={}).json()
    blocked = client.post(f"/api/v1/venues/{pid}/tier1", json={"blocked_exits": ["door_s1"]}).json()
    assert blocked["metrics"]["evac_time_p95_s"] > base["metrics"]["evac_time_p95_s"]
    bad = client.post(f"/api/v1/venues/{pid}/tier1", json={"blocked_exits": ["ghost"]})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_event"


def test_run_flow_with_fake_sandbox(client: TestClient) -> None:
    pid = _new(client, "school_wing")
    r = client.post("/api/v1/runs", json={"project_id": pid, "tier": 3, "seed": 1})
    assert r.status_code == 202, r.text
    rid = r.json()["id"]
    for _ in range(50):
        run = client.get(f"/api/v1/runs/{rid}").json()
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert run["status"] in ("ok", "partial"), run
    again = client.post("/api/v1/runs", json={"project_id": pid, "tier": 3, "seed": 1})
    assert again.json()["id"] == rid  # idempotent
    assert any(x["id"] == rid for x in client.get(f"/api/v1/projects/{pid}/runs").json())
    assert client.get(f"/api/v1/runs/{rid}/trajectory").status_code == 404  # fake: no replay


def test_countdown_indoor_scenario(client: TestClient) -> None:
    pid = _new(client)
    attack = {
        "attack_id": "A1",
        "title": "Door lost",
        "events": [{"type": "block_exit", "exit_id": "door_s1", "at_s": 900}],
        "inspired_by": {"incident": "x", "source_url": "https://example.org"},
    }
    cd = client.post(f"/api/v1/projects/{pid}/countdown", json={"attack": attack}).json()
    c = cd["countdown"]
    assert c["status"] in ("ok", "too_late")
    assert c["t_hazard_s"] == 900 and c["rset_s"] > 0
    assert c["t_latest_s"] == pytest.approx(900 - (60 + c["rset_s"] * 1.5), abs=0.2)


def test_countdown_outdoor_offline_needs_manual(client: TestClient) -> None:
    pid = _new(client, "festival_field")
    cd = client.post(f"/api/v1/projects/{pid}/countdown", json={}).json()
    assert cd["manual_input_needed"]
    cd2 = client.post(f"/api/v1/projects/{pid}/countdown", json={"gust_ms": 50}).json()
    assert cd2["countdown"]["status"] in ("ok", "too_late")


def test_stage_check_and_settings(client: TestClient) -> None:
    pid = _new(client, "festival_field")
    r = client.post("/api/v1/stage-check", json={"project_id": pid}).json()
    assert r["v_limit_ms"] > 10 and r["label"] == "screening estimate"
    s = client.put("/api/v1/settings", json={"values": {"safety_factor": 2.0, "theme": "dark"}})
    assert s.status_code == 200 and s.json()["effective"]["safety_factor"] == 2.0
    bad = client.put("/api/v1/settings", json={"values": {"density_danger_ppm2": -1}})
    assert bad.status_code == 422


def test_export_import(client: TestClient) -> None:
    pid = _new(client, "t_alley")
    data = client.get(f"/api/v1/projects/{pid}/export").content
    r = client.post(
        "/api/v1/projects/import", files={"file": ("x.showtime.zip", data, "application/zip")}
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] != pid


def test_what_if_scales_crowd_closes_exits_and_scores(client: TestClient) -> None:
    pid = client.post("/api/v1/projects", json={"template_id": "school_wing"}).json()["id"]
    base = client.post(f"/api/v1/projects/{pid}/whatif", json={}).json()
    assert base["people"] == 400 and base["basis"].startswith("Instant")
    assert 0 <= base["score"]["score"] <= 100 and base["score"]["grade"] in "ABCDF"
    keys = {p["key"] for p in base["score"]["parts"]}
    assert keys == {"evac", "density", "capacity", "exits", "checks"}
    big = client.post(f"/api/v1/projects/{pid}/whatif", json={"people_scale": 2.5}).json()
    assert big["people"] == 1000 and big["score"]["score"] <= base["score"]["score"]
    venue = client.get(f"/api/v1/projects/{pid}").json()["version"]["venue"]
    exit_id = venue["floors"][0]["exits"][0]["id"]
    closed = client.post(f"/api/v1/projects/{pid}/whatif",
                         json={"blocked_exits": [exit_id], "speed_factor": 0.7}).json()  # fmt: skip
    assert closed["metrics"]["evac_time_p95_s"] >= base["metrics"]["evac_time_p95_s"]
    assert closed["capacity"]["by_egress"] < base["capacity"]["by_egress"]


def test_validation_endpoint_serves_the_shipped_exhibit(client: TestClient) -> None:
    r = client.get("/api/v1/validation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["dataset_doi"] == "10.34735/ped.2006.2"
    assert all(len(w["simulated_flow_ps"]["runs"]) >= 3 for w in body["widths"])
    assert "median_abs_error_pct" in body


def test_validation_endpoint_missing_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("api.app.routes_core.load_validation", lambda: None)
    r = client.get("/api/v1/validation")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
