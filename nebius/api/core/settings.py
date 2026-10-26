"""Application settings: the only place that reads environment variables.

Every tunable number has a default here and in `.env.example`; sources for the
simulation defaults are listed in `docs/ASSUMPTIONS.md`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
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

    # --- Providers (names from the registries in api/adapters/providers; a new provider is a
    # new module there, no edit here) ---
    llm_provider: str = "local"
    sandbox_provider: str = "docker"
    # used while the chosen sandbox is not configured (e.g. Nebius before you have a key)
    sandbox_fallback: str = "docker"
    search_provider: str = "tavily"  # without TAVILY_API_KEY it is off: the incident dataset only

    # --- Local LLM ---
    local_llm_base_url: str = "http://127.0.0.1:8080/v1"
    local_llm_model: str = "nemotron-nano-9b-v2-q4_k_m"
    llm_supports_json_schema: bool = True
    llm_timeout_s: float = 120.0
    # one agent step in total (its call, the repair round, retries, escalation): a model that
    # never answers cannot hold a test up for retries x attempts x timeouts
    agent_step_timeout_s: float = Field(default=300.0, gt=0)
    # a hosted model that keeps failing (rate limit, unreachable, this many 5xx in a row) is
    # skipped for llm_pause_s; one timeout or one 4xx is not a reason to stop asking it
    llm_pause_s: float = Field(default=600.0, ge=0)
    llm_server_errors_to_pause: int = Field(default=3, ge=1)
    # building a real case's venue from its description (the designer agent)
    case_build_timeout_s: float = Field(default=360.0, gt=0)
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
    # the Token Factory project that runs the sandboxes (Project settings, under the project
    # name); sent with every request alongside NEBIUS_API_KEY
    nebius_project_id: str = ""
    sandbox_max_parallel: int = Field(default=1, ge=1, le=16)
    # extra random crowds the seed check runs when the organizer doesn't choose: fewer when the
    # sandbox runs one at a time, more when it runs several at once (at most seeds_extra_max)
    seeds_extra_serial: int = Field(default=3, ge=1)
    seeds_extra_parallel: int = Field(default=5, ge=1)
    seeds_extra_max: int = Field(default=5, ge=1)
    sim_image: str = "showtime-sim:latest"
    sim_platform: str = ""  # e.g. linux/amd64 for JuPedSim under Apple Silicon emulation
    sim_mem_limit: str = "2g"
    sim_cpus: float = 4.0
    sim_dev_mount: bool = False  # mount local sim/ over /app during development
    sim_user: str = ""  # container "uid:gid"; defaults to this process's user, never root
    # what the attack suite recorded against the real sandbox (make sandbox-proof)
    sandbox_proof_file: Path = ROOT_DIR / "api" / "data" / "sandbox_proof.json"
    sim_pids_limit: int = Field(default=256, ge=16)  # processes in a simulation container
    code_pids_limit: int = Field(default=64, ge=8)  # processes in a code-job container

    # --- Guards on AI-written scenario scripts (sent with each run that has one) ---
    script_call_s: float = Field(default=0.05, gt=0)  # one on_step call
    script_total_s: float = Field(default=3.0, gt=0)  # every call of one script in one run
    script_line_budget: int = Field(default=200_000, ge=1000)  # lines run in one call
    script_max_range: int = Field(default=1_000_000, ge=1000)  # numbers in one range()
    script_max_acts_step: int = Field(default=20, ge=1)  # actions in one call
    script_max_acts_total: int = Field(default=400, ge=1)  # actions in one run
    script_max_notes: int = Field(default=10, ge=0)
    script_max_added_people: int = Field(default=2000, ge=0)
    # all of a script's slow-downs together stop at this share of normal walking speed
    script_min_speed_share: float = Field(default=0.1, gt=0, le=1)
    # heap growth allowed once untrusted code runs, as a share of the container's room left
    sandbox_memory_share: float = Field(default=0.85, gt=0, lt=1)

    # --- Search and weather ---
    tavily_api_key: str = ""
    tavily_max_calls: int = 20  # live search calls per session (a cached search is free)
    # the red team's web search for real incidents like this venue's (when search is live)
    search_queries_per_session: int = Field(default=2, ge=0, le=3)
    search_results_per_query: int = Field(default=3, ge=1, le=10)
    search_max_sources: int = Field(default=5, ge=1, le=20)
    # the evidence desk: web lookups about the briefed place and event (0 turns it off), and
    # the sites to search for them (comma-separated; empty: the whole web)
    evidence_desk_queries: int = Field(default=2, ge=0, le=3)
    evidence_desk_domains: str = ""
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    # tried after OVERPASS_URL when it fails (comma-separated), and last the slower ones
    overpass_fallback_urls: str = (
        "https://lz4.overpass-api.de/api/interpreter,https://z.overpass-api.de/api/interpreter"
    )
    overpass_late_urls: str = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    map_tiles_url: str = "https://tiles.openfreemap.org/planet"  # a TileJSON document
    osm_max_span_km: float = Field(default=1.3, gt=0)  # the largest area loaded from the map
    # the browser's maps: the style of the place picker, and the raster tiles under the 3D view
    map_style_url: str = "https://tiles.openfreemap.org/styles/liberty"
    map_raster_tiles_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    # where the place picker opens: "lat,lon,zoom" (the default is the whole world)
    map_start: str = "20,0,1.5"

    @field_validator("map_start")
    @classmethod
    def _map_start_valid(cls, v: str) -> str:
        parts = [p.strip() for p in v.split(",")]
        try:
            lat, lon, zoom = (float(p) for p in parts)
        except ValueError:
            raise ValueError('MAP_START must be "lat,lon,zoom", e.g. "23.73,90.39,13"') from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= zoom <= 22):
            raise ValueError("MAP_START is out of range (lat -90..90, lon -180..180, zoom 0..22)")
        return v

    @property
    def map_start_point(self) -> dict[str, float]:
        lat, lon, zoom = (float(p) for p in self.map_start.split(","))
        return {"lat": lat, "lon": lon, "zoom": zoom}

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
    # how long the web app waits for a read, and for a write that may start an agent, before
    # it says the server took too long (sent to the app in /health)
    web_read_timeout_s: float = Field(default=60.0, gt=0)
    web_write_timeout_s: float = Field(default=330.0, gt=0)
    # more web origins allowed to call the API (comma-separated), besides WEB_ORIGIN: the app on
    # 127.0.0.1 and the Vite preview server by default
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:4173"
    upload_max_bytes: int = 5_000_000
    log_level: str = "INFO"

    @field_validator("llm_provider", "sandbox_provider", "search_provider", "sandbox_fallback")
    @classmethod
    def _known_provider(cls, v: str, info: Any) -> str:
        """A registered provider name (or alias), else an error that lists the valid names."""
        from api.adapters.providers import registry

        kind = str(info.field_name).removesuffix("_provider").removesuffix("_fallback")
        try:
            return registry(kind).canonical(v.strip())
        except ValueError as exc:
            env = str(info.field_name).upper()
            raise ValueError(f"{env}: {exc}") from exc

    @field_validator("density_danger_ppm2")
    @classmethod
    def _danger_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("DENSITY_DANGER_PPM2 must be > 0")
        return v

    @model_validator(mode="after")
    def _model_ids_set(self) -> Settings:
        """An empty model id would only show up as a provider error on the first call."""
        from api.adapters.providers import llm_provider

        self._take_provider_preset()
        if self.cloud_llm and not self.model_fast.strip():
            raise ValueError(
                f"MODEL_FAST is empty: set it in .env to a model id the provider serves "
                f"(LLM_PROVIDER={self.llm_provider}). MODEL_LONG, MODEL_MAIN and MODEL_JUDGE "
                "fall back to it when empty."
            )
        if self.web_write_timeout_s < self.agent_step_timeout_s:
            raise ValueError(
                "WEB_WRITE_TIMEOUT_S must be at least AGENT_STEP_TIMEOUT_S, or the app gives up "
                "on a request while its agent is still allowed to work."
            )
        from api.adapters.providers import sandbox_provider

        if sandbox_provider(self.sandbox_fallback).not_configured(self):
            raise ValueError(
                f"SANDBOX_FALLBACK={self.sandbox_fallback} must work without setup: "
                f"{sandbox_provider(self.sandbox_fallback).not_configured(self)}"
            )
        spec = llm_provider(self.llm_provider)
        if not spec.is_cloud and not spec.is_fake and not self.local_llm_model.strip():
            raise ValueError("LOCAL_LLM_MODEL is empty: set it in .env (LLM_PROVIDER=local).")
        return self

    @property
    def script_guards(self) -> dict[str, float]:
        """The guards the sim image applies to a scenario script (keys as the image reads them)."""
        keys = (
            "script_call_s",
            "script_total_s",
            "script_line_budget",
            "script_max_range",
            "script_max_acts_step",
            "script_max_acts_total",
            "script_max_notes",
            "script_max_added_people",
            "script_min_speed_share",
            "sandbox_memory_share",
        )
        return {k: float(getattr(self, k)) for k in keys}

    @property
    def allowed_origins(self) -> list[str]:
        """WEB_ORIGIN plus CORS_ORIGINS, without blanks or repeats."""
        extra = [o.strip() for o in self.cors_origins.split(",")]
        return list(dict.fromkeys(o for o in [self.web_origin, *extra] if o))

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
        from api.adapters.providers import llm_provider

        return llm_provider(self.llm_provider).is_cloud

    @property
    def llm_label(self) -> str:
        """Short provider name for the UI badge and reports."""
        from api.adapters.providers import llm_provider

        return llm_provider(self.llm_provider).label(self)

    def _take_provider_preset(self) -> None:
        """Switching LLM_PROVIDER needs no other edit: a model id, price or request extra that
        still holds another provider's preset value (a leftover from `make use-*`) takes the
        active provider's preset value, and with no MODEL_FAST at all every empty one does. A
        value of your own is kept, and with MODEL_FAST set an empty role still falls back to it."""
        from pydantic import TypeAdapter

        from api.adapters.providers import LLM, llm_provider

        spec = llm_provider(self.llm_provider)
        if not spec.is_cloud or not spec.presets:
            return
        own = next(iter(spec.presets.values()))
        # a preset for one service on a generic API (OpenRouter on "openai") applies only there
        if any(
            k.endswith("BASE_URL") and str(getattr(self, k.lower(), v)) != v for k, v in own.items()
        ):
            return
        others = [p for o in LLM.all() if o.name != spec.name for p in o.presets.values()]
        fields = type(self).model_fields
        unset = not self.model_fast.strip() or any(
            p.get("MODEL_FAST") == self.model_fast for p in others if p.get("MODEL_FAST")
        )
        for key in {k for p in [own, *others] for k in p} - {"LLM_PROVIDER"}:
            name = key.lower()
            if name not in fields or (key not in own and not name.startswith("model_")):
                continue  # another provider's own settings (its base URL, label) stay as they are
            now = str(getattr(self, name))
            leftover = bool(now.strip()) and any(key in p and str(p[key]) == now for p in others)
            # with no model chosen, a value still at its setting's default was not chosen either
            untouched = not now.strip() or now == str(fields[name].default)
            if leftover or (unset and untouched):
                value = own.get(key, fields[name].default)
                setattr(self, name, TypeAdapter(fields[name].annotation).validate_python(value))

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
