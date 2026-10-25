"""Application container: settings, plugins, providers and services.

This is the only place that decides which provider implementation to use, so switching
to Nebius is a matter of `.env` values (LLM_PROVIDER, SANDBOX_PROVIDER).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import select

from api.adapters.llm import FakeLLM, LLMClient
from api.adapters.osm import OpenStreetMap
from api.adapters.providers import llm_provider, sandbox_provider, search_provider
from api.adapters.sandbox import SandboxRunner
from api.adapters.search import TavilySearch
from api.adapters.weather import OpenMeteoWeather
from api.core.plugins import PluginHost, load_plugins
from api.core.settings import Settings
from api.db.models import UserSetting
from api.db.session import db_session, migrate
from api.models import Usage
from api.orchestrator.projects import ProjectService
from api.orchestrator.runs import RunService

log = logging.getLogger("showtime.state")

# Settings the UI may change (validated by Settings itself). Keys and URLs are not here.
EDITABLE = {
    "pre_movement_s",
    "safety_factor",
    "density_warn_ppm2",
    "density_danger_ppm2",
    "max_rounds",
    "attacks_per_round",
    "fixes_per_attack",
    "fix_min_gain",
    "max_people",
    "session_max_tokens",
    "tavily_max_calls",
    "walk_speed_mean",
    "specific_flow",
    "unit_costs",
}
UI_ONLY = {"units", "theme", "onboarding_done", "reduced_motion"}


@dataclass
class UsageMeter:
    """Process-wide token and cost totals (session meters live on sessions)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_role: dict[str, int] = field(default_factory=dict)

    def add(self, u: Usage) -> None:
        self.prompt_tokens += u.prompt_tokens
        self.completion_tokens += u.completion_tokens
        self.cost_usd += u.cost_usd
        self.calls += 1
        self.by_role[u.role] = self.by_role.get(u.role, 0) + u.prompt_tokens + u.completion_tokens


@dataclass
class AppState:
    """Everything routes need."""

    base_settings: Settings
    host: PluginHost
    llm: Any
    runner: SandboxRunner
    search: TavilySearch
    weather: OpenMeteoWeather
    osm: OpenStreetMap
    projects: ProjectService
    runs: RunService
    usage: UsageMeter
    sessions: Any = None  # SessionManager (set after construction)
    # why the sample projects could not be installed at startup (shown in /health), or None
    samples_error: str | None = None
    ui: dict[str, Any] = field(default_factory=dict)

    @property
    def registry(self) -> Any:
        return self.host.registry

    @property
    def settings(self) -> Settings:
        """Base settings with UI overrides applied."""
        overrides = {k: v for k, v in self.ui.items() if k in EDITABLE}
        return self.base_settings.model_copy(update=overrides) if overrides else self.base_settings

    def refresh_overrides(self) -> None:
        """Reload UI settings from the database and push them into services."""
        with db_session() as s:
            rows = list(s.exec(select(UserSetting)))
        self.ui = {r.key: r.value for r in rows if not r.key.startswith("_")}  # "_" = internal
        self.runs.settings = self.settings

    def save_overrides(self, values: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist UI settings; returns the stored values."""
        clean = {k: v for k, v in values.items() if k in EDITABLE | UI_ONLY}
        Settings.model_validate(
            {**self.base_settings.model_dump(), **{k: v for k, v in clean.items() if k in EDITABLE}}
        )
        with db_session() as s:
            for k, v in clean.items():
                row = s.get(UserSetting, k) or UserSetting(key=k)
                row.value = v
                s.add(row)
            s.commit()
        self.refresh_overrides()
        return clean


def build_runner(settings: Settings) -> SandboxRunner:
    """The sandbox of SANDBOX_PROVIDER, from its registry entry (api/adapters/providers)."""
    runner: SandboxRunner = sandbox_provider(settings.sandbox_provider).build(settings)
    return runner


def build_state(
    settings: Settings, llm: Any | None = None, runner: SandboxRunner | None = None
) -> AppState:
    """Create the container (runs migrations, loads plugins)."""
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    migrate()
    host = load_plugins(settings.root_dir)
    usage = UsageMeter()
    if llm is None:
        llm = (
            FakeLLM({}, settings)
            if llm_provider(settings.llm_provider).is_fake
            else LLMClient(settings, on_usage=usage.add)
        )
    runner = runner or build_runner(settings)
    search = search_provider(settings.search_provider).build(settings)
    weather = OpenMeteoWeather(
        settings.weather_base_url,
        settings.weather_archive_url,
        settings.cache_dir / "weather",
        offline=settings.offline,
    )
    osm = OpenStreetMap(
        settings.nominatim_url,
        settings.overpass_url,
        settings.cache_dir / "osm",
        offline=settings.offline,
    )
    projects = ProjectService(host.registry)
    runs = RunService(settings, host.registry, runner, hooks=host.pm)
    state = AppState(
        base_settings=settings,
        host=host,
        llm=llm,
        runner=runner,
        search=search,
        weather=weather,
        osm=osm,
        projects=projects,
        runs=runs,
        usage=usage,
    )
    state.refresh_overrides()
    try:
        from api.orchestrator.demos import install_demos

        install_demos(state)
    except Exception as exc:  # samples are optional; never block startup, but say so
        log.exception("sample projects not installed")
        state.samples_error = f"{type(exc).__name__}: {exc}"
    return state
