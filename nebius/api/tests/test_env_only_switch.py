"""Switching to Nebius needs only .env (step: "only replacing env is enough").

Checked against the Nebius docs and contree-sdk 0.3.6:
- Token Factory: OpenAI-compatible at https://api.tokenfactory.nebius.com/v1/, key NEBIUS_API_KEY;
  the preset's Nemotron ids are the ones in Nebius's public model info.
- Sandboxes: the same NEBIUS_API_KEY plus NEBIUS_PROJECT_ID (sent as the `Project` header);
  outbound network is ON by default and is switched off per run with
  {"networking": {"enabled": false}} on POST /v1/instances, which SDK 0.3.6 has no argument for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from api.adapters.providers import llm_provider, sandbox_provider
from api.core.settings import Settings

OPENROUTER = llm_provider("openai").presets["openrouter"]
NEBIUS = llm_provider("nebius").presets["nebius"]


def _s(tmp_path: Path, **kw: Any) -> Settings:
    return Settings(_env_file=None, cache_dir=tmp_path, runs_dir=tmp_path / "runs", **kw)


def test_leftover_openrouter_values_give_way_to_the_nebius_preset(tmp_path: Path) -> None:
    # the .env of someone who ran `make use-openrouter`, then set LLM_PROVIDER=nebius and a key
    left = {k.lower(): v for k, v in OPENROUTER.items() if k != "LLM_PROVIDER"}
    s = _s(tmp_path, **left, llm_provider="nebius", nebius_api_key="nb")
    assert s.model_for("fast") == NEBIUS["MODEL_FAST"]
    assert s.model_for("judge") == NEBIUS["MODEL_JUDGE"]
    assert s.llm_extra_body == NEBIUS["LLM_EXTRA_BODY"]
    assert s.model_fallback == ""  # OpenRouter's fallback id is not one Nebius serves


def test_empty_model_ids_take_the_provider_preset(tmp_path: Path) -> None:
    s = _s(tmp_path, llm_provider="nebius", nebius_api_key="nb", model_fast="", model_main="")
    assert (
        s.model_for("fast") == NEBIUS["MODEL_FAST"] and s.model_for("main") == NEBIUS["MODEL_MAIN"]
    )


def test_a_model_id_you_chose_is_kept(tmp_path: Path) -> None:
    s = _s(tmp_path, llm_provider="nebius", nebius_api_key="nb", model_fast="nvidia/my-own-choice")
    assert s.model_for("fast") == "nvidia/my-own-choice"


def test_openrouter_settings_are_untouched(tmp_path: Path) -> None:
    left = {k.lower(): v for k, v in OPENROUTER.items() if k != "LLM_PROVIDER"}
    s = _s(tmp_path, **left, llm_provider="openai", openai_compat_api_key="k")
    assert s.model_for("fast") == OPENROUTER["MODEL_FAST"]


def test_nebius_sandboxes_need_the_project_id(tmp_path: Path) -> None:
    spec = sandbox_provider("nebius")
    missing = {r.env for r in spec.missing(_s(tmp_path, nebius_api_key="nb"))}
    assert missing == {"NEBIUS_PROJECT_ID"}
    assert not spec.missing(_s(tmp_path, nebius_api_key="nb", nebius_project_id="project-e00x"))


def test_the_client_sends_the_key_and_the_project(tmp_path: Path) -> None:
    from api.adapters.nebius_sandbox import NebiusRunner

    s = _s(tmp_path, nebius_api_key="nb-key", nebius_project_id="project-e00x")
    auth = NebiusRunner(s)._get_client()._config.auth
    assert auth.get_headers() == {"Authorization": "Bearer nb-key", "Project": "project-e00x"}


def test_every_sandbox_run_is_started_without_a_network() -> None:
    from api.adapters.nebius_sandbox import network_off

    class Api:
        _client = httpx.AsyncClient(base_url="https://sandboxes.example/")

        def _build_request(self, endpoint_info: Any, data: dict[str, Any]) -> httpx.Request:
            return self._client.build_request("POST", data["path"], json=data["body"])

    api = Api()
    assert network_off(api) is True
    spawn = api._build_request(None, {"path": "/v1/instances", "body": {"command": "python x.py"}})
    assert json.loads(spawn.content) == {"command": "python x.py", "networking": {"enabled": False}}
    other = api._build_request(None, {"path": "/v1/images/import", "body": {"url": "x"}})
    assert json.loads(other.content) == {"url": "x"}
    assert network_off(object()) is False  # an SDK without this seam: the runner must not claim it


def test_a_configured_runner_reports_its_network_off_at_once(tmp_path: Path) -> None:
    from api.adapters.nebius_sandbox import NebiusRunner

    s = _s(tmp_path, nebius_api_key="nb-key", nebius_project_id="project-e00x")
    assert NebiusRunner(s).isolation.network_off is True
