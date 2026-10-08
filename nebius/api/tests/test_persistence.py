"""Projects, versions, undo/redo, export/import, and the run service with a FakeRunner."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.adapters.sandbox import FakeRunner
from api.core.extensions import Registry
from api.core.settings import Settings
from api.core.venue_ops import PatchError, venue_hash
from api.db.session import migrate
from api.models import Attack, Fix, VenuePatch
from api.orchestrator.projects import NotFound, ProjectService
from api.orchestrator.runs import RunService, compose_events


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'test.sqlite'}"
    migrate(url)
    return url


@pytest.fixture
def projects(registry: Registry, db_url: str) -> ProjectService:
    return ProjectService(registry, db_url)


def _patch(**op: object) -> VenuePatch:
    return VenuePatch.model_validate({"ops": [op]})


def test_create_and_version(projects: ProjectService) -> None:
    p = projects.create("Gala", template_id="conference_hall_2f")
    assert p.current_version == 1
    assert projects.venue(p.id).venue_id == p.id
    row, _ = projects.apply(p.id, _patch(op="set_people", zone_id="audience", people=800))
    assert row.version == 2 and row.base_version == 1
    assert projects.venue(p.id).floor("F0").zones[0].people == 800
    assert [v.version for v in projects.versions(p.id)] == [2, 1]


def test_undo_redo_chain(projects: ProjectService) -> None:
    p = projects.create("Gala", template_id="conference_hall_2f")
    h1 = venue_hash(projects.venue(p.id))
    projects.apply(p.id, _patch(op="set_people", zone_id="audience", people=800))
    h2 = venue_hash(projects.venue(p.id))
    projects.apply(p.id, _patch(op="move", target="stage", dx=0, dy=-2))
    h3 = venue_hash(projects.venue(p.id))
    projects.undo(p.id)
    assert venue_hash(projects.venue(p.id)) == h2
    projects.undo(p.id)
    assert venue_hash(projects.venue(p.id)) == h1
    with pytest.raises(PatchError):
        projects.undo(p.id)
    projects.redo(p.id)
    assert venue_hash(projects.venue(p.id)) == h2
    projects.redo(p.id)
    assert venue_hash(projects.venue(p.id)) == h3
    with pytest.raises(PatchError):
        projects.redo(p.id)


def test_new_edit_clears_redo(projects: ProjectService) -> None:
    p = projects.create("Gala", template_id="conference_hall_2f")
    projects.apply(p.id, _patch(op="set_people", zone_id="audience", people=800))
    projects.undo(p.id)
    projects.apply(p.id, _patch(op="set_people", zone_id="audience", people=700))
    with pytest.raises(PatchError):
        projects.redo(p.id)


def test_restore_and_duplicate(projects: ProjectService) -> None:
    p = projects.create("Gala", template_id="conference_hall_2f")
    h1 = venue_hash(projects.venue(p.id))
    projects.apply(p.id, _patch(op="set_people", zone_id="audience", people=800))
    projects.restore(p.id, 1)
    assert venue_hash(projects.venue(p.id)) == h1
    projects.undo(p.id)  # undo the restore
    assert projects.venue(p.id).floor("F0").zones[0].people == 800
    d = projects.duplicate(p.id)
    assert d.id != p.id and projects.venue(d.id).floor("F0").zones[0].people == 800


def test_export_import_roundtrip(projects: ProjectService) -> None:
    p = projects.create("Gala", template_id="school_wing")
    projects.apply(p.id, _patch(op="set_people", zone_id="room_1", people=20))
    data = projects.export_zip(p.id)
    q = projects.import_zip(data)
    assert q.id != p.id
    assert projects.venue(q.id).floor("F0").zones[0].people == 20
    assert len(projects.versions(q.id)) == 2
    with pytest.raises(ValueError):
        projects.import_zip(b"not a zip")


def test_persists_across_service_instances(registry: Registry, db_url: str) -> None:
    p = ProjectService(registry, db_url).create("Gala", template_id="t_alley")
    again = ProjectService(registry, db_url)
    assert again.get(p.id).name == "Gala"
    again.delete(p.id)
    with pytest.raises(NotFound):
        again.get(p.id)


# --- runs -------------------------------------------------------------------------------


@pytest.fixture
def run_service(registry: Registry, db_url: str, tmp_path: Path) -> RunService:
    st = Settings(_env_file=None, runs_dir=tmp_path / "runs")
    return RunService(st, registry, FakeRunner(tmp_path / "runs"), db_url)


ATTACK = Attack.model_validate(
    {
        "attack_id": "A1",
        "title": "South door lost",
        "events": [{"type": "block_exit", "exit_id": "door_s1", "at_s": 0}],
        "inspired_by": {"incident": "test", "source_url": "https://example.org/x"},
    }
)
FIX = Fix.model_validate(
    {
        "fix_id": "F1",
        "for_attack": "A1",
        "title": "East door",
        "patch": {
            "ops": [
                {
                    "op": "add_exit",
                    "floor_id": "F0",
                    "id": "door_e1",
                    "wall": "east",
                    "center": 8,
                    "width_m": 2.5,
                }
            ]
        },
        "operational": [{"type": "staggered_release", "zone_id": "mezzanine", "delay_s": 45}],
    }
)


async def test_run_is_idempotent_and_cached(
    run_service: RunService, projects: ProjectService
) -> None:
    p = projects.create("Gala", template_id="conference_hall_2f")
    v = projects.venue(p.id)
    job1 = run_service.build_job(v, tier=3, seed=1)
    job2 = run_service.build_job(v, tier=3, seed=1)
    assert job1.request.run_id == job2.request.run_id
    res = await run_service.run(job1, project_id=p.id)
    assert res.status in ("ok", "partial")
    runner = run_service.runner
    assert isinstance(runner, FakeRunner)
    calls = len(runner.calls)
    await run_service.run(job2, project_id=p.id)
    assert len(runner.calls) == calls  # cache hit
    other = run_service.build_job(v, tier=3, seed=2)
    assert other.request.run_id != job1.request.run_id


async def test_attack_and_fix_change_results(
    run_service: RunService, projects: ProjectService
) -> None:
    p = projects.create("Gala", template_id="conference_hall_2f")
    v = projects.venue(p.id)
    base = run_service.estimate(v)
    attacked = run_service.estimate(v, ATTACK)
    fixed = run_service.estimate(v, ATTACK, FIX)
    assert attacked.metrics.evac_time_p95_s and base.metrics.evac_time_p95_s
    assert attacked.metrics.evac_time_p95_s > base.metrics.evac_time_p95_s
    assert fixed.metrics.evac_time_p95_s
    assert any(pe.exit_id == "door_e1" and pe.people > 0 for pe in fixed.metrics.per_exit)


def test_compose_events_shifts_fix_to_intervention() -> None:
    evs = compose_events(ATTACK, FIX, intervention_at_s=60)
    assert [e.type for e in evs] == ["block_exit", "staggered_release"]
    assert evs[1].at_s == 60


async def test_failed_sandbox_does_not_crash(
    registry: Registry, db_url: str, tmp_path: Path, projects: ProjectService
) -> None:
    st = Settings(_env_file=None, runs_dir=tmp_path / "runs")
    svc = RunService(st, registry, FakeRunner(tmp_path / "runs", fail_ids={"r_"}), db_url)
    p = projects.create("Gala", template_id="school_wing")
    res = await svc.run(svc.build_job(projects.venue(p.id), tier=2), project_id=p.id)
    assert res.status == "failed" and res.error
    row = svc.get(res.run_id)
    assert row is not None and row.status == "failed"
