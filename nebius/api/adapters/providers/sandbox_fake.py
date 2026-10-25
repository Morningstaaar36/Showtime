"""Sandbox: no simulation, scaled instant estimates labelled as such (tests, previews)."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import SANDBOX
from api.adapters.providers.base import SandboxProvider


def _build(s: Any) -> Any:
    from api.adapters.sandbox import FakeRunner

    return FakeRunner(s.runs_dir, max_parallel=s.sandbox_max_parallel)


SANDBOX.register(
    SandboxProvider(kind="sandbox", name="fake", title="No sandbox (preview)", build=_build)
)
