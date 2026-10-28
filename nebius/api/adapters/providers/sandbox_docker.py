"""Sandbox: one local Docker container per run (no network, read-only, capped)."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import SANDBOX
from api.adapters.providers.base import Requirement, SandboxProvider
from api.adapters.providers.checks import sandbox_check


def _build(s: Any) -> Any:
    from api.adapters.sandbox import DockerRunner

    return DockerRunner(
        s.runs_dir,
        s.sim_image,
        s.sim_mem_limit,
        s.sim_cpus,
        host_runs_dir=s.host_runs_dir,
        max_parallel=s.sandbox_max_parallel,
        sim_code_dir=s.root_dir / "sim" if s.sim_dev_mount else None,
        sim_user=s.sim_user,
        platform=s.sim_platform,
        pids_limit=s.sim_pids_limit,
        code_pids_limit=s.code_pids_limit,
        code_cpus=s.code_max_cpus,
        sim_tmp_mb=s.sim_tmp_mb,
        code_tmp_mb=s.code_tmp_mb,
    )


SANDBOX.register(
    SandboxProvider(
        kind="sandbox",
        name="docker",
        title="Local Docker",
        requirements=(Requirement("SIM_IMAGE", "sim_image", "the simulation image"),),
        check_live=sandbox_check,
        build=_build,
    )
)
