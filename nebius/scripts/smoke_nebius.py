"""Smoke test for Nebius Token Factory + Sandboxes. Skips cleanly without NEBIUS_API_KEY.

Usage: make smoke-nebius
"""

from __future__ import annotations

import asyncio
import sys

from api.adapters.llm import LLMClient
from api.adapters.nebius_sandbox import NebiusRunner
from api.core.plugins import load_plugins
from api.core.settings import ROOT_DIR, Settings
from api.core.templates import get_template
from api.orchestrator.runs import RunService


async def main() -> int:
    base = Settings()
    if not base.nebius_api_key:
        print("SKIPPED: NEBIUS_API_KEY is not set (untested: no keys).")
        return 0
    st = base.model_copy(
        update={"llm_provider": "nebius", "sandbox_provider": "nebius", "llm_cache_mode": "off"}
    )
    llm = LLMClient(st)
    print("LLM health:", await llm.health())
    reply = await llm.chat(
        "fast", [{"role": "user", "content": "Reply with the word ready."}], max_tokens=16
    )
    print(
        "LLM reply:",
        reply.text[:80],
        "| tokens",
        reply.usage.prompt_tokens,
        reply.usage.completion_tokens,
        "| cost",
        reply.usage.cost_usd,
    )
    runner = NebiusRunner(st)
    print("Sandbox health:", await runner.health())
    host = load_plugins(ROOT_DIR)
    job = RunService(st, host.registry, runner).build_job(get_template("school_wing"), tier=2)
    res = await runner.run(job)
    print("Sandbox run:", res.status, res.error or "", res.metrics.evac_time_p95_s)
    return 0 if res.status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
