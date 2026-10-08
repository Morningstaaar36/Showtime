# Switching to Nebius (Token Factory + Sandboxes)

Showtime runs fully locally by default (Nemotron Nano 9B v2 on your GPU, JuPedSim in Docker).
Switching to Nebius is an `.env` change only; no code changes.

## 1. Token Factory (Nemotron in the cloud)

```dotenv
LLM_PROVIDER=nebius
NEBIUS_API_KEY=...                     # from the Token Factory console
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
MODEL_FAST=<Nemotron Nano / Lightning id>   # red team, rules, marshals
MODEL_LONG=<long-context id>                # long incident texts
MODEL_MAIN=<Nemotron Super id>              # venue edits, blue team, explainer
MODEL_JUDGE=<Nemotron Ultra id>             # final judgement
PRICE_<ROLE>_IN / PRICE_<ROLE>_OUT     # USD per 1M tokens, for the cost meter
```

Copy the exact model ids from the console or https://tokenfactory.nebius.com/model-catalog.md.
The adapter (`api/adapters/llm.py`) uses the OpenAI-compatible endpoint, sends JSON schemas via
`response_format`, validates every reply with Pydantic, makes one repair call on invalid output,
reads `usage` for tokens and computes cost from the prices above.

**Reasoning control:** the local model uses `/think` and `/no_think` (Nemotron Nano 9B v2 model
card). Nemotron 3 models may use a different switch; if replies contain reasoning text, set
`LLM_REASONING=false` and check the model card. *Status: untested (no key during development).*

## 2. Sandboxes (simulations in Nebius)

```dotenv
SANDBOX_PROVIDER=nebius
NEBIUS_SANDBOX_BASE_URL=https://api.tokenfactory.nebius.com/sandboxes
SANDBOX_MAX_PARALLEL=4                 # branches simulated in parallel
```

`api/adapters/nebius_sandbox.py` (`NebiusRunner`) uses **contree-sdk 0.3.6**. Verified against
the installed SDK source (not against the live service):

| Step | SDK call (verified in source) |
| --- | --- |
| Client | `Contree(base_url=..., token=NEBIUS_API_KEY)` |
| Base image | `await client.images.oci("python:3.12-slim")` |
| Install deps | `await image.run(shell="pip install ...", files={...}, disposable=False)` → child image |
| Add sim code | `await image.apply_files(files={"/app/...": bytes})` |
| Venue node (tree root) | `apply_files({"/work/venue.json": ...})` |
| Each run | `await parent.run(shell="cd /app && python run_sim.py /work", files=..., disposable=False)` |
| Results | `await image.read("/work/result.json")`, `traj.bin`, `density.bin` |

The base image id is cached in `cache/nebius/base_image.json` (keyed by a hash of `sim/`).
Each run is a child snapshot of the venue node, so branches are real sandbox snapshots.

Tests: `api/tests/test_nebius.py` runs the runner against a fake SDK client (branching, file
transfer, failures). The live test is skipped without `NEBIUS_API_KEY`.

## 3. Check it

```bash
make smoke-nebius     # health, one Tier 2 run in a sandbox, one agent call; skips without a key
```

## Status

| Item | Status |
| --- | --- |
| LLM adapter (OpenAI-compatible) | Works locally with llama.cpp; Token Factory: untested (no key) |
| Model ids and prices | Must be copied from the console |
| Sandboxes runner | Built against SDK source + fake-client tests; live: untested (no access) |
| Parallel branches | `SANDBOX_MAX_PARALLEL` semaphore; local default 1 |
