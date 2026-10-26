"""Attacks on the sandbox: AI-written scenario scripts that try to get out, run through the real
production path (RunService.build_job -> DockerRunner, the flags the app uses).

Each attack must be refused by the static check, or stopped inside the container with a clear
reason, and the simulation must still finish. Slow: needs Docker and the sim image; without them
the container half skips (the static half always runs).

With SANDBOX_PROOF_OUT=<file> (make sandbox-proof) the suite also writes what happened, row by
row, as the sandbox reported it: the app's Help page and docs/SANDBOX_PROOF.md show that file.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import DockerRunner
from api.agents.red_team import script_attack
from api.app.state import build_state
from api.core.scripts import check_script
from api.core.templates import get_template
from api.models import RunResult, Venue
from api.tests.docker_check import docker_unavailable
from api.tests.evidence_fakes import reset_engine, use_test_settings
from api.tests.test_redteam import _incidents

IMAGE = os.environ.get("SIM_IMAGE", "showtime-sim:latest")
PROOF_OUT = os.environ.get("SANDBOX_PROOF_OUT", "")
# what each attack tries, in plain words (shown with the results)
LABELS = {
    "import socket": "Connect to the internet",
    "import os": "Run shell commands",
    "open a file": "Open a file",
    "dunder escape": "Reach Python's internals (__class__)",
    "frame walk": "Walk interpreter frames",
    "endless loop": "Run forever",
    "huge memory": "Grab 8 GB of memory",
    "action flood": "Flood the crowd with actions",
    "network": "Connect to the internet",
    "write a file": "Write a file",
    "read secrets": "Read the environment for API keys",
    "fork bomb": "Start thousands of processes",
}
_rows: dict[tuple[str, str], dict[str, Any]] = {}


def _record(kind: str, name: str, **fields: Any) -> None:
    row = _rows.setdefault((kind, name), {"kind": kind, "name": name, "label": LABELS[name]})
    row.update(fields)


def _docker_version() -> str:
    out = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


@pytest.fixture(scope="module", autouse=True)
def proof_file() -> Iterator[None]:
    yield
    if not PROOF_OUT or not any("inside" in r for r in _rows.values()):
        return  # nothing ran in a container: no proof to record
    proof = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "docker": _docker_version(),
        "image": IMAGE,
        "command": "make sandbox-proof",
        "rows": list(_rows.values()),
    }
    Path(PROOF_OUT).write_text(json.dumps(proof, indent=1) + "\n")


def body(lines: str) -> str:
    return "def on_step(view, act):\n" + "".join(f"    {ln}\n" for ln in lines.splitlines())


# (name, code, refused statically, words the stop reason must contain)
ATTACKS: list[tuple[str, str, bool, str]] = [
    (
        "import socket",
        "import socket\n" + body("socket.create_connection(('1.1.1.1', 53))"),
        True,
        "import of 'socket' is not allowed",
    ),
    (
        "import os",
        "import os\n" + body("os.system('cat /etc/passwd')"),
        True,
        "import of 'os' is not allowed",
    ),
    ("open a file", body("open('/work/request.json').read()"), True, "'open' is not allowed"),
    ("dunder escape", body("().__class__.__bases__[0].__subclasses__()"), True, "'__class__'"),
    ("frame walk", body("g = (x for x in [1])\ng.gi_frame.f_back"), True, "'gi_frame'"),
    ("endless loop", body("while True:\n    pass"), False, "one step"),
    ("huge memory", body("x = [0] * (10 ** 9)"), False, "more memory than the sandbox allows"),
    (
        "action flood",
        body("for i in range(100000):\n    act.note('flood')\n    act.slow_down(0.5)"),
        False,
        "one step",
    ),
]


@pytest.mark.parametrize(("name", "code", "static", "reason"), ATTACKS, ids=[a[0] for a in ATTACKS])
def test_the_static_check_refuses_exactly_the_escapes(
    name: str, code: str, static: bool, reason: str
) -> None:
    problems = check_script(code)
    _record("scenario", name, static=problems[0] if problems else None)
    if static:
        assert problems and any(reason in p for p in problems), problems
    else:
        # runtime attacks pass the static check: the sandbox has to stop them
        assert problems == [], problems


@pytest.fixture
def docker_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    reason = docker_unavailable(IMAGE)
    if reason:
        pytest.skip(reason)
    settings = use_test_settings(tmp_path, monkeypatch)
    runner = DockerRunner(settings.runs_dir, IMAGE, "1g", 1.0)
    st = build_state(settings, llm=FakeLLM({}, settings), runner=runner)
    yield st
    reset_engine()


def _small_room() -> Venue:
    v = get_template("school_wing")
    for f in v.floors:
        for z in f.zones:
            z.people = min(z.people, 10)
    return v


async def _run(st: Any, code: str, static: bool) -> RunResult:
    if static:
        # the API refuses this script before any job exists; write it into the job as if it had
        # slipped past, to prove the container's own check refuses it too
        job = st.runs.build_job(_small_room(), tier=2, seed=3)
        job.events = [{"type": "script", "title": "Slipped past", "code": code, "every_s": 1.0}]
    else:
        attack = script_attack("Attack on the sandbox", code, _incidents()[0], "A1", every_s=1.0)
        job = st.runs.build_job(_small_room(), tier=2, attack=attack, seed=3)
    result: RunResult = await st.runs.runner.run(job)
    return result


@pytest.mark.slow
@pytest.mark.parametrize(("name", "code", "static", "reason"), ATTACKS, ids=[a[0] for a in ATTACKS])
async def test_inside_the_container_the_attack_is_stopped_and_the_run_finishes(
    docker_state: Any, name: str, code: str, static: bool, reason: str
) -> None:
    res = await _run(docker_state, code, static)
    stopped = [n for n in res.notes if n.startswith("scenario script stopped:")]
    _record(
        "scenario",
        name,
        inside=stopped[0].removeprefix("scenario script stopped: ") if stopped else None,
        status=res.status,
        runtime_s=round(res.runtime_s, 1),
        injected=static,  # refused by the API, so written into the job to test the container
    )
    print(f"\n{name}: status={res.status} runtime={res.runtime_s:.1f}s note={stopped[:1]}")
    assert res.status in ("ok", "partial"), (res.status, res.error)
    assert stopped, res.notes
    if static:
        # the container's own copy of the check refuses it (its first problem is named)
        assert "failed the safety check" in stopped[0] and "not allowed" in stopped[0]
    else:
        assert reason in stopped[0], stopped[0]
    if name == "action flood":
        # at most 20 actions in one step, and slow-downs never below 10 % of normal speed
        log = res.extensions.get("event_log", [])
        done = [e for e in log if e.get("type") == "script" and e.get("action") == "slow_down"]
        assert 0 < len(done) <= 20, len(done)
        assert any("already at 10% speed" in n for n in res.notes), res.notes
        assert res.metrics.agents_evacuated > 0


# --- code jobs (the analyst's code and your own scripts): pre-check, then the container -------

CODE_ATTACKS: list[tuple[str, str, str, str]] = [
    # (name, code, pre-check words, container: status and words in its error)
    (
        "network",
        "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=3)\n",
        "'socket'",
        "error:Network is unreachable",
    ),
    (
        "write a file",
        "open('/work/x.txt', 'w').write('x')\n",
        "open()",
        "error:Read-only file system",
    ),
    ("read secrets", "print(open('/proc/self/environ').read())\n", "open()", "ok:no keys"),
    ("endless loop", "while True:\n    pass\n", "", "timeout:"),
    ("huge memory", "x = [0] * (10 ** 9)\n", "", "error:memory"),
    ("fork bomb", "import os\nfor _ in range(2000):\n    os.fork()\n", "'os'", "error:"),
]


@pytest.mark.parametrize(
    ("name", "code", "pre", "box"), CODE_ATTACKS, ids=[a[0] for a in CODE_ATTACKS]
)
def test_the_code_pre_check_refuses_the_escapes(name: str, code: str, pre: str, box: str) -> None:
    from api.core.analysis_check import check_analysis

    problems = check_analysis(code)
    _record("code", name, static=problems[0] if problems else None)
    if pre:
        assert any(pre in p for p in problems), problems
    else:
        assert problems == [], problems


@pytest.fixture
def code_runner(tmp_path: Path) -> DockerRunner:
    reason = docker_unavailable(IMAGE)
    if reason:
        pytest.skip(reason)
    return DockerRunner(tmp_path / "runs", IMAGE, "1g", 1.0)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("name", "code", "pre", "box"), CODE_ATTACKS, ids=[a[0] for a in CODE_ATTACKS]
)
async def test_inside_the_container_a_code_job_attack_fails_safely(
    code_runner: DockerRunner, name: str, code: str, pre: str, box: str
) -> None:
    from api.adapters.sandbox import CodeJob

    status, words = box.split(":", 1)
    job_id = "atk_" + name.replace(" ", "_")
    res = await code_runner.run_code(CodeJob(job_id, "user_script", code, timeout_s=5))
    last = (res.stderr_tail.strip().splitlines() or [""])[-1]
    if name == "read secrets":
        no_keys = "API_KEY" not in res.stdout_tail and "sk-" not in res.stdout_tail
        last = "ran; no API keys in its environment" if no_keys else "KEYS VISIBLE"
    _record("code", name, inside=last, status=res.status, runtime_s=res.runtime_s, injected=True)
    print(f"\n{name}: status={res.status} runtime={res.runtime_s}s err={res.stderr_tail[-160:]!r}")
    assert res.status == status, (res.status, res.stderr_tail)
    if name == "read secrets":
        # the environment a job sees holds no API keys: nothing to steal
        assert "API_KEY" not in res.stdout_tail and "sk-" not in res.stdout_tail
    elif words:
        assert words in res.stderr_tail, res.stderr_tail
    assert res.runtime_s < 30
