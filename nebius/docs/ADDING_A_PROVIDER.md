# Adding a provider

Showtime uses three external services:

| Service | What it does | Today's providers |
| --- | --- | --- |
| **LLM** | Runs the Nemotron agents | `openai` (OpenRouter and any OpenAI-compatible API), `nebius`, `local`, `fake` |
| **Sandbox** | Runs simulations and AI-written code | `docker`, `nebius`, `fake` |
| **Search** | Finds web evidence | `tavily`, `none` |

Each provider is **one file** in `api/adapters/providers/`. The file describes the provider and
registers it. Settings pick a provider by name (`LLM_PROVIDER`, `SANDBOX_PROVIDER`,
`SEARCH_PROVIDER`), and a typo fails at startup with the list of valid names.

No other code compares provider names. Code asks what a provider *can do*:
- `spec.is_cloud`, `spec.sends_extra_body`, `spec.one_request_at_a_time`;
- `runner.isolation.per_job_limits`, `runner.parallel`;
- `search.live`.

`api/tests/test_provider_registry.py` proves this: it registers a test-only provider of each kind
and selects it with no other file edited.

## What a provider declares (`api/adapters/providers/base.py`)

| Field | For |
| --- | --- |
| `name`, `aliases`, `title` | The setting value, and the plain name shown in the UI ("Nebius Token Factory") |
| `requirements` | Each `.env` variable it needs. A missing one gives a clear "not configured" state in `/api/v1/health`, never a crash |
| `presets` | `.env` values that `make use-<preset>` writes: model ids, prices, request extras (never keys) |
| `check_live` | The smallest real call, used by `make verify-live` |
| LLM only | `is_cloud`, `base_url`, `key`, `key_env`, `spare_key`, `label`, `where`, `sends_extra_body`, `directive_on_every_model`, `one_request_at_a_time`, `health` |
| Sandbox, search | `build(settings)`, which returns the runner or client. A runner states its own `isolation` and `parallel` |

## Example 1: an LLM provider

`api/adapters/providers/llm_acme.py`:

```python
from api.adapters.providers import LLM
from api.adapters.providers.base import LlmProvider, Requirement
from api.adapters.providers.checks import llm_check

LLM.register(
    LlmProvider(
        kind="llm",
        name="acme",
        title="Acme Inference",
        requirements=(Requirement("ACME_API_KEY", "acme_api_key", "your Acme key", secret=True),),
        presets={"acme": {"LLM_PROVIDER": "acme", "MODEL_FAST": "nvidia/nemotron-...", "MODEL_MAIN": "..."}},
        check_live=llm_check,
        is_cloud=True,
        base_url=lambda s: "https://api.acme.example/v1",
        key=lambda s: s.acme_api_key,
        key_env="ACME_API_KEY",
        label=lambda s: "ACME",
        where=lambda s: "Acme Inference",
    )
)
```

Then:
1. Add `acme_api_key: str = ""` to `Settings`.
2. Run `python scripts/env_example.py --write`, which documents `ACME_API_KEY` in `.env.example`.
3. Run `make use-acme`, which writes the preset.
4. Put the key in `.env`.
5. Run `make verify-live`.

## Example 2: a sandbox provider

`api/adapters/providers/sandbox_acme.py`:

```python
from api.adapters.providers import SANDBOX
from api.adapters.providers.base import Requirement, SandboxProvider
from api.adapters.providers.checks import sandbox_check


def _build(s):
    from my_package.acme_runner import AcmeRunner  # implements SandboxRunner (api/adapters/sandbox.py)
    return AcmeRunner(s)


SANDBOX.register(SandboxProvider(
    kind="sandbox", name="acme", title="Acme Sandboxes",
    requirements=(Requirement("ACME_API_KEY", "acme_api_key", "your Acme key", secret=True),),
    check_live=sandbox_check, build=_build,
))
```

The runner must:
- implement `run(job)`, `run_code(job)`, `health()` and `close()`;
- set `provider`, `parallel` (how many runs it takes at once) and `fallback_reason = None`;
- state its `isolation`: `Isolation(kind, network_off, memory, cpus, read_only, process_limit,
  non_root, per_job_limits)`.

The sandbox badge, Help and the AI team page show those facts, and `runner.parallel` decides the
sweep tier and the default seed count. While its key is missing, the app runs on
`SANDBOX_FALLBACK` (Docker) and says so.

## Example 3: a search provider

`api/adapters/providers/search_acme.py`:

```python
from api.adapters.providers import SEARCH
from api.adapters.providers.base import Requirement, SearchProvider
from api.adapters.providers.checks import search_check


def _build(s):
    from my_package.acme_search import AcmeSearch  # live, health(), search(query, ...), extract(urls)
    return AcmeSearch(s.acme_search_key, s.cache_dir / "acme")


SEARCH.register(SearchProvider(
    kind="search", name="acme", title="Acme Search", live=True,
    requirements=(Requirement("ACME_SEARCH_KEY", "acme_search_key", "your key", secret=True),),
    check_live=search_check, build=_build,
))
```

Search results are `SearchHit(title, url, snippet, published)`. Agents may cite only URLs that came
back in hits, or rows of the incident dataset.

## Checks

- `make check`: the registry tests, `test_env_example.py` (no `.env.example` drift), and the
  characterization tests of the existing providers.
- `make verify-live`: one real call per service. It writes `docs/LIVE_STATUS.md`, and a service
  without its key is SKIPPED.
