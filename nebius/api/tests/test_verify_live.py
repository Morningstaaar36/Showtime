"""make verify-live: a service without its key is SKIPPED with what to set, and never called;
the status file never holds a key."""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from api.core.settings import ROOT_DIR, Settings


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_live", ROOT_DIR / "scripts" / "verify_live.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_live"] = mod  # its dataclasses look themselves up there
    spec.loader.exec_module(mod)
    return mod


async def test_missing_keys_are_skipped_without_a_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vl = _script()
    monkeypatch.setattr(vl, "STATUS_FILE", tmp_path / "LIVE_STATUS.md")
    monkeypatch.setattr(vl, "RESULTS_FILE", tmp_path / "live_status.json")
    base = Settings(_env_file=None, nebius_api_key="", tavily_api_key="", cache_dir=tmp_path)
    rows = [await vl.check(vl.NAMED[k], base) for k in ("nebius-llm", "nebius-sandbox", "tavily")]
    assert [r.status for _, r, _ in rows] == ["skipped"] * 3
    assert rows[0][1].detail == "SKIPPED: set NEBIUS_API_KEY"
    assert rows[2][1].detail == "SKIPPED: set TAVILY_API_KEY"
    vl.write_status(rows, ["nebius-llm"])
    text = (tmp_path / "LIVE_STATUS.md").read_text()
    assert "not been run live" in text and "SKIPPED" in text


async def test_the_status_file_never_holds_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vl = _script()
    monkeypatch.setattr(vl, "STATUS_FILE", tmp_path / "LIVE_STATUS.md")
    monkeypatch.setattr(vl, "RESULTS_FILE", tmp_path / "live_status.json")
    secret = "sk-or-v1-0123456789abcdef"
    base = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_compat_base_url="https://example.test/v1",
        openai_compat_api_key=secret,
        model_fast="m",
        cache_dir=tmp_path,
    )

    async def fake_check(settings: Settings) -> object:
        return vl.LiveCheck("ok", "answered")

    real = vl.LOOKUP["llm"]
    monkeypatch.setitem(
        vl.LOOKUP, "llm", lambda name: dataclasses.replace(real(name), check_live=fake_check)
    )
    row = await vl.check(vl.Target("active-llm", "llm", "openai"), base)
    vl.write_status([row], [])
    assert secret not in (tmp_path / "LIVE_STATUS.md").read_text()


async def test_one_service_updates_its_own_row_and_keeps_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vl = _script()
    monkeypatch.setattr(vl, "STATUS_FILE", tmp_path / "LIVE_STATUS.md")
    monkeypatch.setattr(vl, "RESULTS_FILE", tmp_path / "live_status.json")
    ok = vl.LiveCheck("ok", "answered")
    vl.write_status([(vl.Target("active-llm", "llm", "openai"), ok, "")], [])
    skip = vl.LiveCheck("skipped", "SKIPPED: set TAVILY_API_KEY")
    merged = vl.write_status([(vl.NAMED["tavily"], skip, "")], ["tavily"])
    assert {(r["provider"], r["status"]) for r in merged} == {
        ("openai", "ok"),
        ("tavily", "skipped"),
    }
