"""`.env.example` documents every setting, provider requirement and preset key (no drift), and
`make use-<preset>` takes its presets from the providers."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

from api.adapters.providers import LLM, ensure_loaded
from api.adapters.providers.base import LlmProvider, Requirement
from api.core.settings import ROOT_DIR


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT_DIR / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_env_example_documents_everything() -> None:
    ee = _load("env_example")
    assert ee.missing(ee.EXAMPLE.read_text()) == {}, "run: python scripts/env_example.py --write"


def test_presets_and_keys_come_from_the_providers() -> None:
    sp = _load("switch_provider")
    known = sp.presets()
    assert {"openrouter", "local"} <= set(known)
    assert sp.keys_needed("local") == []
    assert sp.keys_needed("openrouter") == ["OPENAI_COMPAT_API_KEY"]
    ensure_loaded()
    LLM.register(
        LlmProvider(
            kind="llm",
            name="acme",
            title="Acme",
            requirements=(Requirement("ACME_KEY", "openai_compat_api_key", "key", True),),
            presets={"acme": {"LLM_PROVIDER": "acme", "MODEL_FAST": "acme/m"}},
        )
    )
    try:
        assert sp.presets()["acme"][1]["MODEL_FAST"] == "acme/m"  # a new provider's preset
        assert sp.keys_needed("acme") == ["ACME_KEY"]
    finally:
        LLM.unregister("acme")
