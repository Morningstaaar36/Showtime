"""NebiusRunner against a fake contree-sdk client (live tests run only with NEBIUS_API_KEY).

Covers per-run folders (a child never reads its parent's result), resume_from branching
and code jobs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from api.adapters.nebius_sandbox import NebiusRunner
from api.adapters.sandbox import CodeJob
from api.core.extensions import Registry
from api.core.settings import Settings
from api.core.templates import get_template
from api.orchestrator.runs import RunService


class FakeImage:
    """Mimics contree_sdk image objects: run() returns an awaitable child snapshot.

    The shell command is interpreted step by step (mkdir, cp, cd, run_sim.py, run_code.py), so
    the tests see which folder a run used and what it copied from its parent.
    """

    counter = 0

    def __init__(
        self,
        files: dict[str, bytes] | None = None,
        parent: FakeImage | None = None,
        fail: bool = False,
        crash: set[str] | None = None,
        code: dict[str, Any] | None = None,
    ) -> None:
        FakeImage.counter += 1
        self.uuid = f"img-{FakeImage.counter}"
        self.files = dict(files or {})
        self.parent = parent
        self.fail = fail
        self.crash = crash if crash is not None else set()  # run ids whose sim writes nothing
        self.code = code if code is not None else {}  # scripted run_code outcome
        self.commands: list[str] = []
        self.disposable = False
        self.stdout: str = ""
        self.stderr: str = ""
        self.exit_code = 0

    def run(
        self,
        shell: str,
        files: dict[str, bytes] | None = None,
        disposable: bool = True,
        timeout: int | None = None,
    ) -> Any:
        child = FakeImage(
            {**self.files, **(files or {})},
            parent=self,
            fail=self.fail,
            crash=self.crash,
            code=self.code,
        )
        child.commands = [*self.commands, shell]
        child.disposable = disposable

        async def go() -> FakeImage:
            for step in shell.split(" && "):
                child._step(step.strip())
            return child

        return go()

    def _step(self, step: str) -> None:
        words = step.split()
        if words[:1] == ["cp"]:
            src, dst = words[1], words[2]
            if src not in self.files:
                raise RuntimeError(f"cp: {src}: no such file")
            self.files[dst] = self.files[src]
        elif "run_code.py" in step:
            if "raise" in self.code:
                raise self.code["raise"]
            self.stdout = str(self.code.get("stdout", ""))
            self.stderr = str(self.code.get("stderr", ""))
            self.exit_code = int(self.code.get("exit_code", 0))
        elif "run_sim.py" in step:
            if self.fail:
                raise RuntimeError("sandbox crashed")
            folder = words[-1]
            req = json.loads(self.files[f"{folder}/request.json"])
            if req["run_id"] in self.crash:
                return  # the simulation died before writing anything
            resumed = f"{folder}/checkpoint.json" in self.files
            self.files[f"{folder}/result.json"] = json.dumps(
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
                    "notes": ["resumed from checkpoint"] if resumed else [],
                }
            ).encode()
            if not resumed:
                self.files[f"{folder}/checkpoint.json"] = json.dumps(
                    {"from": req["run_id"]}
                ).encode()

    async def apply_files(self, files: dict[str, bytes]) -> FakeImage:
        return await self.run(shell="true", files=files, disposable=False)

    async def read(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class FakeImages:
    def __init__(
        self, fail: bool = False, crash: set[str] | None = None, code: dict[str, Any] | None = None
    ) -> None:
        self.fail = fail
        self.crash = crash if crash is not None else set()
        self.code = code if code is not None else {}
        self.pulled: list[str] = []

    async def oci(self, ref: str) -> FakeImage:
        self.pulled.append(ref)
        return FakeImage(fail=self.fail, crash=self.crash, code=self.code)

    async def use(self, ref: str) -> FakeImage:
        raise KeyError(ref)


class FakeClient:
    def __init__(
        self, fail: bool = False, crash: set[str] | None = None, code: dict[str, Any] | None = None
    ) -> None:
        self.images = FakeImages(fail, crash, code)

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
    rid = job.request.run_id
    snap = runner._nodes[rid]
    assert "/app/run_sim.py" in snap.files and "/work/venue.json" in snap.files
    # every run has its own folder: inputs and results live under /work/<run_id>/
    assert f"/work/{rid}/request.json" in snap.files and f"/work/{rid}/result.json" in snap.files
    assert "/work/result.json" not in snap.files
    assert snap.commands[-1].endswith(f"python run_sim.py /work/{rid}")
    assert any("pip install" in c for c in snap.commands)
    assert (tmp_path / "cache" / "nebius" / "base_image.json").exists()
    assert (await runner.health())["ok"]


async def test_nebius_runner_failure_is_reported(registry: Registry, tmp_path: Path) -> None:
    st = _settings(tmp_path)
    runner = NebiusRunner(st, client=FakeClient(fail=True))
    job = RunService(st, registry, runner).build_job(get_template("school_wing"), tier=2)
    res = await runner.run(job)
    assert res.status == "failed" and "Nebius sandbox error" in (res.error or "")


def _service(tmp_path: Path, registry: Registry, client: FakeClient) -> tuple[NebiusRunner, Any]:
    st = _settings(tmp_path)
    runner = NebiusRunner(st, client=client)
    return runner, RunService(st, registry, runner)


async def test_a_child_never_returns_its_parents_result(registry: Registry, tmp_path: Path) -> None:
    """The stale-parent bug: a crashed child used to read the parent's /work/result.json."""
    client = FakeClient()
    runner, svc = _service(tmp_path, registry, client)
    venue = get_template("school_wing")
    parent = svc.build_job(venue, tier=2, seed=1)
    assert (await runner.run(parent)).status == "ok"
    child = svc.build_job(venue, tier=2, seed=2)
    child.parent_node = parent.request.run_id
    client.images.crash.add(child.request.run_id)
    res = await runner.run(child)
    snap_files = runner._nodes[parent.request.run_id].files
    assert f"/work/{parent.request.run_id}/result.json" in snap_files
    assert res.status == "failed" and res.run_id == child.request.run_id
    assert "wrote no result" in (res.error or "")
    assert not (tmp_path / "runs" / child.request.run_id / "result.json").exists()


async def test_resume_from_branches_from_the_checkpoint_snapshot(
    registry: Registry, tmp_path: Path
) -> None:
    client = FakeClient()
    runner, svc = _service(tmp_path, registry, client)
    venue = get_template("school_wing")
    first = svc.build_job(venue, tier=2, seed=1)
    a = first.request.run_id
    assert (await runner.run(first)).status == "ok"
    assert (tmp_path / "runs" / a / "checkpoint.json").exists()  # read back with the results
    branch = svc.build_job(venue, tier=2, seed=3)
    b = branch.request.run_id
    branch.resume_from = a
    res = await runner.run(branch)
    assert res.status == "ok" and "resumed from checkpoint" in res.notes
    snap = runner._nodes[b]
    assert snap.parent is runner._nodes[a]  # a real snapshot branch of the checkpoint run
    assert f"cp /work/{a}/checkpoint.json /work/{b}/checkpoint.json" in snap.commands[-1]
    assert snap.files[f"/work/{b}/checkpoint.json"] == snap.files[f"/work/{a}/checkpoint.json"]


async def test_resume_from_after_a_restart_uploads_the_local_checkpoint(
    registry: Registry, tmp_path: Path
) -> None:
    runner, svc = _service(tmp_path, registry, FakeClient())
    venue = get_template("school_wing")
    (tmp_path / "runs" / "r_saved").mkdir(parents=True)
    (tmp_path / "runs" / "r_saved" / "checkpoint.json").write_text('{"t": 30}')
    job = svc.build_job(venue, tier=2, seed=4)
    job.resume_from = "r_saved"
    res = await runner.run(job)
    rid = job.request.run_id
    assert res.status == "ok" and "resumed from checkpoint" in res.notes
    assert runner._nodes[rid].files[f"/work/{rid}/checkpoint.json"] == b'{"t": 30}'

    missing = svc.build_job(venue, tier=2, seed=5)
    missing.resume_from = "r_gone"
    res = await runner.run(missing)
    assert res.status == "failed" and "no saved moment" in (res.error or "")
    bad = svc.build_job(venue, tier=2, seed=6)
    bad.resume_from = "../etc"
    assert (await runner.run(bad)).status == "failed"


async def test_nebius_run_code_uploads_to_the_job_folder(tmp_path: Path) -> None:
    client = FakeClient(code={"stdout": 'hello\n{"queue_s": 42.5}\n', "exit_code": 0})
    runner = NebiusRunner(_settings(tmp_path), client=client)
    job = CodeJob(
        job_id="an-1",
        kind="analysis",
        script="output = {}",
        inputs={"result.json": b"{}"},
        timeout_s=5,
    )
    res = await runner.run_code(job)
    assert res.status == "ok" and res.output == {"queue_s": 42.5}
    assert res.stdout_tail == "hello"


async def test_nebius_run_code_errors_and_timeouts(tmp_path: Path) -> None:
    job = CodeJob(job_id="an-2", kind="analysis", script="x", timeout_s=5)
    err = NebiusRunner(
        _settings(tmp_path),
        client=FakeClient(code={"stderr": "ZeroDivisionError", "exit_code": 1}),
    )
    res = await err.run_code(job)
    assert res.status == "error" and "ZeroDivisionError" in res.stderr_tail

    class OperationTimedOutError(Exception):
        pass

    slow = NebiusRunner(
        _settings(tmp_path / "b"), client=FakeClient(code={"raise": OperationTimedOutError()})
    )
    assert (await slow.run_code(job)).status == "timeout"
    late = NebiusRunner(_settings(tmp_path / "c"), client=FakeClient(code={"exit_code": 124}))
    assert (await late.run_code(job)).status == "timeout"
    bad = CodeJob(job_id="../x", kind="analysis", script="x")
    assert (await err.run_code(bad)).status == "error"


@pytest.mark.nebius
@pytest.mark.skipif(not os.environ.get("NEBIUS_API_KEY"), reason="untested: no NEBIUS_API_KEY")
async def test_nebius_live_health() -> None:
    from api.core.settings import Settings as S

    runner = NebiusRunner(S(sandbox_provider="nebius"))
    assert (await runner.health())["ok"]
