"""Code jobs: result parsing, the fake runner, run_code.py semantics, checkpoints, pre-check.

No Docker here (see test_code_jobs_docker.py): run_code.py needs only the standard library,
so it runs as a plain subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from api.adapters.sandbox import (
    TIMEOUT_EXIT,
    CodeJob,
    CodeResult,
    DockerRunner,
    FakeRunner,
    code_files,
    copy_checkpoint,
    parse_code_output,
)
from api.core.analysis_check import check_analysis
from api.core.extensions import Registry
from api.core.settings import Settings
from api.core.templates import get_template
from api.orchestrator.runs import RunService

RUN_CODE = Path(__file__).resolve().parents[2] / "sim" / "run_code.py"


def _job(**kw: object) -> CodeJob:
    base: dict[str, object] = {"job_id": "j1", "kind": "analysis", "script": "output = 1"}
    return CodeJob(**{**base, **kw})  # type: ignore[arg-type]


# --- parsing ---------------------------------------------------------------------------------


def test_parse_ok_takes_the_last_line_as_json() -> None:
    res = parse_code_output(0, 'working\n{"a": 1}\n', "", 1.234)
    assert res == CodeResult("ok", {"a": 1}, "working", "", 1.23)


def test_parse_error_and_timeout_statuses() -> None:
    err = parse_code_output(1, "", "ZeroDivisionError: division by zero", 0.5)
    assert err.status == "error" and err.output is None and "ZeroDivision" in err.stderr_tail
    oom = parse_code_output(137, "", "", 0.5)
    assert oom.status == "error" and "out of memory" in oom.stderr_tail
    late = parse_code_output(TIMEOUT_EXIT, "", "", 3.0)
    assert late.status == "timeout" and "ran out of time" in late.stderr_tail
    killed = parse_code_output(None, "partial", "", 45.0, timed_out=True)
    assert killed.status == "timeout" and killed.stdout_tail == "partial"


def test_parse_keeps_only_the_tails() -> None:
    res = parse_code_output(0, "x" * 10_000 + "\nnull\n", "e" * 10_000, 1)
    assert len(res.stdout_tail) <= 2000 and len(res.stderr_tail) <= 2000


def test_code_files_refuse_paths_that_leave_the_job_folder() -> None:
    assert code_files(_job(inputs={"traj.bin": b"x"})) == {
        "j1/traj.bin": b"x",
        "j1/script.py": b"output = 1",
    }
    for bad in (_job(job_id="../x"), _job(inputs={"../a": b""}), _job(inputs={"script.py": b""})):
        with pytest.raises(ValueError):
            code_files(bad)


# --- fake runner -----------------------------------------------------------------------------


async def test_fake_runner_executes_nothing_and_returns_scripted_results(tmp_path: Path) -> None:
    scripted = [
        CodeResult("timeout", stderr_tail="stopped"),
        lambda job: CodeResult("ok", {"job": job.job_id}),
    ]
    fake = FakeRunner(tmp_path, code_results=scripted)
    assert (await fake.run_code(_job())).status == "timeout"
    assert (await fake.run_code(_job(job_id="j2"))).output == {"job": "j2"}
    assert (await fake.run_code(_job(job_id="j3"))) == CodeResult("ok", None)
    assert [j.job_id for j in fake.code_jobs] == ["j1", "j2", "j3"]
    assert (await fake.run_code(_job(job_id="a/b"))).status == "error"


# --- run_code.py (the sandbox entry point) ---------------------------------------------------


def _run_code(tmp_path: Path, script: str, timeout_s: float = 5) -> CodeResult:
    work = tmp_path / "job"
    work.mkdir(exist_ok=True)
    (work / "script.py").write_text(script)
    proc = subprocess.run(
        [sys.executable, str(RUN_CODE), str(work)],
        capture_output=True,
        text=True,
        timeout=30,
        env={"SHOWTIME_TIMEOUT_S": str(timeout_s), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    return parse_code_output(proc.returncode, proc.stdout, proc.stderr, 0)


@pytest.mark.parametrize(
    ("script", "want"),
    [
        ("def main():\n    return {'n': 3}\n", {"n": 3}),
        (
            "output = {'mean': float('nan'), 'xs': (1, 2)}\nprint('note')\n",
            {"mean": None, "xs": [1, 2]},
        ),
        ("import json\nprint('a')\nprint(json.dumps([1, 2]))\n", [1, 2]),
        ("print('no json here')\n", None),
    ],
)
def test_run_code_result_conventions(tmp_path: Path, script: str, want: object) -> None:
    res = _run_code(tmp_path, script)
    assert res.status == "ok" and res.output == want


def test_run_code_reports_the_scripts_own_error(tmp_path: Path) -> None:
    res = _run_code(tmp_path, "x = 1\ny = x / 0\n")
    assert res.status == "error"
    assert 'File "script.py", line 2' in res.stderr_tail and "ZeroDivisionError" in res.stderr_tail
    assert "run_code.py" not in res.stderr_tail


def test_run_code_stops_an_endless_loop(tmp_path: Path) -> None:
    script = "while True:\n    try:\n        pass\n    except Exception:\n        pass\n"
    res = _run_code(tmp_path, script, timeout_s=0.5)
    assert res.status == "timeout" and "0.5 s" in res.stderr_tail


def test_run_code_refuses_huge_results(tmp_path: Path) -> None:
    res = _run_code(tmp_path, "output = 'x' * 300000\n")
    assert res.status == "error" and "too large" in res.stderr_tail


# --- checkpoints for resume_from (Docker) ----------------------------------------------------


def test_copy_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "r_a").mkdir()
    (tmp_path / "r_a" / "checkpoint.json").write_text(json.dumps({"t": 30}))
    (tmp_path / "r_b").mkdir()
    assert copy_checkpoint(tmp_path, "r_a", tmp_path / "r_b") is None
    assert json.loads((tmp_path / "r_b" / "checkpoint.json").read_text()) == {"t": 30}
    assert "no saved moment" in (copy_checkpoint(tmp_path, "r_x", tmp_path / "r_b") or "")
    assert "not a run id" in (copy_checkpoint(tmp_path, "../r_a", tmp_path / "r_b") or "")


async def test_docker_resume_without_a_checkpoint_fails_before_starting(
    registry: Registry, tmp_path: Path
) -> None:
    st = Settings(_env_file=None, runs_dir=tmp_path / "runs", cache_dir=tmp_path / "cache")
    runner = DockerRunner(st.runs_dir, "showtime-sim:none", "1g", 1.0)
    runner._docker = "/nonexistent/docker"  # must not be reached
    job = RunService(st, registry, runner).build_job(get_template("school_wing"), tier=2)
    job.resume_from = "r_missing"
    res = await runner.run(job)
    assert res.status == "failed" and "no saved moment" in (res.error or "")


# --- the analysis pre-check ------------------------------------------------------------------

GOOD = """
import math, statistics, json
import numpy as np
import pandas as pd
import showtime_data as sd
from showtime_data import people_near

traj = sd.load_trajectories(every_s=1.0)
q = people_near("E1", radius_m=3.0)
output = {"facts": {"peak_queue": int(q["people"].max())}, "mean": statistics.mean([1, 2])}
"""


def test_check_analysis_accepts_a_plain_pandas_script() -> None:
    assert check_analysis(GOOD) == []


@pytest.mark.parametrize(
    ("code", "word"),
    [
        ("import os\n", "importing 'os'"),
        ("import socket\nsocket.create_connection(('x', 1))\n", "importing 'socket'"),
        ("from subprocess import run\n", "importing from 'subprocess'"),
        ("from . import x\n", "importing from"),
        ("x = ().__class__.__bases__\n", "double underscores"),
        ("open('/etc/passwd')\n", "open()"),
        ("eval('1')\n", "eval()"),
        ("f = getattr(object, 'x')\n", "getattr()"),
        ("import pandas as pd\npd.read_csv('/etc/passwd')\n", "reads or writes files"),
        ("import numpy as np\nnp.save('x', 1)\n", "reads or writes files"),
        ("def f():\n    global x\n", "global"),
        ("x = (\n", "Syntax error"),
        ("", "empty"),
        ("x = 1\n" * 2000, "limit is 8192"),
    ],
)
def test_check_analysis_rejects(code: str, word: str) -> None:
    problems = check_analysis(code)
    assert problems and any(word in p for p in problems), problems
