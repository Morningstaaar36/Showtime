"""Switch the model provider in .env: nebius, openrouter or local.

Rewrites only the provider lines (provider, model ids, prices, request extras) and keeps every
key and other setting. The previous file is saved as .env.bak first.

Usage: make use-nebius | make use-openrouter | make use-local
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"

# Model ids and prices from https://tokenfactory.nebius.com/model-catalog.md (checked 2026-10-14).
# Nemotron 3 reasons by default; the chat template switch turns it off for JSON replies.
PRESETS: dict[str, dict[str, str]] = {
    "nebius": {
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
        # JSON asked for in the prompt and validated: the setup proven live on OpenRouter
        "LLM_SUPPORTS_JSON_SCHEMA": "false",
    },
    "openrouter": {
        "LLM_PROVIDER": "openai",
        "OPENAI_COMPAT_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENAI_COMPAT_LABEL": "OpenRouter",
        "MODEL_FAST": "nvidia/nemotron-3-super-120b-a12b:free",
        "MODEL_LONG": "",
        "MODEL_MAIN": "nvidia/nemotron-3-super-120b-a12b:free",
        "MODEL_JUDGE": "nvidia/nemotron-3-super-120b-a12b:free",
        "LLM_EXTRA_BODY": '{"reasoning":{"enabled":false}}',
        "LLM_SUPPORTS_JSON_SCHEMA": "false",
    },
    "local": {
        "LLM_PROVIDER": "local",
        "MODEL_FAST": "",
        "MODEL_LONG": "",
        "MODEL_MAIN": "",
        "MODEL_JUDGE": "",
        "LLM_EXTRA_BODY": "",
    },
}

KEYS_NEEDED = {
    "nebius": "NEBIUS_API_KEY",
    "openrouter": "OPENAI_COMPAT_API_KEY",
}


def switch(lines: list[str], preset: dict[str, str]) -> list[str]:
    """The .env lines with the preset's keys set; missing keys are appended."""
    done: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = (
            line.split("=", 1)[0].strip()
            if "=" in line and not line.lstrip().startswith("#")
            else ""
        )
        if key in preset:
            if key not in done:  # a key set twice keeps one line
                out.append(f"{key}={preset[key]}")
                done.add(key)
            continue
        out.append(line)
    missing = [k for k in preset if k not in done]
    if missing:
        out.append("# --- set by make use-<provider> ---")
        out += [f"{k}={preset[k]}" for k in missing]
    return out


def value(lines: list[str], key: str) -> str:
    for line in lines:
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].split(" #", 1)[0].strip()
    return ""


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in PRESETS:
        print(f"usage: switch_provider.py {'|'.join(PRESETS)}")
        return 2
    if not ENV.exists():
        print(".env is missing: run make setup (or cp .env.example .env) first.")
        return 1
    lines = ENV.read_text().splitlines()
    shutil.copyfile(ENV, ENV.with_name(".env.bak"))
    ENV.write_text("\n".join(switch(lines, PRESETS[name])) + "\n")
    print(f"Provider set to {name} (previous .env saved as .env.bak).")
    key = KEYS_NEEDED.get(name)
    if key and not value(lines, key):
        print(f"Now add your key: {key}=... in .env")
    print("Restart the app to use it: make up (Docker) or make dev-down && make dev.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
