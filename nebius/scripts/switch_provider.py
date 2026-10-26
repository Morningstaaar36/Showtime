"""Switch the model provider in .env to one of the presets the providers declare
(api/adapters/providers: nebius, openrouter, local today; a new provider's presets appear here).

Rewrites only the provider lines (provider, model ids, prices, request extras) and keeps every
key and other setting. The previous file is saved as .env.bak first.

Usage: make use-<preset>   (make use-list shows them)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
sys.path.insert(0, str(ROOT))

from api.adapters.providers import registry  # noqa: E402  (stdlib-only descriptions)


def presets() -> dict[str, tuple[str, dict[str, str]]]:
    """Every preset any LLM provider offers: name -> (provider title, .env values)."""
    out: dict[str, tuple[str, dict[str, str]]] = {}
    for p in registry("llm").all():
        for name, values in p.presets.items():
            out[name] = (p.title, values)
    return out


def keys_needed(preset: str) -> list[str]:
    """The secret settings the preset's provider needs (e.g. NEBIUS_API_KEY)."""
    for p in registry("llm").all():
        if preset in p.presets:
            return [r.env for r in p.requirements if r.secret]
    return []


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
    known = presets()
    if name in ("", "list"):
        for key, (title, _) in sorted(known.items()):
            print(f"make use-{key:12} {title}")
        return 0 if name == "list" else 2
    if name not in known:
        print(f"Unknown preset '{name}'. Presets: {', '.join(sorted(known))}")
        return 2
    if not ENV.exists():
        print(".env is missing: run make setup (or cp .env.example .env) first.")
        return 1
    lines = ENV.read_text().splitlines()
    shutil.copyfile(ENV, ENV.with_name(".env.bak"))
    ENV.write_text("\n".join(switch(lines, known[name][1])) + "\n")
    print(f"Provider set to {name} (previous .env saved as .env.bak).")
    for key in keys_needed(name):
        if not value(lines, key):
            print(f"Now add your key: {key}=... in .env")
    print("Restart the app to use it: make up (Docker) or make dev-down && make dev.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
