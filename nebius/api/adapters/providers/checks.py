"""The smallest real calls that prove a provider works (used by check_live and make verify-*).
Each returns a LiveCheck: ok, or what failed and how to fix it. Never prints a key."""

from __future__ import annotations

from typing import Any

from api.adapters.providers.base import LiveCheck


async def llm_check(settings: Any) -> LiveCheck:
    """An authenticated health request, then one tiny chat on the fast model."""
    from api.adapters.llm import LLMClient

    client = LLMClient(settings)
    health = await client.health()
    if not health.get("ok"):
        return LiveCheck("failed", str(health.get("detail", "")), "Check the key and base URL.")
    reply = await client.chat(
        "fast", [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=16
    )
    model = settings.model_for("fast")
    text = reply.text.strip()[:40]
    return LiveCheck("ok", f"{health.get('detail', '')}; {model} answered {text!r}")


async def sandbox_check(settings: Any) -> LiveCheck:
    """One tiny code job that must run, and one that must be refused by the sandbox."""
    from api.adapters.sandbox import CodeJob
    from api.app.state import build_runner

    runner = build_runner(settings)
    health = await runner.health()
    if not health.get("ok"):
        return LiveCheck("failed", str(health.get("detail", "")), "See docs/PROVIDERS.md.")
    ok = await runner.run_code(CodeJob("verify_ok", "user_script", "output = {'sum': 1 + 1}\n"))
    if ok.status != "ok" or (ok.output or {}).get("sum") != 2:
        return LiveCheck(
            "failed", f"a tiny script did not run: {ok.status} {ok.stderr_tail[-160:]}"
        )
    bad = await runner.run_code(
        CodeJob(
            "verify_net",
            "user_script",
            "import socket\nsocket.create_connection("
            f"({settings.check_network_host!r}, {settings.check_network_port}), timeout=3)\n",
            timeout_s=10,
        )
    )
    if bad.status == "ok":
        return LiveCheck("failed", "a script reached the network from inside the sandbox")
    last = (bad.stderr_tail.strip().splitlines() or [bad.status])[-1][:120]
    return LiveCheck("ok", f"ran a script in {ok.runtime_s} s; a network call was stopped: {last}")


async def search_check(settings: Any) -> LiveCheck:
    """One real search that must come back with a cited result."""
    from api.adapters.providers import search_provider

    client = search_provider(settings.search_provider).build(settings)
    if not getattr(client, "live", False):
        return LiveCheck("skipped", "Web search is off.", "Set TAVILY_API_KEY in .env.")
    hits = await client.search(settings.check_search_query, max_results=2)
    if not hits:
        return LiveCheck(
            "failed", "the search returned nothing", "Check TAVILY_API_KEY and the quota."
        )
    return LiveCheck("ok", f"{len(hits)} results, first: {hits[0].title[:60]} ({hits[0].url})")
