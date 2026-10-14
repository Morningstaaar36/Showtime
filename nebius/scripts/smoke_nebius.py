"""Smoke test for Nebius Token Factory (+ Sandboxes when enabled). Skips cleanly without a key.

Checks every model role the app uses: a plain reply and a JSON reply validated like the agents'
replies, with timing, tokens and cost. The sandbox part runs only with SANDBOX_PROVIDER=nebius
(or --sandbox), since inference and sandboxes are separate access grants.

Usage: make smoke-nebius            (or: python ../scripts/smoke_nebius.py --sandbox)
"""

from __future__ import annotations

import asyncio
import sys
import time

from pydantic import BaseModel

from api.adapters.llm import LLMClient, LLMError, LLMOutputError
from api.core.settings import Settings


class Ready(BaseModel):
    status: str
    exits: int


async def check_llm(st: Settings) -> bool:
    llm = LLMClient(st)
    health = await llm.health()
    print("LLM health:", health)
    if not health.get("ok"):
        return False
    ok = True
    for role in ("fast", "main", "judge"):
        model = st.model_for(role)  # type: ignore[arg-type]
        t0 = time.monotonic()
        try:
            plain = await llm.chat(
                role,  # type: ignore[arg-type]
                [{"role": "user", "content": "Reply with the single word: ready"}],
                max_tokens=32,
            )
            structured = await llm.chat(
                role,  # type: ignore[arg-type]
                [
                    {
                        "role": "user",
                        "content": 'A hall has two doors and one gate. Return {"status": "ready", '
                        '"exits": <number of exits>}.',
                    }
                ],
                Ready,
                max_tokens=128,
            )
        except (LLMError, LLMOutputError) as exc:
            print(f"  {role:<5} {model}: FAILED {exc}")
            ok = False
            continue
        dt = time.monotonic() - t0
        tokens = (
            plain.usage.prompt_tokens
            + plain.usage.completion_tokens
            + structured.usage.prompt_tokens
            + structured.usage.completion_tokens
        )
        cost = plain.usage.cost_usd + structured.usage.cost_usd
        good = structured.parsed is not None and structured.parsed.exits == 3
        ok = ok and good
        print(
            f"  {role:<5} {model}: '{plain.text.strip()[:20]}' | json={structured.parsed} "
            f"{'(repaired)' if structured.repaired else ''}| {dt:.1f} s | {tokens} tokens | "
            f"${cost:.5f}{'' if good else '  <- unexpected JSON answer'}"
        )
    if llm._unsupported:  # what the adapter learned to leave out for these models
        print("Adapted:", sorted(llm._unsupported))
    return ok


async def check_sandbox(st: Settings) -> bool:
    from api.adapters.nebius_sandbox import NebiusRunner
    from api.core.plugins import load_plugins
    from api.core.settings import ROOT_DIR
    from api.core.templates import get_template
    from api.orchestrator.runs import RunService

    runner = NebiusRunner(st)
    print("Sandbox health:", await runner.health())
    host = load_plugins(ROOT_DIR)
    job = RunService(st, host.registry, runner).build_job(get_template("school_wing"), tier=2)
    res = await runner.run(job)
    print("Sandbox run:", res.status, res.error or "", res.metrics.evac_time_p95_s)
    return res.status in ("ok", "partial")


async def main() -> int:
    base = Settings()
    if not base.nebius_api_key:
        print("SKIPPED: NEBIUS_API_KEY is not set (untested: no keys).")
        return 0
    st = base.model_copy(update={"llm_provider": "nebius", "llm_cache_mode": "off"})
    ok = await check_llm(st)
    if "--sandbox" in sys.argv or base.sandbox_provider == "nebius":
        ok = await check_sandbox(st.model_copy(update={"sandbox_provider": "nebius"})) and ok
    else:
        print("Sandbox: skipped (SANDBOX_PROVIDER is not nebius; pass --sandbox to try it).")
    print("NEBIUS SMOKE OK" if ok else "NEBIUS SMOKE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
