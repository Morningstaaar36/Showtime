"""Each sandbox says what it guarantees per run; /health and the AI team page show those facts."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import DockerRunner, FakeRunner, Isolation
from api.app.main import create_app
from api.app.state import build_state
from api.tests.evidence_fakes import reset_engine, use_test_settings
from api.tests.http import api_client


def test_docker_isolation_matches_the_flags_it_runs_with(tmp_path: Path) -> None:
    iso = DockerRunner(tmp_path, "showtime-sim:latest", "2g", 2.0).isolation
    assert (iso.kind, iso.network_off, iso.memory, iso.cpus) == ("container", True, "2g", 2.0)
    assert iso.read_only and iso.non_root and iso.per_job_limits and iso.process_limit == 256
    assert iso.summary() == (
        "One container per run, no network, 2 GB memory, 2 CPU, read-only system, "
        "at most 256 processes, no admin rights."
    )


def test_a_cloud_sandbox_without_per_job_limits_says_so() -> None:
    iso = Isolation("cloud", None, None, None, False, None, False, per_job_limits=False)
    assert "static check" in iso.summary()


def test_the_fake_runner_is_no_sandbox(tmp_path: Path) -> None:
    iso = FakeRunner(tmp_path).isolation
    assert iso.kind == "none" and "no simulation" in iso.summary()


def test_health_and_the_team_page_report_the_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = use_test_settings(tmp_path, monkeypatch)
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    try:
        with api_client(create_app(state=state, settings=settings)) as c:
            sb = c.get("/api/v1/health").json()["providers"]["sandbox"]
            team = c.get("/api/v1/agents").json()["sandbox"]
        assert sb["isolation"]["kind"] == "none" and sb["isolation"]["summary"]
        assert sb["time_limit_s"] == settings.max_wall_s
        assert team["isolation"] == sb["isolation"]
    finally:
        reset_engine()


def test_the_sandbox_proof_is_served_from_the_recorded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    settings = use_test_settings(tmp_path, monkeypatch)
    proof = tmp_path / "proof.json"
    settings = settings.model_copy(update={"sandbox_proof_file": proof})
    state = build_state(settings, llm=FakeLLM({}, settings), runner=FakeRunner(settings.runs_dir))
    try:
        with api_client(create_app(state=state, settings=settings)) as c:
            missing = c.get("/api/v1/sandbox/proof")
            assert missing.status_code == 404 and "make sandbox-proof" in missing.json()["hint"]
            rows = [
                {"kind": "code", "name": "network", "label": "Connect", "inside": "unreachable"}
            ]
            proof.write_text(json.dumps({"recorded_at": "2026-10-25T10:00:00+00:00", "rows": rows}))
            assert c.get("/api/v1/sandbox/proof").json()["rows"][0]["inside"] == "unreachable"
    finally:
        reset_engine()
