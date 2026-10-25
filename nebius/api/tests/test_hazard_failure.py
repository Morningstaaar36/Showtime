"""A hazard source that fails is left out of the countdown, and says so (log + session event)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from api.core.templates import get_template
from api.orchestrator.session import LiveSession
from api.tests.test_redteam import state  # noqa: F401


class _Broken:
    id = "hazard_broken"
    modes = ("indoor", "outdoor")

    async def evaluate(self, ctx: Any) -> Any:
        raise RuntimeError("forecast service down")


async def test_a_failing_hazard_source_is_reported_not_swallowed(
    state: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = [_Broken(), *state.registry.all("HazardSource")]
    real_all = state.registry.all
    monkeypatch.setattr(
        state.registry, "all", lambda kind: sources if kind == "HazardSource" else real_all(kind)
    )
    live = LiveSession(id="s_test", project_id="p_test", venue_version=1, config={})
    with caplog.at_level(logging.WARNING, logger="showtime.session"):
        await state.sessions._countdown(live, get_template("school_wing"), None, None)
    assert any("hazard source hazard_broken failed" in r.getMessage() for r in caplog.records)
    logs = [e.payload["message"] for e in live.events if e.type == "log"]
    assert any("hazard_broken" in m and "leaves it out" in m for m in logs)
