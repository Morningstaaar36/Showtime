"""A provider is a plug-in: register one and settings select it by name, with no other file
edited (step 6g). Unknown names fail at startup with the valid names listed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.adapters.llm import LLMClient
from api.adapters.providers import LLM, SANDBOX, SEARCH, ensure_loaded
from api.adapters.providers.base import LlmProvider, Requirement, SandboxProvider, SearchProvider
from api.adapters.sandbox import NO_SANDBOX
from api.app.state import build_runner, build_state
from api.core.settings import Settings
from api.tests.evidence_fakes import reset_engine, use_test_settings


@pytest.fixture
def test_providers() -> Iterator[None]:
    """One test-only provider of each kind (each well under 40 lines)."""
    ensure_loaded()
    LLM.register(
        LlmProvider(
            kind="llm",
            name="echo",
            title="Echo test LLM",
            requirements=(Requirement("ECHO_URL", "local_llm_base_url", "the echo server"),),
            is_cloud=True,
            base_url=lambda s: "https://echo.test/v1",
            key=lambda s: "echo-key",
            key_env="ECHO_KEY",
            label=lambda s: "ECHO",
            where=lambda s: "the echo server",
        )
    )

    class Runner:
        provider, isolation, parallel = "box", NO_SANDBOX, 7

        async def health(self) -> dict[str, Any]:
            return {"ok": True, "detail": "box"}

    SANDBOX.register(
        SandboxProvider(kind="sandbox", name="box", title="Box", build=lambda s: Runner())
    )
    SEARCH.register(
        SearchProvider(
            kind="search",
            name="canned",
            title="Canned search",
            live=True,
            build=lambda s: SimpleNamespace(live=True, search=None, extract=None, health=None),
        )
    )
    yield
    LLM.unregister("echo")
    SANDBOX.unregister("box")
    SEARCH.unregister("canned")


def test_a_registered_llm_provider_is_selectable_by_name(
    test_providers: None, tmp_path: Path
) -> None:
    s = Settings(_env_file=None, llm_provider="echo", model_fast="m", cache_dir=tmp_path)
    c = LLMClient(s)
    assert (c.base_url, c.api_key, c.where) == (
        "https://echo.test/v1",
        "echo-key",
        "the echo server",
    )
    assert s.cloud_llm and s.llm_label == "ECHO"


def test_a_registered_sandbox_and_search_are_selectable_by_name(
    test_providers: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = use_test_settings(tmp_path, monkeypatch).model_copy(
        update={"sandbox_provider": "box", "search_provider": "canned"}
    )
    try:
        assert build_runner(s).parallel == 7
        assert build_state(s).search.live is True
    finally:
        reset_engine()


def test_an_unknown_provider_fails_at_startup_listing_the_valid_names(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match=r"LLM_PROVIDER: Unknown llm provider 'nebulous'.*fake, local, nebius, openai",
    ):
        Settings(_env_file=None, llm_provider="nebulous")
    with pytest.raises(ValueError, match=r"SANDBOX_PROVIDER: .*docker, fake, nebius"):
        Settings(_env_file=None, sandbox_provider="kubernetes")
    with pytest.raises(ValueError, match=r"SEARCH_PROVIDER: .*none, tavily"):
        Settings(_env_file=None, search_provider="bing")


def test_an_alias_names_the_same_provider() -> None:
    assert (
        Settings(_env_file=None, llm_provider="openai_compat", model_fast="m").llm_provider
        == "openai"
    )


def test_nebius_and_tavily_are_selected_by_env_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With fake clients only: no live call (NOT a live test of Nebius or Tavily)."""
    base = use_test_settings(tmp_path, monkeypatch)
    s = Settings(
        _env_file=None,
        **{
            **base.model_dump(),
            "llm_provider": "nebius",
            "sandbox_provider": "nebius",
            "search_provider": "tavily",
            "nebius_api_key": "nb",
            "nebius_project_id": "project-e00x",
            "tavily_api_key": "tv",
            "model_fast": "nvidia/x",
            "offline": False,  # the test settings are offline; nothing here calls out
        },
    )
    try:
        assert LLMClient(s).base_url.startswith("https://api.tokenfactory.nebius.com")
        assert build_runner(s).provider == "nebius"
        st = build_state(s, llm=LLMClient(s))
        assert st.search.live is True
    finally:
        reset_engine()


def test_health_states_what_each_provider_is_and_can_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app

    s = use_test_settings(tmp_path, monkeypatch)
    st = build_state(s, llm=FakeLLM({}, s), runner=FakeRunner(s.runs_dir, max_parallel=3))
    try:
        with TestClient(create_app(state=st, settings=s)) as c:
            p = c.get("/api/v1/health").json()["providers"]
        assert p["llm"]["title"] and p["llm"]["is_cloud"] is False
        assert set(p["llm"]["capabilities"]) == {"json_schema", "spare_key", "fallback_to_local"}
        assert p["sandbox"]["parallel"] == 3 and p["sandbox"]["title"]
        assert p["search"]["provider"] == s.search_provider and p["search"]["title"]
    finally:
        reset_engine()
