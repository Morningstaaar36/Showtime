"""sim/memory_cap.py: reads the container's memory limit and caps heap growth to what is left."""

from __future__ import annotations

import importlib.util
import resource
from pathlib import Path
from types import ModuleType

import pytest

from api.core.settings import ROOT_DIR


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("memory_cap", ROOT_DIR / "sim" / "memory_cap.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reads_cgroup_v2_and_v1_limits_and_no_limit(tmp_path: Path) -> None:
    mc = _module()
    v2 = tmp_path / "memory.max"
    v2.write_text("1073741824\n")
    assert mc.container_limit((str(v2),)) == 1073741824
    v2.write_text("max\n")
    v1 = tmp_path / "limit_in_bytes"
    v1.write_text("9223372036854771712\n")  # cgroup v1's "no limit"
    assert mc.container_limit((str(v2), str(v1))) is None
    assert mc.container_limit((str(tmp_path / "missing"),)) is None


def test_without_a_container_limit_nothing_is_capped(tmp_path: Path) -> None:
    mc = _module()
    before = resource.getrlimit(resource.RLIMIT_DATA)
    assert mc.cap_memory(0.85, (str(tmp_path / "missing"),)) is None
    assert resource.getrlimit(resource.RLIMIT_DATA) == before


def test_the_cap_is_current_data_plus_most_of_the_room_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mc = _module()
    limit = tmp_path / "memory.max"
    limit.write_text(str(2 * 1024**3))
    status = {"VmData": 500_000, "VmRSS": 100_000}  # kB
    monkeypatch.setattr(mc, "_status_kb", lambda field, status_file=None: status[field])
    set_to: list[tuple[int, int]] = []
    monkeypatch.setattr(mc.resource, "setrlimit", lambda kind, value: set_to.append(value))
    cap = mc.cap_memory(0.85, (str(limit),))
    room = 2 * 1024**3 - 100_000 * 1024
    assert cap == 500_000 * 1024 + int(room * 0.85)
    assert set_to and set_to[0][0] == cap
