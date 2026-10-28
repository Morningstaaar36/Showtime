"""LLM: Nemotron on Nebius Token Factory (OpenAI-compatible); presets in api/data/."""

from __future__ import annotations

from api.adapters.providers import LLM
from api.adapters.providers.base import LlmProvider, Requirement, preset
from api.adapters.providers.checks import llm_check

LLM.register(
    LlmProvider(
        kind="llm",
        name="nebius",
        title="Nebius Token Factory",
        requirements=(
            Requirement("NEBIUS_API_KEY", "nebius_api_key", "your Token Factory API key", True),
        ),
        presets={"nebius": preset("nebius")},
        check_live=llm_check,
        missing_text=lambda gone: "NEBIUS_API_KEY is not set.",
        is_cloud=True,
        base_url=lambda s: s.nebius_base_url,
        key=lambda s: s.nebius_api_key,
        key_env="NEBIUS_API_KEY",
        label=lambda s: "NEBIUS",
        where=lambda s: "Nebius Token Factory",
    )
)
