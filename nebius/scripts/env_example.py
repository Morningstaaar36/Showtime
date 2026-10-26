"""Keep .env.example in step with the settings and the providers, so it cannot drift.

    python scripts/env_example.py          # list what is missing (exit 1 if anything is)
    python scripts/env_example.py --write  # append the missing settings as commented defaults

Every Settings field, every provider requirement and every preset key must appear in .env.example
(set, or commented out with its default). Never writes a value from .env.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.adapters.providers import registry  # noqa: E402
from api.core.settings import Settings  # noqa: E402

EXAMPLE = ROOT / ".env.example"
HEADER = "# --- Other settings (defaults shown; kept in step by scripts/env_example.py) ---"


def documented(text: str) -> set[str]:
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, re.M))


def required() -> dict[str, str]:
    """Every env name that must be documented, with the default to show."""
    out: dict[str, str] = {}
    for name, field in Settings.model_fields.items():
        out[name.upper()] = _shown(field.get_default(call_default_factory=True))
    for kind in ("llm", "sandbox", "search"):
        for p in registry(kind).all():
            for r in p.requirements:
                out.setdefault(r.env, "")
            for values in p.presets.values():
                for k, v in values.items():
                    out.setdefault(k, v)
    return out


def _shown(default: Any) -> str:
    if isinstance(default, Path):  # a path in this checkout: show it relative to the repo
        try:
            return f"./{default.relative_to(ROOT)}" if default != ROOT else "."
        except ValueError:
            return str(default)
    if isinstance(default, bool):
        return str(default).lower()
    if default is None:
        return ""
    if isinstance(default, dict | list):
        import json

        return json.dumps(default, separators=(",", ":")) if default else ""
    return str(default)


def missing(text: str) -> dict[str, str]:
    have = documented(text)
    return {k: v for k, v in required().items() if k not in have}


def main(argv: list[str]) -> int:
    text = EXAMPLE.read_text()
    gone = missing(text)
    if not gone:
        print(".env.example documents every setting and provider variable.")
        return 0
    if "--write" in argv:
        block = "\n".join(f"# {k}={v}" for k, v in sorted(gone.items()))
        sep = "" if text.endswith("\n") else "\n"
        head = "" if HEADER in text else f"\n{HEADER}\n"
        EXAMPLE.write_text(f"{text}{sep}{head}{block}\n")
        print(f"Added {len(gone)} settings to .env.example.")
        return 0
    print("Missing from .env.example: " + ", ".join(sorted(gone)))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
