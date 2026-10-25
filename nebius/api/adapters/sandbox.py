"""Sandbox providers: run one simulation job in an isolated environment.

`DockerRunner` (local default) starts one `showtime-sim` container per run with
`--network=none`, a non-root user and memory/CPU caps. Branching is logical: the parent
node id is stored on the result so the UI can draw the tree. `NebiusRunner` lives in
`api/adapters/nebius_sandbox.py` and implements the same protocol.

Code jobs (`run_code`) run AI- or user-written Python in the same image and the same
isolation: the inputs and `script.py` go to `/work/<job_id>/` (read-only) and
`python /app/run_code.py /work/<job_id>` prints the script's JSON result as its last line.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

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
    # run id whose checkpoint.json this run starts from (rewind and branch)
    resume_from: str | None = None


CodeKind = Literal["analysis", "user_script"]
CodeStatus = Literal["ok", "error", "timeout"]
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
INPUT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
TAIL_CHARS = 2000
CODE_START_GRACE_S = 15.0  # container start and imports, on top of the script's own budget
TIMEOUT_EXIT = 124  # run_code.py exits with this when the script ran out of time


@dataclass
class CodeJob:
    """One piece of AI- or user-written Python to run in a sandbox."""

    job_id: str
    kind: CodeKind
    script: str
    inputs: dict[str, bytes] = field(default_factory=dict)  # file name -> bytes, read-only
    timeout_s: float = 30
    mem: str = "1g"


@dataclass
class CodeResult:
    """What a code job printed and how it ended."""

    status: CodeStatus
    output: Any = None  # the JSON the script printed on its last stdout line
    stdout_tail: str = ""
    stderr_tail: str = ""
    runtime_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "runtime_s": self.runtime_s,
        }


def check_code_job(job: CodeJob) -> None:
    """Refuse job ids and input names that could leave the job's own folder."""
    if not JOB_ID_RE.match(job.job_id):
        raise ValueError(f"invalid code job id: {job.job_id!r}")
    for name in job.inputs:
        if not INPUT_NAME_RE.match(name) or name == "script.py":
            raise ValueError(f"invalid input file name: {name!r}")


def code_files(job: CodeJob) -> dict[str, bytes]:
    """Paths (relative to /work) and bytes of everything a code job needs."""
    check_code_job(job)
    files = {f"{job.job_id}/{name}": data for name, data in job.inputs.items()}
    files[f"{job.job_id}/script.py"] = job.script.encode()
    return files


def _tail(text: str) -> str:
    return text[-TAIL_CHARS:]


def parse_code_output(
    exit_code: int | None, stdout: str, stderr: str, runtime_s: float, *, timed_out: bool = False
) -> CodeResult:
    """A CodeResult from what `run_code.py` printed (its last stdout line is the JSON)."""
    runtime = round(runtime_s, 2)
    if timed_out or exit_code == TIMEOUT_EXIT:
        msg = stderr.strip() or "The script ran out of time and was stopped."
        return CodeResult("timeout", None, _tail(stdout), _tail(msg), runtime)
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    output: Any = None
    if lines:
        try:
            output = json.loads(lines[-1])
            lines = lines[:-1]
        except ValueError:
            output = None
    body = "\n".join(lines)
    if exit_code != 0:
        hint = "out of memory" if exit_code == 137 else f"exit {exit_code}"
        err = stderr.strip() or f"The script stopped with an error ({hint})."
        return CodeResult("error", None, _tail(body), _tail(err), runtime)
    return CodeResult("ok", output, _tail(body), _tail(stderr), runtime)


@dataclass(frozen=True)
class Isolation:
    """What a sandbox guarantees for every run, as facts the UI can show (no provider names)."""

    kind: Literal["container", "cloud", "none"]
    network_off: bool | None  # None: the provider's default, not set per job
    memory: str | None
    cpus: float | None
    read_only: bool
    process_limit: int | None
    non_root: bool
    per_job_limits: bool  # network and memory limits set for each run

    def summary(self) -> str:
        """One plain sentence."""
        if self.kind == "none":
            return "No sandbox: no simulation runs (preview numbers only)."
        if not self.per_job_limits:
            return (
                "Each run gets its own cloud sandbox. Per-run network and memory limits can't be "
                "set there, so the static check and the in-sandbox budgets are the protection."
            )
        parts = ["one container per run"]
        if self.network_off:
            parts.append("no network")
        if self.memory:
            parts.append(f"{_bytes_label(self.memory)} memory")
        if self.cpus:
            parts.append(f"{self.cpus:g} CPU")
        if self.read_only:
            parts.append("read-only system")
        if self.process_limit:
            parts.append(f"at most {self.process_limit} processes")
        if self.non_root:
            parts.append("no admin rights")
        text = ", ".join(parts)
        return text[:1].upper() + text[1:] + "."

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "summary": self.summary()}


def _bytes_label(docker_size: str) -> str:
    """Docker's "2g" / "512m" as "2 GB" / "512 MB" (anything else as given)."""
    m = re.fullmatch(r"\s*([0-9.]+)\s*([kmg])b?\s*", docker_size, re.IGNORECASE)
    return f"{m.group(1)} {m.group(2).upper()}B" if m else docker_size


NO_SANDBOX = Isolation("none", None, None, None, False, None, False, False)


class SandboxRunner(Protocol):
    """Provider-agnostic sandbox interface."""

    provider: str
    isolation: Isolation
    parallel: int  # how many runs it takes at once (SANDBOX_MAX_PARALLEL; one for local Docker)
    fallback_reason: str | None  # why this runner stands in for the chosen one (None: it is it)

    async def prepare_base(self, venue: Venue) -> str:
        """Prepare (or reuse) the base environment; returns a node id for the tree root."""

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        """Run the job; artifacts end up under runs/<run_id>/."""

    async def run_code(self, job: CodeJob) -> CodeResult:
        """Run one code job in a fresh sandbox (no network, non-root, capped, timed)."""

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


CODE_DIR = "_code"  # code job folders under runs/ (removed after each job)
MEM_RE = re.compile(r"^\d{1,5}[mg]$")
STDOUT_KEEP = 512_000  # the JSON result is the last line: keep the tail only
STDERR_KEEP = 16_000
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def copy_checkpoint(runs_dir: Path, resume_from: str, work: Path) -> str | None:
    """Copy runs/<resume_from>/checkpoint.json into a new run folder; a problem in words."""
    if not RUN_ID_RE.match(resume_from) or ".." in resume_from:
        return f"Can't resume from run {resume_from!r}: not a run id."
    src = runs_dir / resume_from / "checkpoint.json"
    if not src.is_file():
        return f"Run {resume_from} has no saved moment (checkpoint.json) to start from."
    shutil.copyfile(src, work / "checkpoint.json")
    return None


async def _read_tail(stream: asyncio.StreamReader, keep: int) -> str:
    """Read a stream to its end, keeping only the last `keep` bytes (bounded memory)."""
    buf = b""
    while chunk := await stream.read(65536):
        buf = (buf + chunk)[-keep:]
    return buf.decode(errors="replace")


def _acquire_lock(path: Path) -> Any:
    """Blocking exclusive file lock (fcntl), shared by every Showtime process."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")  # noqa: SIM115 - kept open while the lock is held
    # the Docker stack's API runs as root; let host tools sharing runs/ open the same lock
    with contextlib.suppress(OSError):
        os.chmod(path, 0o666)
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
        pids_limit: int = 256,
        code_pids_limit: int = 64,
    ) -> None:
        self.runs_dir = runs_dir
        self.pids_limit = pids_limit
        self.code_pids_limit = code_pids_limit
        self.image = image
        self.platform = platform
        self.mem_limit = mem_limit
        self.cpus = cpus
        self.host_runs_dir = host_runs_dir
        self.parallel = max(1, max_parallel)
        self.fallback_reason: str | None = None
        self.sem = asyncio.Semaphore(self.parallel)
        self.code_sem = asyncio.Semaphore(1)
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

    @property
    def isolation(self) -> Isolation:
        return Isolation(
            kind="container",
            network_off=True,
            memory=self.mem_limit,
            cpus=self.cpus,
            read_only=True,
            process_limit=self.pids_limit,
            non_root=True,
            per_job_limits=True,
        )

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
                if on_progress is not None:
                    on_progress({"sandbox_started": True})  # it had to wait its turn until now
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
        if job.resume_from is not None:
            problem = copy_checkpoint(self.runs_dir, job.resume_from, work)
            if problem:
                return failed_result(job, self.provider, problem)
        if os.getuid() == 0:
            hand_over(work, self.sim_user)
        name = f"showtime-sim-{req.run_id}"
        cmd = [
            self._docker,
            "run",
            "--rm",
            "--name",
            name,
            "--pull=never",
            "--network=none",
            f"--memory={self.mem_limit}",
            f"--memory-swap={self.mem_limit}",
            f"--cpus={self.cpus}",
            f"--pids-limit={self.pids_limit}",
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",
            # scenario scripts run in here: only /work (this run's folder) and /tmp writable
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
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
            # stdout is not used; stderr is drained as it comes so a chatty sim can never
            # fill the pipe and stall until the wall-clock limit
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            return failed_result(job, self.provider, f"The simulation couldn't start: {exc}")
        assert proc.stderr is not None
        err_reader = asyncio.ensure_future(_read_tail(proc.stderr, STDERR_KEEP))
        deadline = t0 + req.max_wall_s + 30
        progress_file = work / "progress.json"
        last_seen = ""
        try:
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
                    err_reader.cancel()
                    await self._kill(name)
                    await proc.wait()
                    return failed_result(
                        job,
                        self.provider,
                        f"Stopped after {req.max_wall_s:.0f} s of wall-clock time.",
                        status="timeout",
                        runtime=time.monotonic() - t0,
                    )
        except asyncio.CancelledError:
            # the run was cancelled from anywhere (session stop, shutdown): never leave
            # the container running on its own
            err_reader.cancel()
            await asyncio.shield(self._kill(name))
            raise
        try:
            stderr = (await asyncio.wait_for(err_reader, timeout=5))[-800:]
        except TimeoutError:
            stderr = ""
        if not (work / "result.json").exists():
            hint = "out of memory" if proc.returncode == 137 else stderr.strip()[-300:]
            return failed_result(
                job,
                self.provider,
                f"The simulation crashed (exit {proc.returncode}): {hint}",
                runtime=time.monotonic() - t0,
            )
        return read_result(work, job, self.provider, self.runs_dir)

    async def run_code(self, job: CodeJob) -> CodeResult:
        """One code container at a time per machine (memory budget), separate from sims."""
        async with self.code_sem:
            lock = await asyncio.to_thread(_acquire_lock, self.runs_dir / ".code.lock")
            try:
                return await self._run_code(job)
            finally:
                _release_lock(lock)

    async def _run_code(self, job: CodeJob) -> CodeResult:
        try:
            files = code_files(job)
        except ValueError as exc:
            return CodeResult("error", stderr_tail=str(exc))
        if not MEM_RE.match(job.mem):
            return CodeResult("error", stderr_tail=f"invalid memory limit: {job.mem!r}")
        root = self.runs_dir / CODE_DIR
        work = root / job.job_id
        shutil.rmtree(work, ignore_errors=True)
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        if os.getuid() == 0:
            hand_over(work, self.sim_user)
            # the shared code folder stays usable by host tools (the API may run as root)
            with contextlib.suppress(OSError):
                os.chmod(root, 0o777)
        name = f"showtime-code-{job.job_id}"
        cmd = [
            self._docker,
            "run",
            "--rm",
            "--name",
            name,
            "--pull=never",
            "--network=none",
            f"--memory={job.mem}",
            f"--memory-swap={job.mem}",
            f"--cpus={min(self.cpus, 2.0)}",
            f"--pids-limit={self.code_pids_limit}",
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--label",
            "com.showtime.project=true",
            "--user",
            self.sim_user,
            "-e",
            "MPLCONFIGDIR=/tmp",
            "-e",
            f"SHOWTIME_TIMEOUT_S={job.timeout_s:g}",
            "-v",
            f"{self._host_path(work)}:/work/{job.job_id}:ro",
        ]
        if self.platform:
            cmd += ["--platform", self.platform]
        if self.sim_code_dir is not None:
            cmd += ["-v", f"{self.sim_code_dir.resolve()}:/app:ro"]
        cmd += [self.image, "python", "/app/run_code.py", f"/work/{job.job_id}"]
        t0 = time.monotonic()
        try:
            return await self._exec_code(cmd, name, job, t0)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    async def _exec_code(self, cmd: list[str], name: str, job: CodeJob, t0: float) -> CodeResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            return CodeResult("error", stderr_tail=f"The sandbox couldn't start: {exc}")
        assert proc.stdout is not None and proc.stderr is not None
        readers = asyncio.gather(
            _read_tail(proc.stdout, STDOUT_KEEP), _read_tail(proc.stderr, STDERR_KEEP)
        )
        try:
            out, err = await asyncio.wait_for(
                asyncio.shield(readers), timeout=job.timeout_s + CODE_START_GRACE_S
            )
            code = await proc.wait()
        except TimeoutError:
            await self._kill(name)
            await proc.wait()
            out, err = await readers
            return parse_code_output(None, out, err, time.monotonic() - t0, timed_out=True)
        except asyncio.CancelledError:
            # stop the container before the caller's cleanup removes its mounted inputs
            await asyncio.shield(self._kill(name))
            raise
        return parse_code_output(code, out, err, time.monotonic() - t0)

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
    Concurrency is bounded like the real runners (`max_parallel`); `max_active` records the
    most runs it ever had in flight. A checkpoint run writes a small `checkpoint.json`, and a
    run with `resume_from` copies that file into its own folder (or fails without it).
    """

    provider = "fake"
    isolation = NO_SANDBOX

    def __init__(
        self,
        runs_dir: Path,
        delay_s: float = 0.0,
        fail_ids: set[str] | None = None,
        code_results: list[CodeResult | Callable[[CodeJob], CodeResult]] | None = None,
        max_parallel: int = 4,
    ) -> None:
        self.runs_dir = runs_dir
        self.delay_s = delay_s
        self.fail_ids = fail_ids or set()
        self.calls: list[str] = []
        self.code_jobs: list[CodeJob] = []
        # scripted code results, used in order; when empty, run_code returns an empty "ok"
        self.code_results = list(code_results or [])
        self.parallel = max(1, max_parallel)
        self.fallback_reason: str | None = None
        self.sem = asyncio.Semaphore(self.parallel)
        self.active = 0
        self.max_active = 0
        self.resumed: dict[str, str] = {}

    async def run_code(self, job: CodeJob) -> CodeResult:
        """Executes nothing: records the job and returns the next scripted result."""
        try:
            check_code_job(job)
        except ValueError as exc:
            return CodeResult("error", stderr_tail=str(exc))
        self.code_jobs.append(job)
        if not self.code_results:
            return CodeResult("ok", None)
        item = self.code_results.pop(0)
        return item(job) if callable(item) else item

    async def prepare_base(self, venue: Venue) -> str:
        return "fake:base"

    async def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "Fake sandbox (no simulation)"}

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        async with self.sem:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if on_progress is not None:
                on_progress({"sandbox_started": True})
            try:
                return await self._run(job)
            finally:
                self.active -= 1

    def _checkpoint(self, job: SimJob) -> str | None:
        """Write or inherit checkpoint.json; returns an error message when it can't."""
        req = job.request
        work = self.runs_dir / req.run_id
        if job.resume_from:
            src = self.runs_dir / job.resume_from / "checkpoint.json"
            if not src.exists():
                return f"No checkpoint to resume from (run {job.resume_from})."
            work.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, work / "checkpoint.json")
            self.resumed[req.run_id] = job.resume_from
        elif req.checkpoint_at_s is not None:
            work.mkdir(parents=True, exist_ok=True)
            (work / "checkpoint.json").write_text(
                json.dumps({"t_s": req.checkpoint_at_s, "run_id": req.run_id, "fake": True})
            )
        return None

    async def _run(self, job: SimJob) -> RunResult:
        self.calls.append(job.request.run_id)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        problem = self._checkpoint(job)
        if problem:
            return failed_result(job, self.provider, problem)
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
        if job.resume_from:
            res.notes.append(f"Started from the checkpoint of run {job.resume_from}.")
        return res

    async def close(self) -> None:
        return None
