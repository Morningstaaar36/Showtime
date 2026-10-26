"""The disk cache is an optimisation: a folder it cannot write must never fail the lookup."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from api.adapters.cache import DiskCache


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write a read-only folder")
def test_an_unwritable_cache_logs_and_carries_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    c = DiskCache(tmp_path)
    (tmp_path / "ab").mkdir()
    (tmp_path / "ab").chmod(0o500)  # like a folder another user (root in a container) created
    try:
        with caplog.at_level(logging.WARNING, logger="showtime.cache"):
            c.put("ab" + "0" * 62, {"x": 1})
            c.put("ab" + "1" * 62, {"x": 2})
        assert c.get("ab" + "0" * 62) is None
        warned = [r for r in caplog.records if "cannot write" in r.getMessage()]
        assert len(warned) == 1, "warned once, not on every write"
    finally:
        (tmp_path / "ab").chmod(0o700)


def test_a_writable_cache_round_trips(tmp_path: Path) -> None:
    c = DiskCache(tmp_path)
    c.put("cd" + "0" * 62, {"x": 1})
    assert c.get("cd" + "0" * 62) == {"x": 1}
