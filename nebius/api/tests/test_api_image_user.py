"""The API container drops to the owner of the mounted runs/ folder, with the Docker socket's
group, by itself: plain `docker compose up` (no make, no variables) can still start sandboxes.
Slow: needs Docker and the showtime-api image."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from api.tests.docker_check import docker_unavailable

pytestmark = pytest.mark.slow
IMAGE = os.environ.get("API_IMAGE", "showtime-api:latest")
SOCK = Path("/var/run/docker.sock")


def test_the_api_runs_as_the_runs_owner_with_the_docker_group(tmp_path: Path) -> None:
    reason = docker_unavailable(IMAGE)
    if reason:
        pytest.skip(reason)
    if not SOCK.exists():
        pytest.skip("no Docker socket on this machine")
    out = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{tmp_path}:/app/runs",
            "-v",
            f"{SOCK}:{SOCK}",
            IMAGE,
            "sh",
            "-c",
            "id -u; id -g; id -G; docker version --format '{{.Server.Version}}'",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    uid, gid, groups, server = out.stdout.split("\n")[:4]
    assert (int(uid), int(gid)) == (tmp_path.stat().st_uid, tmp_path.stat().st_gid)
    assert str(SOCK.stat().st_gid) in groups.split()
    assert server  # it reached the Docker daemon as that user
