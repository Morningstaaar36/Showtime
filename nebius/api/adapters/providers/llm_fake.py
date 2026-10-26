"""LLM: scripted replies for tests (no model)."""

from __future__ import annotations

from api.adapters.providers import LLM
from api.adapters.providers.base import LlmProvider

LLM.register(
    LlmProvider(
        kind="llm",
        name="fake",
        title="Fake LLM (tests)",
        is_cloud=False,
        label=lambda s: "LOCAL",
        where=lambda s: "fake",
        health="fake",
        is_fake=True,
    )
)
