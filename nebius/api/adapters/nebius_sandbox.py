"""Nebius Sandboxes runner (SANDBOX_PROVIDER=nebius), built on contree-sdk 0.3.6.

Verified against the installed SDK (docs/NEBIUS_SWITCH.md):
- `Contree(base_url=..., token=...)`; `await client.images.oci("python:3.12-slim")`
- `image.run(shell=..., files={dest: bytes}, disposable=False, timeout=...)` returns a new
  child image (a snapshot we can branch from); awaiting it executes the command
- `await image.read(path)` reads a file from an image; `image.stdout`, `image.exit_code`

Branching: base image (deps + sim code) → venue node (venue.json) → attack node → fix node.
Every run is a child of its parent node, so the UI tree mirrors real sandbox snapshots.

Each run uses its own folder `/work/<run_id>/`: a child snapshot also holds its parent's
files, so reading a shared `/work/result.json` could return the parent's result when the
child's simulation fails. A run with `resume_from` branches from that run's snapshot and
copies `/work/<resume_from>/checkpoint.json` into its own folder before it starts.
Code jobs (`run_code`) run on the base image in a disposable sandbox.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shlex
import shutil
import time
from pathlib import Path
from typing import Any

from api.adapters.sandbox import (
    CODE_START_GRACE_S,
    RUN_ID_RE,
    CodeJob,
    CodeResult,
    ProgressFn,
    SimJob,
    code_files,
    failed_result,
    parse_code_output,
    read_result,
    write_job_files,
)
from api.core.settings import Settings
from api.models import RunResult, Venue

log = logging.getLogger("showtime.nebius")
ARTIFACTS = (
    "result.json",
    "traj.bin",
    "traj_index.json",
    "density.bin",
    "density_index.json",
    "checkpoint.json",
)
BASE_IMAGE = "python:3.12-slim"


def _sim_files(sim_dir: Path) -> dict[str, bytes]:
    """The simulation code as files for /app inside the sandbox."""
    out: dict[str, bytes] = {}
    for p in sorted(sim_dir.rglob("*")):
        if (
            p.is_file()
            and "tests" not in p.parts
            and "__pycache__" not in p.parts
            and p.suffix in (".py", ".json", ".txt")
        ):
            out[f"/app/{p.relative_to(sim_dir).as_posix()}"] = p.read_bytes()
    return out


class NebiusRunner:
    """Sandbox provider for Nebius Sandboxes (async contree-sdk client)."""

    provider = "nebius"

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.runs_dir = settings.runs_dir
        self.sem = asyncio.Semaphore(settings.sandbox_max_parallel)
        self._client = client
        self._base: Any | None = None
        self._venue_nodes: dict[str, Any] = {}
        self._nodes: dict[str, Any] = {}  # run_id -> image snapshot (for children)
        self.sim_dir = settings.root_dir / "sim"
        self.cache_file = settings.cache_dir / "nebius" / "base_image.json"

    def _get_client(self) -> Any:
        if self._client is None:
            from contree_sdk import Contree

            self._client = Contree(
                base_url=self.settings.nebius_sandbox_base_url, token=self.settings.nebius_api_key
            )
        return self._client

    async def health(self) -> dict[str, Any]:
        if not self.settings.nebius_api_key:
            return {"ok": False, "detail": "NEBIUS_API_KEY is not set."}
        try:
            info = await asyncio.wait_for(self._get_client().get_token_info(), timeout=10)
            return {
                "ok": True,
                "detail": f"Nebius Sandboxes ready ({getattr(info, 'name', 'token ok')})",
            }
        except Exception as exc:
            return {"ok": False, "detail": f"Nebius Sandboxes not reachable: {type(exc).__name__}"}

    def _code_hash(self) -> str:
        h = hashlib.sha256()
        for k, v in sorted(_sim_files(self.sim_dir).items()):
            h.update(k.encode())
            h.update(v)
        return h.hexdigest()[:16]

    async def _base_image(self) -> Any:
        """Base node: deps + sim code, cached by code hash (cache/nebius/base_image.json)."""
        if self._base is not None:
            return self._base
        client = self._get_client()
        code_hash = self._code_hash()
        if self.cache_file.exists():
            cached = json.loads(self.cache_file.read_text())
            if cached.get("code_hash") == code_hash:
                try:
                    self._base = await client.images.use(cached["image"])
                    return self._base
                except Exception:
                    log.info("cached base image unavailable; rebuilding")
        img = await client.images.oci(BASE_IMAGE)
        reqs = (self.sim_dir / "requirements.txt").read_bytes()
        img = await img.run(
            shell="pip install --no-cache-dir -r /tmp/requirements.txt && "
            "pip install --no-cache-dir --no-deps jupedsim==1.4.2",
            files={"/tmp/requirements.txt": reqs},
            disposable=False,
            timeout=900,
        )
        img = await img.apply_files(files=_sim_files(self.sim_dir))
        self._base = img
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps({"code_hash": code_hash, "image": str(img.uuid), "created": time.time()})
        )
        return img

    async def prepare_base(self, venue: Venue) -> str:
        """Venue node (tree root): base image + venue.json."""
        key = hashlib.sha256(venue.model_dump_json().encode()).hexdigest()[:16]
        if key not in self._venue_nodes:
            base = await self._base_image()
            self._venue_nodes[key] = await base.apply_files(
                files={"/work/venue.json": venue.model_dump_json().encode()}
            )
        return str(self._venue_nodes[key].uuid)

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        async with self.sem:
            t0 = time.monotonic()
            req = job.request
            try:
                return await self._run(job)
            except Exception as exc:
                log.warning("nebius run %s failed: %s", req.run_id, exc)
                return failed_result(
                    job,
                    self.provider,
                    f"Nebius sandbox error: {exc}",
                    runtime=time.monotonic() - t0,
                )

    async def _run(self, job: SimJob) -> RunResult:
        req = job.request
        rid = req.run_id
        if not RUN_ID_RE.match(rid):
            raise ValueError(f"not a run id: {rid!r}")
        venue = job.base_venue or job.venue
        await self.prepare_base(venue)
        key = hashlib.sha256(venue.model_dump_json().encode()).hexdigest()[:16]
        parent = self._nodes.get(job.parent_node or "") or self._venue_nodes[key]
        work = self.runs_dir / rid
        if work.exists():  # a stale result.json from an earlier attempt must not be uploaded
            shutil.rmtree(work)
        job.extra["provider"] = self.provider
        write_job_files(work, job)
        folder = f"/work/{rid}"
        files = {f"{folder}/{p.name}": p.read_bytes() for p in work.glob("*.json")}
        steps = [f"mkdir -p {shlex.quote(folder)}"]
        if job.resume_from is not None:
            src = job.resume_from
            if not RUN_ID_RE.match(src) or ".." in src:
                raise ValueError(f"not a run id: {src!r}")
            if src in self._nodes:  # branch from the very snapshot that holds the checkpoint
                parent = self._nodes[src]
                steps.append(
                    f"cp {shlex.quote(f'/work/{src}/checkpoint.json')} "
                    f"{shlex.quote(f'{folder}/checkpoint.json')}"
                )
            else:  # snapshot unknown (e.g. after a restart): upload the local copy instead
                local = self.runs_dir / src / "checkpoint.json"
                if not local.is_file():
                    return failed_result(
                        job,
                        self.provider,
                        f"Run {src} has no saved moment (checkpoint.json) to start from.",
                    )
                files[f"{folder}/checkpoint.json"] = local.read_bytes()
        steps.append(f"cd /app && python run_sim.py {shlex.quote(folder)}")
        done = await parent.run(
            shell=" && ".join(steps),
            files=files,
            disposable=False,
            timeout=int(req.max_wall_s) + 60,
        )
        self._nodes[rid] = done
        for name in ARTIFACTS:
            try:
                (work / name).write_bytes(await done.read(f"{folder}/{name}"))
            except Exception:
                if name == "result.json":
                    raise RuntimeError(
                        f"the simulation wrote no result in {folder} (it may have crashed)"
                    ) from None
        return read_result(work, job, self.provider, self.runs_dir)

    async def run_code(self, job: CodeJob) -> CodeResult:
        """A code job on the base image (sim deps + run_code.py), in a disposable sandbox."""
        t0 = time.monotonic()
        try:
            files = {f"/work/{rel}": data for rel, data in code_files(job).items()}
        except ValueError as exc:
            return CodeResult("error", stderr_tail=str(exc))
        folder = shlex.quote(f"/work/{job.job_id}")
        shell = f"cd /app && SHOWTIME_TIMEOUT_S={job.timeout_s:g} python run_code.py {folder}"
        async with self.sem:
            try:
                base = await self._base_image()
                done = await base.run(
                    shell=shell,
                    files=files,
                    disposable=True,
                    timeout=int(job.timeout_s + CODE_START_GRACE_S),
                )
            except Exception as exc:
                runtime = time.monotonic() - t0
                if "timedout" in type(exc).__name__.lower().replace("_", ""):
                    return parse_code_output(None, "", "", runtime, timed_out=True)
                log.warning("nebius code job %s failed: %s", job.job_id, exc)
                return CodeResult(
                    "error", stderr_tail=f"Nebius sandbox error: {exc}", runtime_s=round(runtime, 2)
                )
        return parse_code_output(
            int(getattr(done, "exit_code", 1)),
            _text(getattr(done, "stdout", "")),
            _text(getattr(done, "stderr", "")),
            time.monotonic() - t0,
        )

    async def close(self) -> None:
        return None


def _text(value: Any) -> str:
    """Sandbox output as text (the SDK may give str, bytes or a file-like object)."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if hasattr(value, "getvalue"):
        return _text(value.getvalue())
    return str(value)
