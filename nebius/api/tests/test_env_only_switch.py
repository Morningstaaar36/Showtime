"""Switching the LLM provider needs only .env (step: "only replacing env is enough").

A provider's preset (api/data/llm_presets.json) fills model ids, prices and request extras that
are empty or still hold another provider's preset values; ids you chose yourself are kept.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from api.adapters.providers import LLM, llm_provider
from api.core.settings import Settings

OPENROUTER = llm_provider("openai").presets["openrouter"]
ACME = {
    "LLM_PROVIDER": "acme",
    "MODEL_FAST": "nvidia/acme-fast",
    "MODEL_MAIN": "nvidia/acme-main",
    "MODEL_JUDGE": "nvidia/acme-judge",
    "LLM_EXTRA_BODY": '{"reasoning_effort":"none"}',
}


def _s(tmp_path: Path, **kw: Any) -> Settings:
    return Settings(_env_file=None, cache_dir=tmp_path, runs_dir=tmp_path / "runs", **kw)


@pytest.fixture
def acme() -> Iterator[None]:
    """A second hosted provider with its own preset (registered for this test only)."""
    base = llm_provider("openai")
    LLM.register(replace(base, name="acme", aliases=(), title="Acme", presets={"acme": ACME}))
    try:
        yield
    finally:
        LLM.unregister("acme")


def _openrouter(**kw: Any) -> dict[str, Any]:
    return {"openai_compat_base_url": OPENROUTER["OPENAI_COMPAT_BASE_URL"], **kw}


def test_leftover_values_give_way_to_the_new_providers_preset(tmp_path: Path, acme: None) -> None:
    # the .env of someone who ran `make use-openrouter`, then set LLM_PROVIDER=acme and a key
    left = {k.lower(): v for k, v in OPENROUTER.items() if k != "LLM_PROVIDER"}
    s = _s(tmp_path, **left, llm_provider="acme", openai_compat_api_key="k")
    assert s.model_for("fast") == ACME["MODEL_FAST"]
    assert s.model_for("judge") == ACME["MODEL_JUDGE"]
    assert s.llm_extra_body == ACME["LLM_EXTRA_BODY"]
    assert s.model_fallback == ""  # OpenRouter's fallback id is not one Acme serves


def test_empty_model_ids_take_the_provider_preset(tmp_path: Path) -> None:
    s = _s(
        tmp_path,
        **_openrouter(),
        llm_provider="openai",
        openai_compat_api_key="k",
        model_fast="",
        model_main="",
    )
    assert s.model_for("fast") == OPENROUTER["MODEL_FAST"]
    assert s.model_for("main") == OPENROUTER["MODEL_MAIN"]


def test_a_model_id_you_chose_is_kept(tmp_path: Path) -> None:
    s = _s(
        tmp_path,
        **_openrouter(),
        llm_provider="openai",
        openai_compat_api_key="k",
        model_fast="nvidia/my-own-choice",
    )
    assert s.model_for("fast") == "nvidia/my-own-choice"


def test_the_openrouter_preset_stays_on_openrouter(tmp_path: Path) -> None:
    # another OpenAI-compatible API on the same provider does not get OpenRouter's ids
    s = _s(
        tmp_path,
        llm_provider="openai",
        openai_compat_base_url="https://llm.example/v1",
        openai_compat_api_key="k",
        model_fast="my-model",
    )
    assert s.model_for("fast") == "my-model" and s.llm_extra_body == ""


def test_openrouter_settings_are_untouched(tmp_path: Path) -> None:
    left = {k.lower(): v for k, v in OPENROUTER.items() if k != "LLM_PROVIDER"}
    s = _s(tmp_path, **left, llm_provider="openai", openai_compat_api_key="k")
    assert s.model_for("fast") == OPENROUTER["MODEL_FAST"]


def test_the_readme_quickstart_needs_only_three_lines(tmp_path: Path, monkeypatch: Any) -> None:
    # .env.example plus the three lines the README tells a new user to set (the test run's own
    # provider variables would override the file, so they are cleared)
    from api.core.settings import ROOT_DIR

    for var in ("LLM_PROVIDER", "SANDBOX_PROVIDER", "LLM_CACHE_MODE", "TAVILY_API_KEY", "OFFLINE"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        (ROOT_DIR / ".env.example").read_text()
        + "\nLLM_PROVIDER=openai\nOPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1\n"
        + "OPENAI_COMPAT_API_KEY=sk-or-test\n"
    )
    s = Settings(_env_file=env, cache_dir=tmp_path, runs_dir=tmp_path / "runs")
    assert s.model_for("fast") == OPENROUTER["MODEL_FAST"]
    assert s.model_for("judge") == OPENROUTER["MODEL_JUDGE"]
    assert s.llm_extra_body == OPENROUTER["LLM_EXTRA_BODY"]
    assert s.llm_label == "OPENROUTER"
