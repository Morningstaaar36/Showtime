"""Check each external service with its smallest real call, and record the result.

    make verify-live              # the active LLM, sandbox and search, plus Nebius and Tavily
    make verify-nebius-llm        # Nemotron on Nebius Token Factory (needs NEBIUS_API_KEY)
    make verify-nebius-sandbox    # Nebius Sandboxes (needs NEBIUS_API_KEY and access)
    make verify-tavily            # Tavily web search (needs TAVILY_API_KEY)

Each target is a provider from api/adapters/providers with the settings it needs taken from .env.
A target whose requirements are missing is SKIPPED with what to set. Prints a pass/fail table and
writes docs/LIVE_STATUS.md (date, provider, model ids). Never prints or writes a key. Exits 1 only
when a configured service fails.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.adapters.providers import llm_provider, sandbox_provider, search_provider  # noqa: E402
from api.adapters.providers.base import LiveCheck, Provider  # noqa: E402
from api.core.settings import Settings  # noqa: E402

STATUS_FILE = ROOT / "docs" / "LIVE_STATUS.md"


@dataclass
class Target:
    key: str  # the make target suffix
    kind: str  # llm | sandbox | search
    provider: str
    note: str = ""


NAMED = {
    "nebius-llm": Target("nebius-llm", "llm", "nebius"),
    "nebius-sandbox": Target("nebius-sandbox", "sandbox", "nebius"),
    "tavily": Target("tavily", "search", "tavily"),
}
FIELD = {"llm": "llm_provider", "sandbox": "sandbox_provider", "search": "search_provider"}
LOOKUP = {"llm": llm_provider, "sandbox": sandbox_provider, "search": search_provider}


def targets(which: list[str], base: Settings) -> list[Target]:
    if which and which != ["all"]:
        return [NAMED[w] for w in which]
    active = [
        Target(f"active-{kind}", kind, getattr(base, FIELD[kind]), "in use now")
        for kind in ("llm", "sandbox", "search")
    ]
    seen = {(t.kind, t.provider) for t in active}
    return active + [t for t in NAMED.values() if (t.kind, t.provider) not in seen]


def ids(spec: Provider, kind: str, s: Settings) -> str:
    """Non-secret values worth recording: the provider's non-secret settings, and the model ids
    of an LLM. Keys are never read here."""
    parts = [f"{r.env}={getattr(s, r.setting)}" for r in spec.requirements if not r.secret]
    if kind == "llm":
        roles = ("fast", "main", "judge")
        parts.append("models: " + ", ".join(sorted({s.model_for(r) for r in roles})))  # type: ignore[arg-type]
    return "; ".join(parts)


async def check(t: Target, base: Settings) -> tuple[Target, LiveCheck, str]:
    spec: Provider = LOOKUP[t.kind](t.provider)
    values: dict[str, Any] = {**base.model_dump(), FIELD[t.kind]: t.provider, "offline": False}
    if getattr(base, FIELD[t.kind]) != t.provider and spec.presets:
        # another provider than the one in use: its own model ids and request extras (the
        # active provider's ids are not ones it serves); never keys, presets hold none
        preset = next(iter(spec.presets.values()))
        values |= {k.lower(): v for k, v in preset.items() if k.lower() != FIELD[t.kind]}
    try:
        s = Settings(**values)
    except ValueError as exc:
        return t, LiveCheck("failed", f"settings: {str(exc).splitlines()[-1][:200]}"), ""
    missing = spec.missing(s)
    if missing:
        names = ", ".join(r.env for r in missing)
        return t, LiveCheck("skipped", f"SKIPPED: set {names}", "docs/WHEN_YOU_GET_THE_KEYS.md"), ""
    if spec.check_live is None:
        return t, LiveCheck("skipped", "nothing to check (no live service)"), ""
    try:
        result = await asyncio.wait_for(spec.check_live(s), timeout=300)
    except Exception as exc:  # a check never stops the others
        result = LiveCheck("failed", f"{type(exc).__name__}: {str(exc)[:200]}")
    return t, result, ids(spec, t.kind, s)


def table(rows: list[tuple[Target, LiveCheck, str]]) -> list[str]:
    out = ["| Service | Provider | Result | Detail | Ids |", "| --- | --- | --- | --- | --- |"]
    for t, r, ident in rows:
        title = LOOKUP[t.kind](t.provider).title
        mark = {"ok": "PASS", "failed": "FAIL", "skipped": "SKIPPED"}[r.status]
        detail = r.detail.replace("|", "/") + (
            f" Fix: {r.fix}" if r.fix and r.status != "ok" else ""
        )
        note = f" ({t.note})" if t.note else ""
        out.append(f"| {t.kind}{note} | {title} | {mark} | {detail} | {ident} |")
    return out


def write_status(rows: list[tuple[Target, LiveCheck, str]], argv: list[str]) -> None:
    when = datetime.now(UTC).isoformat(timespec="seconds")
    lines = [
        "# Live status of the external services",
        "",
        f"Written by `scripts/verify_live.py {' '.join(argv) or 'all'}` on {when}. Each row is the",
        "provider's smallest real call (one chat, one sandbox script plus one refused network call,",
        "one search). SKIPPED means its key is not in .env, so it has **not been run live**.",
        "",
        *table(rows),
        "",
    ]
    STATUS_FILE.write_text("\n".join(lines))


async def main(argv: list[str]) -> int:
    base = Settings()
    rows = [await check(t, base) for t in targets(argv, base)]  # one at a time (quota, memory)
    for line in table(rows):
        print(line)
    write_status(rows, argv)
    print(f"\nWrote {STATUS_FILE.relative_to(ROOT)}")
    return 1 if any(r.status == "failed" for _, r, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
