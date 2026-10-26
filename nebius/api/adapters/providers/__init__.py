"""Registries of the three external services: LLM, sandbox and search providers.

Every module in this package that is not `base` describes providers and registers them on
import; `ensure_loaded()` imports them all, so a new provider is one new file here.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from api.adapters.providers.base import (
    LiveCheck,
    LlmProvider,
    Provider,
    Registry,
    Requirement,
    SandboxProvider,
    SearchProvider,
)

LLM: Registry[LlmProvider] = Registry("llm")
SANDBOX: Registry[SandboxProvider] = Registry("sandbox")
SEARCH: Registry[SearchProvider] = Registry("search")
_loaded = False


def ensure_loaded() -> None:
    """Import every provider module once (they register themselves)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for mod in pkgutil.iter_modules(__path__):
        if mod.name != "base":
            importlib.import_module(f"{__name__}.{mod.name}")


def llm_provider(name: str) -> LlmProvider:
    ensure_loaded()
    return LLM.get(name)


def sandbox_provider(name: str) -> SandboxProvider:
    ensure_loaded()
    return SANDBOX.get(name)


def search_provider(name: str) -> SearchProvider:
    ensure_loaded()
    return SEARCH.get(name)


def registry(kind: str) -> Registry[Any]:
    """The registry of one kind: "llm", "sandbox" or "search"."""
    ensure_loaded()
    regs: dict[str, Registry[Any]] = {"llm": LLM, "sandbox": SANDBOX, "search": SEARCH}
    return regs[kind]


__all__ = [
    "LLM",
    "SANDBOX",
    "SEARCH",
    "LiveCheck",
    "LlmProvider",
    "Provider",
    "Registry",
    "Requirement",
    "SandboxProvider",
    "SearchProvider",
    "ensure_loaded",
    "llm_provider",
    "registry",
    "sandbox_provider",
    "search_provider",
]
