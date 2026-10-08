"""NebiusRunner against a fake contree-sdk client (live tests run only with NEBIUS_API_KEY)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from api.adapters.nebius_sandbox import NebiusRunner
from api.core.extensions import Registry
from api.core.settings import Settings
from api.core.templates import get_template
from api.orchestrator.runs import RunService


class FakeImage:
    """Mimics contree_sdk image objects: run() returns an awaitable child snapshot."""

    counter = 0

    def __init__(
        self,
        files: dict[str, bytes] | None = None,
        parent: FakeImage | None = None,
        fail: bool = False,
    ) -> None:
        FakeImage.counter += 1
        self.uuid = f"img-{FakeImage.counter}"
        self.files = dict(files or {})
        self.parent = parent
        self.fail = fail
        self.commands: list[str] = []

    def run(
        self,
        shell: str,
        files: dict[str, bytes] | None = None,
        disposable: bool = True,
        timeout: int | None = None,
    ) -> Any:
        child = FakeImage({**self.files, **(files or {})}, parent=self, fail=self.fail)
        child.commands = [*self.commands, shell]

        async def go() -> FakeImage:
            if "run_sim.py" in shell:
                if child.fail:
                    raise RuntimeError("sandbox crashed")
                req = json.loads(child.files["/work/request.json"])
                child.files["/work/result.json"] = json.dumps(
                    {
                        "run_id": req["run_id"],
                        "tier": req["tier"],
                        "status": "ok",
                        "metrics": {
                            "evac_time_p95_s": 100.0,
                            "peak_density_ppm2": 3.0,
                            "agents_total": 10,
                            "agents_evacuated": 10,
                        },
                        "artifacts": {},
                    }
                ).encode()
            return child

        return go()

    async def apply_files(self, files: dict[str, bytes]) -> FakeImage:
        return await self.run(shell="true", files=files, disposable=False)

    async def read(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class FakeImages:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.pulled: list[str] = []

    async def oci(self, ref: str) -> FakeImage:
        self.pulled.append(ref)
        return FakeImage(fail=self.fail)

    async def use(self, ref: str) -> FakeImage:
        raise KeyError(ref)


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.images = FakeImages(fail)

    async def get_token_info(self) -> Any:
        return type("Who", (), {"name": "test"})()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        runs_dir=tmp_path / "runs",
        cache_dir=tmp_path / "cache",
        sandbox_provider="nebius",
        nebius_api_key="test",
    )


async def test_nebius_runner_branches_and_reads_results(registry: Registry, tmp_path: Path) -> None:
    st = _settings(tmp_path)
    client = FakeClient()
    runner = NebiusRunner(st, client=client)
    svc = RunService(st, registry, runner, db_url=f"sqlite:///{tmp_path / 'db.sqlite'}")
    from api.db.session import migrate

    migrate(f"sqlite:///{tmp_path / 'db.sqlite'}")
    job = svc.build_job(get_template("school_wing"), tier=2)
    res = await runner.run(job)
    assert res.status == "ok" and res.provider == "nebius"
    assert client.images.pulled == ["python:3.12-slim"]
    snap = runner._nodes[job.request.run_id]
    assert "/app/run_sim.py" in snap.files and "/work/venue.json" in snap.files
    assert any("pip install" in c for c in snap.commands)
    assert (tmp_path / "cache" / "nebius" / "base_image.json").exists()
    assert (await runner.health())["ok"]


async def test_nebius_runner_failure_is_reported(registry: Registry, tmp_path: Path) -> None:
    st = _settings(tmp_path)
    runner = NebiusRunner(st, client=FakeClient(fail=True))
    job = RunService(st, registry, runner).build_job(get_template("school_wing"), tier=2)
    res = await runner.run(job)
    assert res.status == "failed" and "Nebius sandbox error" in (res.error or "")


@pytest.mark.nebius
@pytest.mark.skipif(not os.environ.get("NEBIUS_API_KEY"), reason="untested: no NEBIUS_API_KEY")
async def test_nebius_live_health() -> None:
    from api.core.settings import Settings as S

    runner = NebiusRunner(S(sandbox_provider="nebius"))
    assert (await runner.health())["ok"]
