"""Sandbox providers: run one simulation job in an isolated environment.

`DockerRunner` (local default) starts one `showtime-sim` container per run with
`--network=none`, a non-root user and memory/CPU caps. Branching is logical: the parent
node id is stored on the result so the UI can draw the tree. `NebiusRunner` lives in
`api/adapters/nebius_sandbox.py` and implements the same protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from api.models import Attack, Fix, RunArtifacts, RunRequest, RunResult, Venue

log = logging.getLogger("showtime.sandbox")
ProgressFn = Callable[[dict[str, Any]], None]


@dataclass
class SimJob:
    """Everything a sandbox needs for one run (written as JSON files into the work dir)."""

    request: RunRequest
    venue: Venue
    events: list[dict[str, Any]]
    plan: dict[str, Any]
    sim_settings: dict[str, Any]
    base_venue: Venue | None = None
    attack: Attack | None = None
    fix: Fix | None = None
    parent_node: str | None = None
    tier1: RunResult | None = None  # used by FakeRunner and as a fallback
    extra: dict[str, Any] = field(default_factory=dict)


class SandboxRunner(Protocol):
    """Provider-agnostic sandbox interface."""

    provider: str

    async def prepare_base(self, venue: Venue) -> str:
        """Prepare (or reuse) the base environment; returns a node id for the tree root."""

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        """Run the job; artifacts end up under runs/<run_id>/."""

    async def health(self) -> dict[str, Any]:
        """{"ok": bool, "detail": str}."""

    async def close(self) -> None:
        """Release resources."""


def write_job_files(work: Path, job: SimJob) -> None:
    """Write request/venue/events/plan (+ attack/fix/base) JSON into a work folder."""
    work.mkdir(parents=True, exist_ok=True)
    req = job.request.model_dump(mode="json")
    req["settings"] = job.sim_settings
    req["provider"] = job.extra.get("provider", "docker")
    files: dict[str, Any] = {
        "request.json": req,
        "venue.json": job.venue.model_dump(mode="json"),
        "events.json": job.events,
        "plan.json": job.plan,
    }
    if job.base_venue is not None:
        files["base_venue.json"] = job.base_venue.model_dump(mode="json")
    if job.attack is not None:
        files["attack.json"] = job.attack.model_dump(mode="json")
    if job.fix is not None:
        files["fix.json"] = job.fix.model_dump(mode="json")
    for name, data in files.items():
        (work / name).write_text(json.dumps(data))


def hand_over(work: Path, sim_user: str) -> None:
    """Give a run folder to the simulation user so it can write its results.

    Needed when the API runs as root (in Docker on Linux): the folder it creates would be
    root-owned and the non-root simulation container could not write `result.json`.
    """
    uid, _, gid = sim_user.partition(":")
    if not uid.isdigit():
        return
    owner, group = int(uid), int(gid) if gid.isdigit() else -1
    for path in [work, *work.rglob("*")]:
        os.chown(path, owner, group)


def read_result(work: Path, job: SimJob, provider: str, runs_root: Path) -> RunResult:
    """Parse result.json and make artifact paths relative to the project root."""
    raw = json.loads((work / "result.json").read_text())
    res = RunResult.model_validate(raw)
    rel = work.relative_to(runs_root.parent)
    arts = res.artifacts
    res.artifacts = RunArtifacts(
        **{k: (str(rel / v) if v else None) for k, v in arts.model_dump().items()}
    )
    res.provider = provider
    res.parent_run_id = job.request.parent_run_id
    res.venue_hash = job.request.venue_hash
    return res


def failed_result(
    job: SimJob, provider: str, message: str, status: str = "failed", runtime: float = 0.0
) -> RunResult:
    """A RunResult describing a failure in plain words."""
    r = job.request
    return RunResult(
        run_id=r.run_id,
        tier=r.tier,
        status=status,
        engine=r.engine,
        provider=provider,
        parent_run_id=r.parent_run_id,
        venue_hash=r.venue_hash,
        seed=r.seed,
        attack_id=r.attack_id,
        fix_id=r.fix_id,
        error=message,
        runtime_s=round(runtime, 2),
    )


def _acquire_lock(path: Path) -> Any:
    """Blocking exclusive file lock (fcntl), shared by every Showtime process."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")  # noqa: SIM115 - kept open while the lock is held
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    return fh


def _release_lock(fh: Any) -> None:
    import fcntl

    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


class DockerRunner:
    """Local sandbox: one container per run via the docker CLI."""

    provider = "docker"

    def __init__(
        self,
        runs_dir: Path,
        image: str,
        mem_limit: str,
        cpus: float,
        host_runs_dir: str = "",
        max_parallel: int = 1,
        sim_code_dir: Path | None = None,
        sim_user: str = "",
        platform: str = "",
    ) -> None:
        self.runs_dir = runs_dir
        self.image = image
        self.platform = platform
        self.mem_limit = mem_limit
        self.cpus = cpus
        self.host_runs_dir = host_runs_dir
        self.sem = asyncio.Semaphore(max_parallel)
        self.sim_code_dir = sim_code_dir  # dev: mount local sim/ over /app
        uid, gid = os.getuid(), os.getgid()
        # sims never run as root, even when the API itself runs as root in a container
        self.sim_user = sim_user or (f"{uid}:{gid}" if uid != 0 else "10001:10001")
        self._docker = shutil.which("docker") or "docker"

    async def prepare_base(self, venue: Venue) -> str:
        return f"local:{self.image}"

    def _host_path(self, work: Path) -> str:
        if self.host_runs_dir:
            return str(Path(self.host_runs_dir) / work.relative_to(self.runs_dir))
        return str(work.resolve())

    async def health(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._docker,
                "image",
                "inspect",
                self.image,
                "--format",
                "{{.Id}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _out, err = await asyncio.wait_for(proc.communicate(), timeout=10)
        except (OSError, TimeoutError) as exc:
            return {"ok": False, "detail": f"Docker is not reachable: {exc}"}
        if proc.returncode != 0:
            msg = err.decode()[:200]
            if "No such image" in msg or "not found" in msg.lower():
                return {
                    "ok": False,
                    "detail": f"Image {self.image} is missing. Run: make build-sim",
                }
            return {"ok": False, "detail": f"Docker error: {msg}"}
        return {"ok": True, "detail": f"Docker ready ({self.image})"}

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        async with self.sem:
            # one simulation at a time per machine, across processes (memory budget)
            lock = await asyncio.to_thread(_acquire_lock, self.runs_dir / ".sim.lock")
            try:
                return await self._run(job, on_progress)
            finally:
                _release_lock(lock)

    async def _run(self, job: SimJob, on_progress: ProgressFn | None) -> RunResult:
        req = job.request
        work = self.runs_dir / req.run_id
        if work.exists():
            shutil.rmtree(work)
        job.extra.setdefault("provider", self.provider)
        write_job_files(work, job)
        if os.getuid() == 0:
            hand_over(work, self.sim_user)
        name = f"showtime-sim-{req.run_id}"
        cmd = [
            self._docker,
            "run",
            "--rm",
            "--name",
            name,
            "--network=none",
            f"--memory={self.mem_limit}",
            f"--cpus={self.cpus}",
            "--pids-limit=256",
            "--security-opt=no-new-privileges",
            "--label",
            "com.showtime.project=true",
            "--user",
            self.sim_user,
            "-e",
            "MPLCONFIGDIR=/tmp",
            "-v",
            f"{self._host_path(work)}:/work",
        ]
        if self.platform:
            cmd += ["--platform", self.platform]
        if self.sim_code_dir is not None:
            cmd += ["-v", f"{self.sim_code_dir.resolve()}:/app:ro"]
        cmd += [self.image, "python", "/app/run_sim.py", "/work"]
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            return failed_result(job, self.provider, f"The simulation couldn't start: {exc}")
        deadline = t0 + req.max_wall_s + 30
        progress_file = work / "progress.json"
        last_seen = ""
        while True:
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
                break
            except TimeoutError:
                pass
            if on_progress and progress_file.exists():
                try:
                    txt = progress_file.read_text()
                    if txt and txt != last_seen:
                        last_seen = txt
                        on_progress(json.loads(txt))
                except (OSError, json.JSONDecodeError):
                    pass
            if time.monotonic() > deadline:
                await self._kill(name)
                await proc.wait()
                return failed_result(
                    job,
                    self.provider,
                    f"Stopped after {req.max_wall_s:.0f} s of wall-clock time.",
                    status="timeout",
                    runtime=time.monotonic() - t0,
                )
        stderr = (await proc.stderr.read()).decode()[-800:] if proc.stderr else ""
        if not (work / "result.json").exists():
            hint = "out of memory" if proc.returncode == 137 else stderr.strip()[-300:]
            return failed_result(
                job,
                self.provider,
                f"The simulation crashed (exit {proc.returncode}): {hint}",
                runtime=time.monotonic() - t0,
            )
        return read_result(work, job, self.provider, self.runs_dir)

    async def cancel(self, run_id: str) -> None:
        """Stop a running container."""
        await self._kill(f"showtime-sim-{run_id}")

    async def _kill(self, name: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            self._docker,
            "kill",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    async def close(self) -> None:
        return None


class FakeRunner:
    """Deterministic stand-in for tests and when no sandbox is available.

    It does not simulate: it scales the Tier 1 estimate and labels the result clearly.
    """

    provider = "fake"

    def __init__(
        self, runs_dir: Path, delay_s: float = 0.0, fail_ids: set[str] | None = None
    ) -> None:
        self.runs_dir = runs_dir
        self.delay_s = delay_s
        self.fail_ids = fail_ids or set()
        self.calls: list[str] = []

    async def prepare_base(self, venue: Venue) -> str:
        return "fake:base"

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "Fake sandbox (no simulation)"}

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        self.calls.append(job.request.run_id)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if job.request.run_id in self.fail_ids or any(
            part in job.request.run_id for part in self.fail_ids
        ):
            return failed_result(job, self.provider, "Injected failure (test)")
        base = job.tier1
        if base is None:
            return failed_result(job, self.provider, "FakeRunner needs a Tier 1 estimate")
        res = base.model_copy(deep=True)
        res.run_id = job.request.run_id
        res.tier = job.request.tier
        res.engine = "fake"
        res.provider = self.provider
        res.parent_run_id = job.request.parent_run_id
        res.attack_id = job.request.attack_id
        res.fix_id = job.request.fix_id
        res.seed = job.request.seed
        m = res.metrics
        if m.evac_time_p95_s is not None:
            m.evac_time_p95_s = round(m.evac_time_p95_s * 1.2, 1)
        if m.evac_time_max_s is not None:
            m.evac_time_max_s = round(m.evac_time_max_s * 1.2, 1)
        res.notes = [*res.notes, "Fake sandbox: scaled instant estimate, not a simulation."]
        return res

    async def close(self) -> None:
        return None
