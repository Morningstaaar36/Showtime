"""What a provider is: one small description per external service (LLM, sandbox, search).

A provider says what it needs (settings and environment variables), what it can do
(capabilities), how to build its client, and how to make the smallest real call to check it.
Code asks for capabilities, never for a provider's name. Adding a provider is one new module in
this package that calls `register(...)`: docs/ADDING_A_PROVIDER.md.

Nothing here imports Settings at runtime (settings validate provider names against these
registries, so the import must go one way).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

Kind = Literal["llm", "sandbox", "search"]


@dataclass(frozen=True)
class Requirement:
    """One thing a provider needs, by its .env name."""

    env: str  # e.g. NEBIUS_API_KEY
    setting: str  # the Settings attribute it fills, e.g. nebius_api_key
    what: str  # plain words: "your Nebius Token Factory API key"
    secret: bool = False


@dataclass(frozen=True)
class LiveCheck:
    """The result of the smallest real call: ok, or what is missing and how to fix it."""

    status: Literal["ok", "failed", "skipped"]
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class Provider:
    """Common to every kind of provider."""

    kind: Kind
    name: str
    title: str  # plain name for people: "Nebius Token Factory"
    requirements: tuple[Requirement, ...] = ()
    aliases: tuple[str, ...] = ()
    # .env values `make use-<preset>` writes (model ids, prices, request extras); never keys
    presets: dict[str, dict[str, str]] = field(default_factory=dict)
    # the smallest real call with these settings (None: nothing to check, e.g. a fake)
    check_live: Callable[[Any], Awaitable[LiveCheck]] | None = None
    # its own wording for what is missing (default: "<title> is not configured: set X in .env.")
    missing_text: Callable[[list[Requirement]], str] | None = None

    def missing(self, settings: Any) -> list[Requirement]:
        """Requirements the settings leave empty."""
        return [r for r in self.requirements if not str(getattr(settings, r.setting, "")).strip()]

    def not_configured(self, settings: Any) -> str | None:
        """A clear "not configured" message, or None when everything it needs is set."""
        gone = self.missing(settings)
        if not gone:
            return None
        if self.missing_text is not None:
            return self.missing_text(gone)
        names = " and ".join(r.env for r in gone)
        return f"{self.title} is not configured: set {names} in .env."


@dataclass(frozen=True)
class LlmProvider(Provider):
    """An OpenAI-compatible chat endpoint and how to talk to it."""

    is_cloud: bool = False  # MODEL_* ids and PRICE_* apply; otherwise LOCAL_LLM_MODEL, free
    base_url: Callable[[Any], str] = lambda s: ""
    key: Callable[[Any], str] | None = None  # None: needs no key
    key_env: str | None = None
    spare_key: Callable[[Any], str] | None = None  # a second key to switch to on a quota
    label: Callable[[Any], str] = lambda s: "LOCAL"  # the badge
    where: Callable[[Any], str] = lambda s: ""  # for error messages
    sends_extra_body: bool = True  # LLM_EXTRA_BODY may be sent
    directive_on_every_model: bool = False  # /think, /no_think even for non-Nemotron ids
    one_request_at_a_time: bool = False  # a local GPU server
    health: Literal["models", "hosted", "fake"] = "hosted"
    is_fake: bool = False


@dataclass(frozen=True)
class SandboxProvider(Provider):
    """Where simulations and untrusted code run. Capabilities live on the runner it builds
    (`runner.isolation`, `runner.parallel`)."""

    build: Callable[[Any], Any] = lambda s: None


@dataclass(frozen=True)
class SearchProvider(Provider):
    """Web search for evidence. `build(settings)` returns a client with `live`, `health()`,
    `search(...)` and `extract(...)`."""

    build: Callable[[Any], Any] = lambda s: None
    live: bool = False  # it searches the web (False: the incident dataset only)


P = TypeVar("P", bound=Provider)


class Registry(Generic[P]):
    """Providers of one kind, by name (and alias)."""

    def __init__(self, kind: Kind) -> None:
        self.kind = kind
        self._by_name: dict[str, P] = {}
        self._alias: dict[str, str] = {}

    def register(self, provider: P) -> P:
        self._by_name[provider.name] = provider
        for a in provider.aliases:
            self._alias[a] = provider.name
        return provider

    def unregister(self, name: str) -> None:
        self._by_name.pop(name, None)
        self._alias = {a: n for a, n in self._alias.items() if n != name}

    def canonical(self, name: str) -> str:
        """The registered name for `name` or its alias; ValueError lists the valid ones."""
        n = self._alias.get(name, name)
        if n not in self._by_name:
            raise ValueError(
                f"Unknown {self.kind} provider '{name}'. Valid: {', '.join(self.names())}."
            )
        return n

    def get(self, name: str) -> P:
        return self._by_name[self.canonical(name)]

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def all(self) -> list[P]:
        return [self._by_name[n] for n in self.names()]
