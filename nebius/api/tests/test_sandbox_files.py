"""Run folders written by a root API are handed to the non-root simulation user."""

from pathlib import Path

import pytest

from api.adapters import sandbox


def test_hand_over_chowns_the_folder_and_its_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "r_1"
    work.mkdir()
    (work / "request.json").write_text("{}")
    calls: list[tuple[str, int, int]] = []
    monkeypatch.setattr(sandbox.os, "chown", lambda p, u, g: calls.append((Path(p).name, u, g)))
    sandbox.hand_over(work, "1000:1000")
    assert sorted(calls) == [("r_1", 1000, 1000), ("request.json", 1000, 1000)]


def test_hand_over_ignores_a_named_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox.os, "chown", lambda *a: pytest.fail("must not chown"))
    sandbox.hand_over(tmp_path, "sim")
