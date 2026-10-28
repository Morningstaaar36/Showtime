"""LLM: any OpenAI-compatible service (OpenRouter's free Nemotron models as its preset)."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import LLM
from api.adapters.providers.base import LlmProvider, Requirement, preset
from api.adapters.providers.checks import llm_check


def _label(s: Any) -> str:
    return str(s.openai_compat_label).upper() or "CLOUD"


LLM.register(
    LlmProvider(
        kind="llm",
        name="openai",
        aliases=("openai_compat",),
        title="OpenAI-compatible API",
        requirements=(
            Requirement("OPENAI_COMPAT_BASE_URL", "openai_compat_base_url", "the API's base URL"),
            Requirement("OPENAI_COMPAT_API_KEY", "openai_compat_api_key", "your API key", True),
        ),
        presets={"openrouter": preset("openrouter")},
        check_live=llm_check,
        missing_text=lambda gone: "OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_API_KEY must be set.",
        is_cloud=True,
        base_url=lambda s: s.openai_compat_base_url,
        key=lambda s: s.openai_compat_api_key,
        key_env="OPENAI_COMPAT_API_KEY",
        spare_key=lambda s: s.openai_compat_api_key_fallback,
        label=_label,
        where=lambda s: f"{_label(s)} API ({s.openai_compat_base_url})",
    )
)
