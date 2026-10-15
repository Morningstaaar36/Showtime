"""DockerRunner process handling, with a stand-in `docker` executable (no Docker needed)."""

from __future__ import annotations

import asyncio
import json
import stat
import sys
from pathlib import Path

import pytest

from api.adapters.sandbox import DockerRunner, SimJob
from api.core.templates import get_template
from api.models import RunRequest

FAKE_DOCKER = """#!{python}
import json, os, sys, time
args = sys.argv[1:]
log = os.environ["FAKE_DOCKER_LOG"]
with open(log, "a") as fh:
    fh.write(json.dumps(args) + "\\n")
pidfile = log + ".pid"
if args[0] == "kill" and os.path.exists(pidfile):
    os.kill(int(open(pidfile).read()), 15)
if args[0] == "run":
    open(pidfile, "w").write(str(os.getpid()))
    work = next(a.split(":")[0] for a in args if a.endswith(":/work"))
    mode = os.environ.get("FAKE_DOCKER_MODE", "chatty")
    if mode == "hang":
        time.sleep(60)
    # far more than a pipe buffer (64 KiB) on both streams
    sys.stdout.write("x" * 400_000)
    sys.stdout.flush()
    sys.stderr.write("warning: agent too close\\n" * 20_000)
    sys.stderr.flush()
    with open(os.path.join(work, "result.json"), "w") as fh:
        json.dump({{"run_id": os.path.basename(work), "tier": 3, "status": "ok"}}, fh)
"""


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    exe = tmp_path / "docker"
    exe.write_text(FAKE_DOCKER.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    return exe


def _runner(tmp_path: Path, exe: Path) -> DockerRunner:
    r = DockerRunner(tmp_path / "runs", "showtime-sim:test", "1g", 1.0)
    r._docker = str(exe)
    return r


def _job(run_id: str) -> SimJob:
    venue = get_template("school_wing")
    req = RunRequest(run_id=run_id, venue_id=venue.venue_id, max_wall_s=2)
    return SimJob(request=req, venue=venue, events=[], plan={}, sim_settings={})


def _calls(tmp_path: Path) -> list[list[str]]:
    lines = (tmp_path / "docker.log").read_text().splitlines()
    return [json.loads(x) for x in lines]


@pytest.mark.asyncio
async def test_chatty_sim_does_not_stall_on_a_full_pipe(tmp_path: Path, fake_docker: Path) -> None:
    runner = _runner(tmp_path, fake_docker)
    res = await asyncio.wait_for(runner.run(_job("r_chatty")), timeout=20)
    assert res.status == "ok", res.error
    run_args = _calls(tmp_path)[0]
    for flag in ("--network=none", "--cap-drop=ALL", "--read-only", "--pull=never"):
        assert flag in run_args
    assert "--memory-swap=1g" in run_args


@pytest.mark.asyncio
async def test_cancelled_run_kills_its_container(
    tmp_path: Path, fake_docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "hang")
    runner = _runner(tmp_path, fake_docker)
    task = asyncio.ensure_future(runner.run(_job("r_cancel")))
    await asyncio.sleep(1.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ["kill", "showtime-sim-r_cancel"] in _calls(tmp_path)
    await asyncio.sleep(0.2)  # the stand-in exits on kill like `docker run` does
