# Switching on Nebius and Tavily

Today Showtime runs on NVIDIA Nemotron through **OpenRouter** (free tier) and on **local Docker**
sandboxes; web search is off and the red team cites the incident dataset. Three services are
built and tested with fake clients but **have not run live** (no keys):

- Nebius Token Factory (Nemotron in the cloud);
- Nebius Sandboxes;
- Tavily web search.

Each one switches on with `.env` alone, no code edits. Each provider is one module in
`api/adapters/providers/` ([ADDING_A_PROVIDER.md](ADDING_A_PROVIDER.md)). `make verify-live`
shows the state of all of them at any time and writes [LIVE_STATUS.md](LIVE_STATUS.md).
To host the app itself on a Nebius VM, see [HOSTING.md](HOSTING.md).

## 1. Nebius Token Factory

**Why it matters most:** the hackathon requires the project to run on Nebius Token Factory or
Nebius AI Cloud.

### Steps

1. Get an API key from the Token Factory console.
2. In `.env`, set `NEBIUS_API_KEY=...`.
3. Run `make verify-nebius-llm`. It makes one authenticated request and one tiny chat with the
   Nebius preset ids, even while another provider is active.
   - **A pass looks like:** `| llm | Nebius Token Factory | PASS | NEBIUS: ...; nvidia/... answered 'ready' |`.
   - **If it fails,** the row says why:
     - `rejected the API key (HTTP 401)`: the key is wrong.
     - A model error: the model id has changed. Check the
       [catalog](https://tokenfactory.nebius.com/model-catalog.md) and edit the preset in
       `api/data/llm_presets.json` (a data file, not code).
     - `GET /api/v1/health` (`model_warnings`) also names any id the provider does not serve.
4. In `.env`, set `LLM_PROVIDER=nebius`. That is the whole switch: model ids, prices and request
   extras that are empty, or still hold another provider's preset values (for example
   OpenRouter's `:free` ids), take the Nebius preset on their own. Ids you chose yourself are kept
   (`api/core/settings.py`, `_take_provider_preset`; tests in `api/tests/test_env_only_switch.py`).
   `make use-nebius` writes the same values into `.env` if you want to see them there (it keeps
   your keys and backs up `.env` to `.env.bak`).
5. Run `make up` (restart), then `make smoke-nebius`: every model role, a plain and a JSON reply,
   with time, tokens and cost.
6. Run one real test in the app: **Projects › New project › School wing › Create project**, then
   **Standard › Test this plan**. The AI badge should read NEBIUS.

`make use-openrouter` and `make use-local` switch back the same way (`make use-list` lists the
presets).

### The preset

`api/data/llm_presets.json` (edit that file when a model is renamed or retired). Ids and prices
are from the [model catalog](https://tokenfactory.nebius.com/model-catalog.md) and the public model
info (`https://tokenfactory.nebius.com/api/public/models_info`), checked on 2026-10-29. Nemotron 3
Nano and Nemotron 3 Super leave Serverless on 2026-11-09
([deprecations](https://docs.tokenfactory.nebius.com/model-deprecations-november-2026.md)), so the
preset uses the replacements the notice names:

| Role | Agents on this role | Model id | USD per 1M in / out |
| --- | --- | --- | --- |
| fast | red team, what-if planner, router | `nvidia/Nemotron-3_5-Lightning` | 0.06 / 0.24 |
| long | long incident texts | `nvidia/Nemotron-3_5-Lightning` | 0.06 / 0.24 |
| main | brief, designer, editor, blue team, explainer, analyst | `nvidia/Nemotron-3.5-Super-VL` | 0.30 / 0.90 |
| judge | judge, safety officer | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1.00 / 3.00 |

To keep costs lower, set `MODEL_JUDGE` to the Super VL id (and its prices) after switching. Super
VL is listed as an image-to-text model with a text use case; `make smoke-nebius` checks every role
on the first run.

For comparison, the OpenRouter preset (the one that runs live today) uses
`nvidia/nemotron-3.5-lightning:free` for fast, long and fallback, and
`nvidia/nemotron-3-ultra-550b-a55b:free` for main and judge.

**Reasoning:** Nemotron 3 reasons by default (model card: "Reasoning ON (default)"). JSON replies
need it off, so the preset sets `LLM_EXTRA_BODY={"reasoning_effort":"none"}`, the parameter the
Token Factory API reference documents. If a model rejects it, the request is retried without it.

**JSON:** both presets set `LLM_SUPPORTS_JSON_SCHEMA=false`: JSON is asked for in the prompt,
validated with Pydantic, and repaired with one extra call. This is the setup used live on
OpenRouter. With `true`, the adapter sends `response_format` JSON schemas instead.

**Self-healing requests** (`api/adapters/llm.py`): if Token Factory rejects `response_format` or
the extra request fields, the call is retried once without them and the model is remembered; a
reply whose reasoning used up every token is retried once with more room. `make smoke-nebius`
prints what it had to leave out.

**Verified so far:** the base URL answers and rejects a wrong key with 401. Live replies: **not
run live** (no key).

## 2. Nebius Sandboxes

### Steps

1. Request Sandboxes access (the Sandboxes page on tokenfactory.nebius.com). It uses the same
   `NEBIUS_API_KEY`, plus the project that has the access: in `.env`, set `NEBIUS_PROJECT_ID`
   (Token Factory › Project settings, under the project name). It is sent as the `Project` header.
2. Run `make verify-nebius-sandbox`. It checks the token, runs one tiny code job (it must answer
   `{"sum": 2}`) and one network call that must be stopped.
   - **A pass looks like:** `| sandbox | Nebius Sandboxes | PASS | ran a script in ... s; a network call was stopped: ... |`.
   - **If it fails:** `not reachable` means check the access and `NEBIUS_SANDBOX_BASE_URL`.
     "A script reached the network" means the run is **not** safe for AI-written code: keep
     `SANDBOX_PROVIDER=docker` and report it in [FEEDBACK.md](FEEDBACK.md).
3. In `.env`, set `SANDBOX_PROVIDER=nebius` and `SANDBOX_MAX_PARALLEL=4`, then `make up`. The
   sandbox badge should read NEBIUS, with no fallback note.

```dotenv
SANDBOX_PROVIDER=nebius
NEBIUS_API_KEY=...                     # the same Token Factory key
NEBIUS_PROJECT_ID=...                  # Token Factory › Project settings
NEBIUS_SANDBOX_BASE_URL=https://api.tokenfactory.nebius.com/sandboxes
SANDBOX_MAX_PARALLEL=4                 # branches simulated in parallel (Beta limit: 50 at once)
```

Without the project ID the app says what to set and runs on Docker.

### How the runner works

`api/adapters/nebius_sandbox.py` (`NebiusRunner`) uses **contree-sdk 0.3.6**. Verified against the
installed SDK source, not against the live service:

| Step | SDK call (verified in source) |
| --- | --- |
| Client | `Contree(ContreeConfig(auth=IAMAuth(token=NEBIUS_API_KEY, project_id=NEBIUS_PROJECT_ID, base_url=...)))`, with values from settings |
| No network | every spawn (`POST /v1/instances`) carries `{"networking": {"enabled": false}}` (`network_off`), except the setup run below |
| Base image | `await client.images.oci(<FROM of sim/Dockerfile>)`, so the cloud runs the local versions |
| Install deps | `await image.run(shell="pip install ... jupedsim==<pin>", files={...}, disposable=False)` → child image; the only spawn with the network on (install with it on, then run without), within `NEBIUS_SETUP_TIMEOUT_S` |
| Add sim code | `await image.apply_files(files={"/app/...": bytes})` |
| Venue node (tree root) | `apply_files({"/work/venue.json": ...})` |
| Each run | `await parent.run(shell="cd /app && python run_sim.py /work", files=..., disposable=False)` |
| Results | `await image.read("/work/result.json")`, `traj.bin`, `density.bin` |

What the sandboxes run: every crowd simulation, every AI-written scenario script (inside the
simulation), every analysis script the AI or a user writes, and rewind branches. Each run works in
its own folder `/work/<run_id>/`; a rewind branch is a snapshot child of the checkpoint run. The
base image id is cached in `cache/nebius/base_image.json` (keyed by a hash of `sim/`).

**Protection on Nebius is different from Docker:**
- **Network:** outbound network is on by default in Nebius Sandboxes. contree-sdk 0.3.6 has no
  argument for it, so the runner adds `networking.enabled: false` to every spawn request except
  the setup run. If a future SDK removes that seam, the runner logs a warning and reports the
  network as not guaranteed. Step 2's network call proves it live.
- **Memory and CPU** can't be set per run there. The protection instead is the static check
  before a script runs, the same check again inside the sandbox, and the in-sandbox budgets
  (`SCRIPT_*`, `SANDBOX_MEMORY_SHARE`; see [SANDBOX_PROOF.md](SANDBOX_PROOF.md)).
- `make sandbox-proof` attacks the local Docker runner only.

The runner reports this itself: `GET /api/v1/health` › `providers.sandbox.isolation` says
`per_job_limits: false` and `network_off: true`, and the sandbox badge says so on screen.

Tests: `api/tests/test_nebius.py` runs the runner against a fake SDK client (branching, file
transfer, failures). The live test is skipped without `NEBIUS_API_KEY`.

## 3. Tavily web search

1. Get a free key at tavily.com.
2. In `.env`, set `TAVILY_API_KEY=...` (`SEARCH_PROVIDER=tavily` is the default).
3. Run `make verify-tavily`: one search that must come back with a cited result.
   - **A pass looks like:** `| search | Tavily web search | PASS | 2 results, first: ... (https://...) |`.
   - **If it fails:** check the key and its monthly quota. Showtime caches every search under
     `cache/tavily/` and caps calls per session.
4. Run `make up`. In **AI tests it**, the red team's tool calls should include a web search, and
   the **Evidence** panel should show a "Live web (Tavily)" group next to "Incident dataset".

What it does once on: the red team searches (basic depth, up to 5 results) for incidents like the
venue's and may cite only URLs that came back; the evidence desk looks up capacity and guidance
for the brief.

## 4. Check everything

```bash
make verify-live             # all services; writes docs/LIVE_STATUS.md
make verify-nebius-llm       # Token Factory: one authenticated request, one tiny chat
make verify-nebius-sandbox   # Sandboxes: one tiny script, one network call that must be stopped
make verify-tavily           # Tavily: one search with a cited result
make smoke-nebius            # health, one Tier 2 run in a sandbox, one agent call
```

Without a key each prints SKIPPED and exits cleanly, never a fake pass. With
`SANDBOX_PROVIDER=nebius` and no key, the app runs on `SANDBOX_FALLBACK` (Docker) and the sandbox
badge says so.

## 5. After a live pass, update

- [FEEDBACK.md](FEEDBACK.md): the service's section (what worked, errors, time to first answer).
- [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md): say "Nebius Token Factory" or "Nebius Sandbox" in the
  voice-over only now.
- The status lines in [README](../README.md), [PITCH.md](PITCH.md), [JUDGE_GUIDE.md](JUDGE_GUIDE.md)
  and the table below.

## Status (2026-10-29)

| Item | Status |
| --- | --- |
| LLM adapter (OpenAI-compatible) | Live on OpenRouter: Nemotron 3 Ultra and 3.5 Lightning (results logged up to 2026-10-19 used Nemotron 3 Super, whose free endpoint later returned 404). Token Factory: **not run live** (no key) |
| Model ids and prices | Nebius preset from the public model info, checked 2026-10-29 |
| Sandboxes runner | Built against the SDK source, fake-client tests; **not run live** (no access) |
| Tavily | Built, cached, capped, fake-client tests; **not run live** (no key) |
| Parallel branches | `SANDBOX_MAX_PARALLEL` semaphore; local default 1 |

If you get none of the keys, everything works as it does today, and the UI says what is off: the
AI badge, the sandbox badge (with a fallback note if `SANDBOX_PROVIDER` names one without a key),
and "Web search: off" in the evidence views.
