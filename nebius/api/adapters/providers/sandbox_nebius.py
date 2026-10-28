"""Sandbox: Nebius Sandboxes (contree-sdk), snapshot branches. Live status: docs/LIVE_STATUS.md.

Needs the Token Factory key and the project ID (docs: Sandboxes › Set up access)."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import SANDBOX
from api.adapters.providers.base import Requirement, SandboxProvider
from api.adapters.providers.checks import sandbox_check


def _build(s: Any) -> Any:
    from api.adapters.nebius_sandbox import NebiusRunner

    return NebiusRunner(s)


SANDBOX.register(
    SandboxProvider(
        kind="sandbox",
        name="nebius",
        title="Nebius Sandboxes",
        requirements=(
            Requirement("NEBIUS_API_KEY", "nebius_api_key", "your Nebius API key", True),
            Requirement(
                "NEBIUS_PROJECT_ID",
                "nebius_project_id",
                "the Token Factory project ID (Project settings, under the project name)",
            ),
            Requirement("NEBIUS_SANDBOX_BASE_URL", "nebius_sandbox_base_url", "the Sandboxes URL"),
        ),
        check_live=sandbox_check,
        build=_build,
    )
)
