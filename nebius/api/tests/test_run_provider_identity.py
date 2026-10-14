"""Switching from previews to Docker must require a new run."""

from api.adapters.sandbox import FakeRunner
from api.core.settings import Settings
from api.orchestrator.runs import RunService


def test_provider_switch_changes_cache_identity(tmp_path, registry, hall) -> None:
    settings = Settings(_env_file=None, runs_dir=tmp_path / "runs")
    fake = FakeRunner(settings.runs_dir)
    service = RunService(settings, registry, fake)
    preview = service.build_job(hall, tier=2, seed=7)
    assert service.build_job(hall, tier=2, seed=7).request.run_id == preview.request.run_id
    assert preview.request.extensions["sandbox_provider"] == "fake"
    # No simulation is needed to check identity: the real runner shares the same protocol.
    fake.provider = "docker"
    real = service.build_job(hall, tier=2, seed=7)
    assert real.request.venue_hash == preview.request.venue_hash
    assert real.request.run_id != preview.request.run_id
    assert real.request.extensions["sandbox_provider"] == "docker"
