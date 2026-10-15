"""Why the Docker-backed tests can't run on this machine (None when they can).

`docker` on PATH is not enough: DOCKER_CONTEXT may point at a stopped Docker Desktop, or the
sim image may live in another context. Those tests skip with the reason instead of failing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache

TIMEOUT_S = 15


@lru_cache(maxsize=8)
def docker_unavailable(image: str | None = None) -> str | None:
    """A skip reason, or None when the daemon answers (and `image` exists, when given)."""
    exe = shutil.which("docker")
    if exe is None:
        return "docker CLI is not installed"
    where = (
        f"DOCKER_CONTEXT={os.environ['DOCKER_CONTEXT']}"
        if os.environ.get("DOCKER_CONTEXT")
        else "the current docker context"
    )
    try:
        r = subprocess.run(
            [exe, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Docker daemon did not answer within {TIMEOUT_S} s ({where})"
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["no answer"])[-1][:160]
        return f"Docker daemon is unreachable ({where}): {last}"
    if image:
        r = subprocess.run(
            [exe, "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
        if r.returncode != 0:
            return f"image {image} is not in {where}: build it (make build-sim) or set SIM_IMAGE"
    return None
