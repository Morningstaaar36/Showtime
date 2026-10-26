# Switching to Nebius (Token Factory + Sandboxes)

Showtime runs on OpenRouter's free Nemotron models with local Docker sandboxes today, or fully
locally (Nemotron Nano 9B v2 on your GPU). Switching to Nebius is an `.env` change only; no code
changes. Each provider is one module in `api/adapters/providers/` (docs/ADDING_A_PROVIDER.md);
`make verify-live` checks them all, and docs/WHEN_YOU_GET_THE_KEYS.md is the checklist.

## 1. Token Factory (Nemotron in the cloud)

Only `.env` changes:

```dotenv
LLM_PROVIDER=nebius
NEBIUS_API_KEY=...
```

Leftover values are replaced automatically. Model ids, prices and request extras that are empty
(no `MODEL_FAST`), or that still hold another provider's preset values (for example OpenRouter's
`:free` ids from `make use-openrouter`), take the Nebius preset below. Ids you chose yourself are
kept (`api/core/settings.py`, `_take_provider_preset`; tests in `api/tests/test_env_only_switch.py`).
`make use-nebius` writes the same values into `.env`, if you want to see them there.

```bash
make verify-nebius-llm   # one authenticated request and one tiny chat (PASS / FAIL / SKIPPED)
make smoke-nebius        # every model role: a plain and a JSON reply, with time, tokens and cost
make up                  # restart the app (or: make dev-down && make dev)
```

`make use-openrouter` and `make use-local` switch back the same way (`make use-list` lists the
presets the providers declare).

The Nebius preset. The ids and prices are from the
[model catalog](https://tokenfactory.nebius.com/model-catalog.md), and the ids were checked
against the public model info (`https://tokenfactory.nebius.com/api/public/models_info`) on
2026-10-26:

| Role | Used for | Model id | USD per 1M in / out |
| --- | --- | --- | --- |
| fast | red team drafts, routing, classification | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 0.06 / 0.24 |
| long | long incident texts | `nvidia/Nemotron-3_5-Lightning` | 0.06 / 0.24 |
| main | venue edits, blue team, explainer | `nvidia/nemotron-3-super-120b-a12b` | 0.30 / 0.90 |
| judge | final judgement | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1.00 / 3.00 |

To keep costs lower, set `MODEL_JUDGE` to the Super id (and its prices) after switching.

**Reasoning:** Nemotron 3 reasons by default (model card: "Reasoning ON (default)"). JSON replies
need it off, so the preset sets `LLM_EXTRA_BODY={"chat_template_kwargs":{"enable_thinking":false}}`.

**JSON:** the preset asks for JSON in the prompt and validates it with Pydantic, with one repair
call (`LLM_SUPPORTS_JSON_SCHEMA=false`, the setup proven live on OpenRouter with Nemotron 3 Super).
With `true` the adapter sends `response_format` JSON schemas.

**Self-healing requests** (`api/adapters/llm.py`): if Token Factory rejects `response_format`
(models without the "JSON mode" tag) or the extra request fields, the call is retried once without
them and the model is remembered; a reply whose reasoning used up every token is retried once with
more room. `make smoke-nebius` prints what it had to leave out.

*Status: base URL verified (the endpoint answers and rejects a wrong key with 401). Live replies:
**not run live** (no key).*

## 2. Sandboxes (simulations in Nebius)

```dotenv
SANDBOX_PROVIDER=nebius
NEBIUS_API_KEY=...                     # the same Token Factory key
NEBIUS_PROJECT_ID=...                  # Token Factory › Project settings (sent as the Project header)
NEBIUS_SANDBOX_BASE_URL=https://api.tokenfactory.nebius.com/sandboxes
SANDBOX_MAX_PARALLEL=4                 # branches simulated in parallel (Beta limit: 50 at once)
```

The Sandboxes docs ("Set up access") require the project ID alongside the key. Without it, the
app says what to set and runs on Docker.

`api/adapters/nebius_sandbox.py` (`NebiusRunner`) uses **contree-sdk 0.3.6**. Verified against
the installed SDK source (not against the live service):

| Step | SDK call (verified in source) |
| --- | --- |
| Client | `Contree(ContreeConfig(auth=IAMAuth(token=NEBIUS_API_KEY, project_id=NEBIUS_PROJECT_ID, base_url=...)))`, with values from settings, so no exported environment is needed |
| No network | every spawn (`POST /v1/instances`) carries `{"networking": {"enabled": false}}` (`network_off`) |
| Base image | `await client.images.oci("python:3.12-slim")` |
| Install deps | `await image.run(shell="pip install ...", files={...}, disposable=False)` → child image |
| Add sim code | `await image.apply_files(files={"/app/...": bytes})` |
| Venue node (tree root) | `apply_files({"/work/venue.json": ...})` |
| Each run | `await parent.run(shell="cd /app && python run_sim.py /work", files=..., disposable=False)` |
| Results | `await image.read("/work/result.json")`, `traj.bin`, `density.bin` |

What the sandboxes run: every crowd simulation, every AI-written scenario script (inside the
simulation), every analysis script the AI or a user writes (`run_code` jobs), and rewind
branches. Each run works in its own folder `/work/<run_id>/`, so a branch never sees its parent's
results; a rewind branch is a snapshot child of the checkpoint run and starts from its
`checkpoint.json`. Attacks and fixes of a round run in parallel up to `SANDBOX_MAX_PARALLEL`.
**Protection on Nebius is different.**
- **Network:** outbound network is on by default in Nebius Sandboxes (Sandboxes docs: "Configure
  networking and secrets"). The REST spawn request turns it off with `networking.enabled`.
  contree-sdk 0.3.6 has no argument for it, so the runner adds the field to every spawn request
  (`network_off` in `api/adapters/nebius_sandbox.py`). If a future SDK removes that seam, the
  runner logs a warning and reports the network as not guaranteed. `make verify-nebius-sandbox`
  proves it live with a network call that must fail.
- **Memory and CPU:** these can't be set per run there. The protection instead is:
- the static check before a script runs;
- the same check run again inside the sandbox;
- the in-sandbox budgets (`SCRIPT_*`, `SANDBOX_MEMORY_SHARE`; see `docs/SANDBOX_PROOF.md`).

The runner reports this itself: `GET /api/v1/health` → `providers.sandbox.isolation` says
`per_job_limits: false`, and `network_off: true` once the client is built with the network
switch. The sandbox badge says so on screen. How many
runs it takes at once (`SANDBOX_MAX_PARALLEL`) is the runner's `parallel` capacity, which decides
the sweep tier and the default seed count; no code checks the provider's name.

The base image id is cached in `cache/nebius/base_image.json` (keyed by a hash of `sim/`).
Each run is a child snapshot of the venue node, so branches are real sandbox snapshots.

Tests: `api/tests/test_nebius.py` runs the runner against a fake SDK client (branching, file
transfer, failures). The live test is skipped without `NEBIUS_API_KEY`.

## 3. Check it

```bash
make verify-nebius-llm       # Token Factory: one authenticated request, one tiny chat
make verify-nebius-sandbox   # Sandboxes: one tiny script, one network call that must be stopped
make smoke-nebius            # health, one Tier 2 run in a sandbox, one agent call
```

Without `NEBIUS_API_KEY` each prints SKIPPED and exits cleanly; with `SANDBOX_PROVIDER=nebius` and
no key the app runs on `SANDBOX_FALLBACK` (Docker) and the sandbox badge says so.

## Status

| Item | Status |
| --- | --- |
| LLM adapter (OpenAI-compatible) | Live on OpenRouter (Nemotron 3 Ultra and 3.5 Lightning); Token Factory: **not run live** (no key) |
| Model ids and prices | From the public model catalog (2026-10-14); `make use-nebius` |
| Sandboxes runner | Built against SDK source + fake-client tests; **not run live** (no access) |
| Parallel branches | `SANDBOX_MAX_PARALLEL` semaphore; local default 1 |
