# Providers and keys

Showtime talks to three outside services: an AI model, a sandbox that runs simulations, and
(optionally) web search. Each one is picked in `.env`, with no code edits. Each provider is one
module in `api/adapters/providers/` ([ADDING_A_PROVIDER.md](ADDING_A_PROVIDER.md)).

## What runs today

| Service | Provider | Setting |
| --- | --- | --- |
| AI | NVIDIA Nemotron through **OpenRouter** (free models), or any other OpenAI-compatible API | `LLM_PROVIDER=openai` |
| AI | Nemotron Nano 9B v2 on a **local llama.cpp server** (`make llm-up`) | `LLM_PROVIDER=local` |
| Sandbox | **Local Docker**: every simulation and every AI-written script runs in a locked container | `SANDBOX_PROVIDER=docker` |
| Web search | **Tavily** (optional). Without a key, search is off and the red team cites the incident dataset | `TAVILY_API_KEY` |

Tests use fake providers (`fake` for the AI, the sandbox and search). With no AI key at all the
app still works: tests use rule-based attacks and fixes, and the AI badge says Offline.

## Where each key goes

All keys go in `.env` in the project folder (`make setup` copies `.env.example` to it). `.env`
is gitignored; keys stay on the server and never reach the browser. Every other setting, with
its default, is in `.env.reference`.

| You want | Put in `.env` |
| --- | --- |
| OpenRouter | `OPENAI_COMPAT_API_KEY=...` (a free key from openrouter.ai). `OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1` is already set |
| Spare OpenRouter keys | `OPENAI_COMPAT_API_KEY_FALLBACK=key2,key3`: each is used in turn once the one before is out of credit, rate limited or expired |
| Another OpenAI-compatible API | `OPENAI_COMPAT_BASE_URL=...`, `OPENAI_COMPAT_API_KEY=...`, the `MODEL_*` ids it serves, and `OPENAI_COMPAT_LABEL=...` (the name on the AI badge) |
| The local model | No key. `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL` (defaults work with `make llm-up`) |
| Docker sandbox | No key. Docker must be running, and `make build-sim` (or `make up`) builds the image |
| Tavily | `TAVILY_API_KEY=...` |

## Switch the AI

```bash
make use-openrouter    # LLM_PROVIDER=openai with OpenRouter's free Nemotron models
make use-local         # LLM_PROVIDER=local (start the model with make llm-up)
make use-list          # every preset
```

`make use-<preset>` rewrites only the provider lines (provider, model ids, prices, request
extras), keeps every key and other setting, and saves the old file as `.env.bak`. Restart after:
`make up` (Docker) or `make dev-down && make dev`.

You can also set `LLM_PROVIDER` and the `OPENAI_COMPAT_*` lines by hand. The presets live in
`api/data/llm_presets.json` (a data file: edit it, not the code, when a model is renamed or
retired). A `MODEL_*` id, price or request extra that is empty, or still holds another preset's
value, takes the active provider's preset on its own. An id you chose yourself is kept
(`api/core/settings.py`, `_take_provider_preset`; tests in `api/tests/test_env_only_switch.py`).

### The OpenRouter preset

| Role | Agents on this role | Model id |
| --- | --- | --- |
| fast | red team, what-if planner, router | `nvidia/nemotron-3.5-lightning:free` |
| long | long incident texts | `nvidia/nemotron-3.5-lightning:free` |
| main | brief, designer, editor, blue team, explainer, analyst | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| judge | judge, safety officer | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| vision | plan critic: reads the drawn floor plans in each design round (`MODEL_VISION`; empty turns it off) | `nvidia/nemotron-3.5-super-vl:free` |
| fallback | tried when a role's model fails at the provider | `nvidia/nemotron-3.5-lightning:free` |

`GET /api/v1/health` (`model_warnings`) names any id the provider does not serve.

**Reasoning off:** Nemotron 3 reasons by default, and JSON replies need it off. The preset sets
`LLM_EXTRA_BODY={"reasoning":{"enabled":false}}`, else a reasoning model can spend its whole reply
length thinking and return nothing.

**JSON:** the preset sets `LLM_SUPPORTS_JSON_SCHEMA=false`: JSON is asked for in the prompt,
validated with Pydantic, and repaired with one extra call. With `true`, the adapter sends
`response_format` JSON schemas instead (the local llama.cpp server uses this).

**Self-healing requests** (`api/adapters/llm.py`): if a provider rejects `response_format` or
the extra request fields, the call is retried once without them and the model is remembered. A
reply whose reasoning used up every token is retried once with more room.

## Tavily web search

1. Get a free key at tavily.com.
2. In `.env`, set `TAVILY_API_KEY=...` (`SEARCH_PROVIDER=tavily` is the default).
3. Run `make verify-tavily`: one search that must come back with a cited result.
   - **A pass looks like:** `| search | Tavily web search | PASS | 2 results, first: ... (https://...) |`.
   - **If it fails:** check the key and its monthly quota. Showtime caches every search under
     `cache/tavily/` and caps calls per session (`TAVILY_MAX_CALLS`).
4. Restart (`make up`). In **AI tests it**, the red team's tool calls should include a web search,
   and the **Evidence** panel should show a "Live web (Tavily)" group next to "Incident dataset".

What it does once on: the red team searches (basic depth, up to 5 results) for incidents like the
venue's and may cite only URLs that came back; the evidence desk looks up capacity and guidance
for the brief.

## Check what is live

```bash
make verify-live      # the active AI, sandbox and search, plus Tavily; writes docs/LIVE_STATUS.md
make verify-tavily    # Tavily only: one search with a cited result
```

Each check makes the smallest real call to the service and prints a pass/fail table.
[LIVE_STATUS.md](LIVE_STATUS.md) keeps the latest result of each, with the date and the model
ids. Keys are never printed or written.

**SKIPPED** means the service has no key (or other required setting) in `.env`. The row says
what to set. It is never a fake pass, and the command still exits cleanly. It fails (exit 1)
only when a service that is set up does not answer.

If a key is missing, the app says so instead of crashing: the AI badge, the sandbox badge, and
"Web search: off" in the evidence views.

## Add another provider

One new module in `api/adapters/providers/`, no other code edits:
[ADDING_A_PROVIDER.md](ADDING_A_PROVIDER.md).
