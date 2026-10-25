"""LLM: a local llama-server (Nemotron Nano GGUF) on this machine's GPU."""

from __future__ import annotations

from api.adapters.providers import LLM
from api.adapters.providers.base import LlmProvider, Requirement
from api.adapters.providers.checks import llm_check

LLM.register(
    LlmProvider(
        kind="llm",
        name="local",
        title="Local llama-server",
        requirements=(
            Requirement("LOCAL_LLM_BASE_URL", "local_llm_base_url", "the llama-server URL"),
            Requirement("LOCAL_LLM_MODEL", "local_llm_model", "the model name it serves"),
        ),
        presets={
            "local": {
                "LLM_PROVIDER": "local",
                "MODEL_FAST": "",
                "MODEL_LONG": "",
                "MODEL_MAIN": "",
                "MODEL_JUDGE": "",
                "LLM_EXTRA_BODY": "",
            }
        },
        check_live=llm_check,
        is_cloud=False,
        base_url=lambda s: s.local_llm_base_url,
        label=lambda s: "LOCAL",
        where=lambda s: "local llama-server",
        sends_extra_body=False,  # llama-server rejects unknown request fields
        directive_on_every_model=True,  # the local model is Nemotron Nano
        one_request_at_a_time=True,  # one GPU
        health="models",
    )
)
