"""Scenario scripts: the static pre-check and the `script` event (no code is ever run here)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

from api.core.extensions import Registry
from api.core.scripts import EXAMPLE_SCRIPT, MAX_SCRIPT_CHARS, check_script

SIM = Path(__file__).resolve().parents[2] / "sim"

OK_STEP = "def on_step(view, act):\n    act.note('hi')\n"

BAD: dict[str, tuple[str, str]] = {
    "import socket": ("import socket\n" + OK_STEP, "import of 'socket'"),
    "import os.path": ("import os.path\n" + OK_STEP, "import of 'os.path'"),
    "from subprocess": ("from subprocess import run\n" + OK_STEP, "import from 'subprocess'"),
    "dunder attribute": (
        "def on_step(view, act):\n    act.__class__\n",
        "attribute '__class__'",
    ),
    "dunder name": ("__builtins__\n" + OK_STEP, "name '__builtins__'"),
    "open": ("def on_step(view, act):\n    open('/etc/passwd')\n", "'open' is not allowed"),
    "exec": ("def on_step(view, act):\n    exec('1')\n", "'exec' is not allowed"),
    "eval": ("def on_step(view, act):\n    eval('1')\n", "'eval' is not allowed"),
    "getattr": ("def on_step(view, act):\n    getattr(act, 'x')\n", "'getattr'"),
    "private attribute": ("def on_step(view, act):\n    act._ctx\n", "attribute '_ctx'"),
    "frame escape": (
        "g = (x for x in [1])\ndef on_step(view, act):\n    g.gi_frame.f_back\n",
        "attribute 'gi_frame'",
    ),
    "format escape": (
        "def on_step(view, act):\n    '{0.x}'.format(act)\n",
        "attribute 'format'",
    ),
    "try": (
        "def on_step(view, act):\n    try:\n        pass\n    except Exception:\n        pass\n",
        "'try/except'",
    ),
    "no on_step": ("x = 1\n", "must define on_step"),
    "wrong arity": ("def on_step(view):\n    pass\n", "exactly two arguments"),
    "syntax": ("def on_step(view, act)\n    pass\n", "syntax error on line 1"),
}


def _sim_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sim_script_check", SIM / "script_check.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_example_script_passes() -> None:
    assert check_script(EXAMPLE_SCRIPT) == []
    assert check_script(OK_STEP) == []
    ok = "import math\nfrom random import random\n" + OK_STEP
    assert check_script(ok) == []


@pytest.mark.parametrize("name", sorted(BAD))
def test_rejects(name: str) -> None:
    code, expected = BAD[name]
    problems = check_script(code)
    assert problems, name
    assert any(expected in p for p in problems), problems


def test_rejects_oversized_script() -> None:
    code = OK_STEP + "#" * MAX_SCRIPT_CHARS
    assert check_script(code) == [f"The script is longer than {MAX_SCRIPT_CHARS} characters."]


def test_sim_copy_of_the_check_agrees() -> None:
    """sim/script_check.py re-checks inside the sandbox; it must apply the same rules."""
    sim = _sim_check()
    samples = [EXAMPLE_SCRIPT, OK_STEP, *(code for code, _ in BAD.values())]
    for code in samples:
        assert sim.check_script(code) == check_script(code)
    assert sim.ALLOWED_IMPORTS == ("math", "statistics", "random")


def test_script_event_validates_statically(registry: Registry) -> None:
    spec = registry.event("script")
    ev = spec.params_model.model_validate(
        {"type": "script", "title": "Gate jam", "code": EXAMPLE_SCRIPT, "at_s": 0}
    )
    assert ev.model_dump()["every_s"] == 1.0
    with pytest.raises(ValidationError, match="import of 'socket'"):
        spec.params_model.model_validate(
            {"type": "script", "title": "x", "code": BAD["import socket"][0]}
        )
    with pytest.raises(ValidationError):
        spec.params_model.model_validate(
            {"type": "script", "title": "x" * 91, "code": EXAMPLE_SCRIPT}
        )
