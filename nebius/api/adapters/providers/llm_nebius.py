"""LLM: Nemotron on Nebius Token Factory (OpenAI-compatible). Not run live yet (no key)."""

from __future__ import annotations

from api.adapters.providers import LLM
from api.adapters.providers.base import LlmProvider, Requirement
from api.adapters.providers.checks import llm_check

# Model ids and prices from https://tokenfactory.nebius.com/model-catalog.md (checked 2026-10-14).
# Nemotron 3 reasons by default; the chat template switch turns it off for JSON replies.
NEBIUS_PRESET = {
    "LLM_PROVIDER": "nebius",
    "MODEL_FAST": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "MODEL_LONG": "nvidia/Nemotron-3_5-Lightning",
    "MODEL_MAIN": "nvidia/nemotron-3-super-120b-a12b",
    "MODEL_JUDGE": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "PRICE_FAST_IN": "0.06",
    "PRICE_FAST_OUT": "0.24",
    "PRICE_LONG_IN": "0.06",
    "PRICE_LONG_OUT": "0.24",
    "PRICE_MAIN_IN": "0.30",
    "PRICE_MAIN_OUT": "0.90",
    "PRICE_JUDGE_IN": "1.00",
    "PRICE_JUDGE_OUT": "3.00",
    "LLM_EXTRA_BODY": '{"chat_template_kwargs":{"enable_thinking":false}}',
    "LLM_SUPPORTS_JSON_SCHEMA": "false",
}

LLM.register(
    LlmProvider(
        kind="llm",
        name="nebius",
        title="Nebius Token Factory",
        requirements=(
            Requirement("NEBIUS_API_KEY", "nebius_api_key", "your Token Factory API key", True),
        ),
        presets={"nebius": NEBIUS_PRESET},
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
