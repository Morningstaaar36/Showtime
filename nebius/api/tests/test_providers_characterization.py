"""Characterization of the three external services as they behave today (step 6a). These pin the
behaviour before the provider registries replace the if/else chains, and must pass unchanged
after: base URL, which key is used, extra request fields, the Nemotron directive, models,
prices, labels, health without a key, sandbox selection and search on/off."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from api.adapters.llm import LLMClient
from api.adapters.nebius_sandbox import NebiusRunner
from api.adapters.sandbox import DockerRunner, FakeRunner
from api.adapters.search import TavilySearch
from api.app.state import build_runner
from api.core.settings import Settings

COMMON: dict[str, Any] = {
    "local_llm_base_url": "http://127.0.0.1:8080/v1",
    "local_llm_model": "nemotron-nano-9b-v2-q4_k_m",
    "nebius_base_url": "https://api.tokenfactory.nebius.com/v1",
    "openai_compat_base_url": "https://openrouter.ai/api/v1",
    "openai_compat_label": "OpenRouter",
    "model_fast": "nvidia/fast",
    "model_main": "nvidia/main",
    "model_long": "",
    "model_judge": "",
    "price_fast_in": 0.5,
    "price_fast_out": 1.5,
    "price_main_in": 2.0,
    "price_main_out": 4.0,
    "llm_extra_body": '{"reasoning": {"enabled": false}}',
    "llm_cache_mode": "off",
}


def _s(tmp_path: Path, provider: str, **kw: Any) -> Settings:
    return Settings(_env_file=None, llm_provider=provider, cache_dir=tmp_path, **(COMMON | kw))


# --- LLM ---------------------------------------------------------------------------------------


def test_local(tmp_path: Path) -> None:
    s = _s(tmp_path, "local")
    c = LLMClient(s)
    assert (c.base_url, c.api_key, c.extra_body) == ("http://127.0.0.1:8080/v1", "local", {})
    assert not s.cloud_llm and s.llm_label == "LOCAL"
    assert s.model_for("main") == "nemotron-nano-9b-v2-q4_k_m" and s.price_for("main") == (0, 0)
    assert c._directive(False, "anything") == "/no_think"  # always, on the local model
    assert c.where == "local llama-server" and c.lock is not None


def test_nebius(tmp_path: Path) -> None:
    s = _s(tmp_path, "nebius", nebius_api_key="nb-key")
    c = LLMClient(s)
    assert c.base_url == "https://api.tokenfactory.nebius.com/v1" and c.api_key == "nb-key"
    assert c.extra_body == {"reasoning": {"enabled": False}}
    assert s.cloud_llm and s.llm_label == "NEBIUS"
    assert s.model_for("judge") == "nvidia/main" and s.model_for("long") == "nvidia/fast"
    assert s.price_for("main") == (2.0, 4.0)
    assert c._directive(True, "nvidia/nemotron-x") == "/think" and c._directive(True, "llama") == ""
    assert c.where == "Nebius Token Factory" and c.lock is None


async def test_nebius_without_a_key_says_so(tmp_path: Path) -> None:
    h = await LLMClient(_s(tmp_path, "nebius", nebius_api_key="")).health()
    assert h == {"ok": False, "detail": "NEBIUS_API_KEY is not set."}


def test_openai_compatible(tmp_path: Path) -> None:
    s = _s(tmp_path, "openai", openai_compat_api_key="or-key", openai_compat_api_key_fallback="sp")
    c = LLMClient(s)
    assert c.base_url == "https://openrouter.ai/api/v1" and c.api_key == "or-key"
    assert c.extra_body == {"reasoning": {"enabled": False}}
    assert s.cloud_llm and s.llm_label == "OPENROUTER"
    assert s.price_for("fast") == (0.5, 1.5)
    assert c.where == "OPENROUTER API (https://openrouter.ai/api/v1)"
    assert c._switch_to_spare_key("429 quota") and c.api_key == "sp"


async def test_openai_compatible_without_a_key_says_so(tmp_path: Path) -> None:
    h = await LLMClient(_s(tmp_path, "openai", openai_compat_api_key="")).health()
    assert h == {
        "ok": False,
        "detail": "OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_API_KEY must be set.",
    }


async def test_fake(tmp_path: Path) -> None:
    s = _s(tmp_path, "fake")
    assert await LLMClient(s).health() == {"ok": True, "detail": "Fake LLM (tests)"}
    assert not s.cloud_llm and s.llm_label == "LOCAL"


# --- sandbox -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"), [("docker", DockerRunner), ("nebius", NebiusRunner), ("fake", FakeRunner)]
)
def test_sandbox_selection(tmp_path: Path, name: str, kind: type) -> None:
    s = Settings(_env_file=None, sandbox_provider=name, runs_dir=tmp_path, cache_dir=tmp_path)
    runner = build_runner(s)
    assert isinstance(runner, kind) and runner.provider == name


# --- search ------------------------------------------------------------------------------------


async def test_search_is_off_without_a_key_and_live_with_one(tmp_path: Path) -> None:
    off = TavilySearch("", tmp_path)
    assert not off.live
    assert await off.health() == {
        "ok": True,
        "live": False,
        "detail": "Live search is off (no TAVILY_API_KEY).",
    }
    assert TavilySearch("tv-key", tmp_path).live
    assert not TavilySearch("tv-key", tmp_path, offline=True).live
