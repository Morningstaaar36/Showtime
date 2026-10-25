"""Application settings: the only place that reads environment variables.

Every tunable number has a default here and in `.env.example`; sources for the
simulation defaults are listed in `docs/ASSUMPTIONS.md`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

LlmRole = Literal["fast", "long", "main", "judge"]


class Settings(BaseSettings):
    """Validated configuration for the whole API process."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Paths ---
    root_dir: Path = ROOT_DIR
    runs_dir: Path = ROOT_DIR / "runs"
    cache_dir: Path = ROOT_DIR / "cache"
    data_dir: Path = ROOT_DIR / "data"
    db_url: str = ""
    host_runs_dir: str = ""  # absolute host path of runs/ when the API runs in Docker

    # --- Providers ---
    llm_provider: Literal["local", "nebius", "openai", "fake"] = "local"
    sandbox_provider: Literal["docker", "nebius", "fake"] = "docker"

    # --- Local LLM ---
    local_llm_base_url: str = "http://127.0.0.1:8080/v1"
    local_llm_model: str = "nemotron-nano-9b-v2-q4_k_m"
    llm_supports_json_schema: bool = True
    llm_timeout_s: float = 120.0
    # one agent step in total (its call, the repair round, retries, escalation): a model that
    # never answers cannot hold a test up for retries x attempts x timeouts
    agent_step_timeout_s: float = Field(default=300.0, gt=0)
    llm_reasoning: bool = False
    # a `fast`-role answer that stays invalid after its repair round is retried once on `main`
    llm_escalate: bool = True

    # --- Nebius Token Factory ---
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    model_fast: str = ""
    model_long: str = ""
    model_main: str = ""
    model_judge: str = ""
    # a second model for any role whose model fails at the provider (removed, overloaded, 404)
    model_fallback: str = ""
    price_fast_in: float = 0.0
    price_fast_out: float = 0.0
    price_long_in: float = 0.0
    price_long_out: float = 0.0
    price_main_in: float = 0.0
    price_main_out: float = 0.0
    price_judge_in: float = 0.0
    price_judge_out: float = 0.0

    # --- Any other OpenAI-compatible API (LLM_PROVIDER=openai; uses MODEL_* and PRICE_*) ---
    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    # a second key for the same API, used once the first is out of credit or rate limited
    openai_compat_api_key_fallback: str = ""
    openai_compat_label: str = "CLOUD"
    # Extra JSON fields for every hosted chat request, e.g. OpenRouter's
    # {"reasoning": {"enabled": false}} so reasoning models answer instead of thinking.
    llm_extra_body: str = ""
    # when the hosted model fails (quota, outage, timeout), answer with the local llama-server
    llm_fallback: Literal["local", "none"] = "local"

    @field_validator("llm_extra_body")
    @classmethod
    def _json_object(cls, v: str) -> str:
        if v.strip():
            try:
                ok = isinstance(json.loads(v), dict)
            except ValueError:
                ok = False
            if not ok:
                raise ValueError('must be a JSON object, e.g. {"reasoning":{"enabled":false}}')
        return v

    @property
    def llm_extra_body_dict(self) -> dict[str, Any]:
        """LLM_EXTRA_BODY parsed (empty when unset)."""
        return dict(json.loads(self.llm_extra_body)) if self.llm_extra_body.strip() else {}

    # --- Nebius Sandboxes ---
    nebius_sandbox_base_url: str = "https://api.tokenfactory.nebius.com/sandboxes"
    sandbox_max_parallel: int = Field(default=1, ge=1, le=16)
    sim_image: str = "showtime-sim:latest"
    sim_platform: str = ""  # e.g. linux/amd64 for JuPedSim under Apple Silicon emulation
    sim_mem_limit: str = "2g"
    sim_cpus: float = 4.0
    sim_dev_mount: bool = False  # mount local sim/ over /app during development
    sim_user: str = ""  # container "uid:gid"; defaults to this process's user, never root

    # --- Search and weather ---
    tavily_api_key: str = ""
    tavily_max_calls: int = 20
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    offline: bool = False

    # --- Caches ---
    llm_cache_mode: Literal["off", "record", "replay", "record_replay"] = "record_replay"

    # --- Simulation defaults ---
    max_people: int = 8000
    max_sim_s: float = 900.0
    max_wall_s: float = 600.0
    tier2_max_sim_s: float = 180.0
    walk_speed_mean: float = 1.34
    walk_speed_sd: float = 0.26
    slow_walker_fraction: float = 0.05
    agent_radius: float = 0.22
    # collision-free speed model: time gap each person keeps to the one ahead (s); 0.25 s is
    # calibrated on the Juelich 2006 bottleneck series (docs/VALIDATION.md); 1.0 is the model default
    agent_time_gap: float = Field(default=0.25, gt=0.05, le=3.0)
    sim_dt_s: float = 0.05
    danger_min_duration_s: float = 5.0
    # planning targets for 'everyone out' when no hazard time is known (labelled as targets)
    unit_costs: dict[str, Any] = Field(default_factory=dict)  # budget prices; example ones if empty
    target_evac_indoor_s: float = 300.0
    target_evac_outdoor_s: float = 480.0
    specific_flow: float = 1.3
    stair_speed: float = 0.6
    stair_flow: float = 1.0
    density_warn_ppm2: float = 3.5
    density_danger_ppm2: float = 5.0
    safety_factor: float = 1.5
    pre_movement_s: float = 60.0
    default_seed: int = 42

    # --- Session budgets ---
    max_rounds: int = 3
    attacks_per_round: int = 5
    fixes_per_attack: int = 2
    fix_targets: int = 2
    fix_min_gain: float = 0.10
    marshals: int = 5
    session_max_tokens: int = 400_000
    session_max_runs: int = 40
    session_max_wall_s: float = 1800.0

    # --- Server ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://localhost:5173"
    upload_max_bytes: int = 5_000_000
    log_level: str = "INFO"

    @field_validator("density_danger_ppm2")
    @classmethod
    def _danger_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("DENSITY_DANGER_PPM2 must be > 0")
        return v

    @property
    def database_url(self) -> str:
        """SQLite URL, defaulting to `<root>/state/showtime.sqlite`."""
        if self.db_url:
            return self.db_url
        return f"sqlite:///{self.state_dir / 'showtime.sqlite'}"

    @property
    def state_dir(self) -> Path:
        """Folder holding the SQLite database (gitignored)."""
        return self.root_dir / "state"

    @property
    def cloud_llm(self) -> bool:
        """True when the LLM is a hosted API (model ids and prices come from MODEL_*/PRICE_*)."""
        return self.llm_provider in ("nebius", "openai")

    @property
    def llm_label(self) -> str:
        """Short provider name for the UI badge and reports."""
        return {"nebius": "NEBIUS", "openai": self.openai_compat_label.upper() or "CLOUD"}.get(
            self.llm_provider, "LOCAL"
        )

    def model_for(self, role: LlmRole) -> str:
        """Model id for an LLM role under the active provider."""
        if not self.cloud_llm:
            return self.local_llm_model
        mapping = {
            "fast": self.model_fast,
            "long": self.model_long or self.model_fast,
            "main": self.model_main or self.model_fast,
            "judge": self.model_judge or self.model_main or self.model_fast,
        }
        return mapping[role]

    def price_for(self, role: LlmRole) -> tuple[float, float]:
        """(input, output) USD per 1M tokens for a role. Local and ":free" models cost 0."""
        if not self.cloud_llm or self.model_for(role).endswith(":free"):
            return (0.0, 0.0)
        return (
            float(getattr(self, f"price_{role}_in")),
            float(getattr(self, f"price_{role}_out")),
        )

    def public_dict(self) -> dict[str, object]:
        """Settings safe to send to the browser (no keys)."""
        return {
            "llm_provider": self.llm_provider,
            "sandbox_provider": self.sandbox_provider,
            "tavily_enabled": bool(self.tavily_api_key) and not self.offline,
            "max_people": self.max_people,
            "max_sim_s": self.max_sim_s,
            "density_warn_ppm2": self.density_warn_ppm2,
            "density_danger_ppm2": self.density_danger_ppm2,
            "safety_factor": self.safety_factor,
            "pre_movement_s": self.pre_movement_s,
            "max_rounds": self.max_rounds,
            "attacks_per_round": self.attacks_per_round,
            "fixes_per_attack": self.fixes_per_attack,
            "session_max_tokens": self.session_max_tokens,
            "tavily_max_calls": self.tavily_max_calls,
            "specific_flow": self.specific_flow,
            "walk_speed_mean": self.walk_speed_mean,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
