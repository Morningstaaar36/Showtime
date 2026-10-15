"""Code jobs in a real container (slow: needs Docker and the sim image, SIM_IMAGE).

Proves the sandbox boundary, not just the pre-check: no network, read-only inputs, a wall
timeout, and the data helper reading real artifact formats.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from api.adapters.sandbox import CodeJob, DockerRunner
from api.tests.docker_check import docker_unavailable

pytestmark = pytest.mark.slow
IMAGE = os.environ.get("SIM_IMAGE", "showtime-sim:latest")


@pytest.fixture
def runner(tmp_path: Path) -> DockerRunner:
    reason = docker_unavailable(IMAGE)
    if reason:
        pytest.skip(reason)
    return DockerRunner(tmp_path / "runs", IMAGE, "1g", 1.0)


def _artifacts() -> dict[str, bytes]:
    """Two people walking towards exit E1 at (10, 0): a tiny run in the real file formats."""
    venue = {
        "floors": [
            {
                "floor_id": "F0",
                "exits": [
                    {
                        "id": "E1",
                        "label": "Gate B",
                        "polygon": [[9.5, -0.5], [10.5, -0.5], [10.5, 0.5], [9.5, 0.5]],
                        "width_m": 1.0,
                    }
                ],
                "zones": [],
            }
        ]
    }
    frames, offsets, pos = b"", [], 0
    times = [0.0, 1.0, 2.0, 3.0]
    for t in times:
        ids = np.array([1, 2], dtype="<u2")
        xs = np.array([4 + 2 * t, 3 + 2 * t]) / 0.02
        buf = (
            np.asarray([2], dtype="<u4").tobytes()
            + ids.tobytes()
            + xs.astype("<i2").tobytes()
            + np.zeros(2, dtype="<i2").tobytes()
            + np.zeros(2, dtype="u1").tobytes()
        )
        buf += b"\0" * ((-len(buf)) % 4)
        offsets.append(pos)
        frames += buf
        pos += len(buf)
    index = {"times": times, "offsets": offsets, "origin": [0, 0], "scale": 0.02, "floors": ["F0"]}
    return {
        "venue.json": json.dumps(venue).encode(),
        "traj.bin": frames,
        "traj_index.json": json.dumps(index).encode(),
        "result.json": json.dumps({"metrics": {"agents_total": 2}}).encode(),
    }


async def test_no_network_inside_the_sandbox(runner: DockerRunner) -> None:
    script = (
        "import socket\n"
        "socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "output = {'connected': True}\n"
    )
    res = await runner.run_code(CodeJob("net1", "user_script", script, timeout_s=10))
    assert res.status == "error", res
    assert "Network is unreachable" in res.stderr_tail or "OSError" in res.stderr_tail


async def test_inputs_are_read_only_and_loops_are_stopped(runner: DockerRunner) -> None:
    write = "open('/work/w1/result.json', 'w').write('x')\n"
    res = await runner.run_code(CodeJob("w1", "user_script", write, inputs={"result.json": b"{}"}))
    assert res.status == "error" and "Read-only file system" in res.stderr_tail
    loop = "while True:\n    pass\n"
    res = await runner.run_code(CodeJob("loop1", "user_script", loop, timeout_s=2))
    assert res.status == "timeout" and res.runtime_s < 20


async def test_the_data_helper_reads_the_run(runner: DockerRunner) -> None:
    script = (
        "import showtime_data as sd\n"
        "traj = sd.load_trajectories()\n"
        "q = sd.people_near('Gate B', radius_m=3.0)\n"
        "output = {'rows': len(traj), 'max_x': float(traj['x'].max()),\n"
        "          'queue': q['people'].tolist(), 'exit': sd.exits()['name'][0],\n"
        "          'people': sd.result()['metrics']['agents_total']}\n"
    )
    res = await runner.run_code(CodeJob("an1", "analysis", script, inputs=_artifacts()))
    assert res.status == "ok", res.stderr_tail
    assert res.output == {
        "rows": 8,
        "max_x": 10.0,
        "queue": [0, 0, 2, 2],
        "exit": "Gate B",
        "people": 2,
    }
