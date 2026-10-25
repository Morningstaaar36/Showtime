"""Keep a runaway allocation inside the process: a heap limit just under the container's memory.

Without it, AI-written code that asks for gigabytes (`[0] * 10**9`) makes the kernel kill the
whole container, and the run is lost. With it, the allocation fails with MemoryError inside the
script, the script is stopped with that reason, and the simulation carries on.
Stdlib only: this file runs inside the sandbox image.
"""

from __future__ import annotations

import resource
from pathlib import Path

SHARE = 0.85  # of the container's memory; the rest is the interpreter, libraries and buffers
CGROUP_FILES = ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")


def container_limit(files: tuple[str, ...] = CGROUP_FILES) -> int | None:
    """The container's memory limit in bytes, or None when there is none to read."""
    for name in files:
        try:
            text = Path(name).read_text().strip()
        except OSError:
            continue
        if text.isdigit() and int(text) < 1 << 60:  # cgroup v1 reports "no limit" as ~2^63
            return int(text)
    return None


def _status_kb(field: str, status: str = "/proc/self/status") -> int | None:
    for line in Path(status).read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1])
    return None


def cap_memory(files: tuple[str, ...] = CGROUP_FILES) -> int | None:
    """Limit further heap growth to SHARE of what the container has left; returns the cap in
    bytes (None: no container limit to read, left alone).

    RLIMIT_DATA counts virtual data, and loaded libraries (numpy, JuPedSim) reserve much more
    than they use, so the cap is "virtual data now + room left in the container", set once the
    simulator is loaded, just before untrusted code runs.
    """
    limit = container_limit(files)
    data_kb, rss_kb = _status_kb("VmData"), _status_kb("VmRSS")
    if limit is None or data_kb is None or rss_kb is None:
        return None
    room = max(limit - rss_kb * 1024, 0)
    cap = data_kb * 1024 + int(room * SHARE)
    _soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
    if hard != resource.RLIM_INFINITY:
        cap = min(cap, hard)
    resource.setrlimit(resource.RLIMIT_DATA, (cap, hard))
    return cap
