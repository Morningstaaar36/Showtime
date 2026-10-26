# Feedback on the services we used

Written from what we actually ran while building Showtime, with the five headings from the
hackathon's "How to build a winning project" update for each service. Live use is marked **live**.
A service we only built against, from its docs and SDK, is marked **not tried live**. Numbers come
from our logs (`docs/BUILD_LOG.md`, `docs/LIVE_STATUS.md`, `logs/design_probe_*.log`).

## NVIDIA Nemotron on OpenRouter (live)

Models: `nvidia/nemotron-3.5-lightning:free` (fast, long and fallback roles) and
`nvidia/nemotron-3-ultra-550b-a55b:free` (main and judge roles).

**1. What we used it for.** Twelve agents. Among them, the **Designer** turns one sentence into a
venue spec that a solver builds and checks. The **Red team** writes attacks, including small
Python scenario scripts that run in the sandbox. The **Blue team** proposes fixes, the **Judge**
writes the verdict, and the **Analyst** writes analysis code that runs in the sandbox on the
simulation data. Every reply is JSON validated with Pydantic, repaired once, and number-checked.

**2. What worked well.**
- **Designer fidelity:** on 8 different descriptions (convocation hall, concert, mall, pandal,
  airport concourse, mosque, metro station, street market), every layout built cleanly, and
  32 of 32 requested features were present. That is one live run per prompt, 14 calls in all.
- **Time per designer call:** median 10 s, from 4 s to 42 s over 13 calls.
- **Ultra's red-team ideas were specific to the venue** and cited the incident rows we gave it.
  It also wrote valid scenario scripts against our small script API.
- The same OpenAI-compatible adapter serves OpenRouter, Nebius and a local llama-server: only the
  base URL, the key and the model ids change.

**3. What needs work.**
- **Free daily quota.** The free tier is about 50 requests a day per account, and a full test uses
  4–8 of them. Today the quota ran out on every key we had, with
  `429 Rate limit exceeded: free-models-per-day`. We now pause the hosted model until midnight
  UTC, switch to a spare key, then to the local model. The badge says which one is in use.
- **Nemotron 3 Super's free endpoint returned 404** during our tests, so the main role runs on
  Ultra.
- **Reasoning can use up the reply.** With reasoning on, a reply sometimes came back with no
  answer, all tokens spent on reasoning. We retry once with 4,096 tokens.
- **Some request fields are rejected.** `response_format` with a JSON schema, and extra fields
  such as `chat_template_kwargs`, are refused by some hosted models. We drop the field, ask for
  JSON in the prompt, and remember this per model.
- **Instruction following that we had to enforce in code:**
  - the designer ignored a stated headcount (1,500 asked for, 2,800 built);
  - it flattened a crowd on an upper floor onto the street;
  - it dropped the crowds standing in an alley;
  - the red team copied its target's name as an attack title, and once copied an example title
    from our repair message.

  Each one is now a check that sends the reply back once with the exact problem.

**4. Onboarding: zero to hello world.** We made an OpenRouter account, created a key, set three
`.env` values (base URL, key, model ids), and the first chat answered. We did not time it. The
slow part was finding which free Nemotron ids actually answer (Super did not).
`make verify-live` now does that check in one command.

**5. Would we build with it again?** Yes. Ultra's judgement and Lightning's speed suit the
split between "decide" and "draft". With paid credit or Token Factory, the daily quota would stop
being the limit on testing.

## NVIDIA Nemotron Nano 9B v2 (local, GGUF Q4_K_M on llama.cpp; live in earlier milestones)

**1. What we used it for.** The local provider for development, and the automatic fallback when
the hosted model is paused.

**2. What worked well.** It runs on a 16 GB consumer GPU (about 6.4 GB VRAM at 8k context). The
`/no_think` and `/think` switches work as documented. With grammar-constrained JSON
(llama-server `response_format: json_schema`) it got 10 of 10 scripted venue edits right, and 12 of 12 after we added two more phrasings.

**3. What needs work.**
- With a discriminated union (a list of edit operations), it chose the wrong operation when the
  tag field was optional and listed last in the schema. Making the tag the first, required
  property raised accuracy from 6/10 to 10/10. Worth a line in the model card.
- llama.cpp memory-maps the model by default, which counted about 4.4 GB of resident RAM on a
  14 GB machine. `--load-mode dio` and a small `--cache-ram` fixed it.
- It sometimes paraphrases a computed number ("about 300 s"). Our number check regenerates once.

**4. Onboarding.** Download the GGUF, start `llama-server` with `--jinja`, and the first JSON reply
came back the same hour.

**5. Again?** Yes, as the offline and fallback model.

## Docker as the sandbox (live)

**1. What we used it for.** Every simulation, every AI-written scenario script and every analysis
script runs in a throwaway `showtime-sim` container. The flags are:
- `--network=none` and `--read-only`;
- `--cap-drop=ALL` and `no-new-privileges`;
- `--pids-limit`, plus memory and CPU caps;
- a non-root user and no keys.

**2. What worked well.** Our attack suite (`make sandbox-proof`) throws 14 attacks at it, and each
one is stopped or contained:
- network: `Errno 101 Network is unreachable`;
- writing files: `Errno 30 Read-only file system`;
- endless loops: stopped at 5 s;
- an 8 GB allocation: `MemoryError`;
- a fork bomb: `Errno 11`.

A container starts and runs a tiny script in 0.31 s.

**3. What needs work.**
- **Memory limits in two steps.** A `--memory` limit alone let an 8 GB allocation OOM-kill the
  whole simulation. We added a process limit (`RLIMIT_DATA`), but setting it at startup broke
  JuPedSim's shared library load with `failed to map segment`. It now applies just before
  untrusted code runs, relative to the memory already in use.
- **Root-owned files and the socket group.** Files written by containers came back root-owned,
  and running Compose without `DOCKER_GID` lost access to the Docker socket. The API's
  entrypoint now drops to the owner of `runs/` plus the socket's group.

**4. Onboarding.** Well known. The sandbox image build is the slow step.

**5. Again?** Yes, locally. For parallel branches from a saved crowd state, we built the Nebius
Sandboxes runner (below).

## Nebius Token Factory (not tried live)

**1. What we used it for.** A provider plug-in (`api/adapters/providers/llm_nebius.py`) with preset
model ids and prices. `LLM_PROVIDER=nebius` plus the key selects them, and
`make verify-nebius-llm` makes one authenticated request and one tiny chat. It is tested with fake clients only: we had no key.

**2. What worked well.** Not tried live. Because the API is OpenAI-compatible, no
provider-specific code was needed beyond the preset.

**3. What needs work** (from building against the docs).
- The public model info (`/api/public/models_info`) gives exact ids and tags but no prices.
  Prices are only in the catalog page, so a cost meter has to copy them by hand. Prices in that
  JSON would fix it.
- The catalog shows `Nemotron-3\_5-Lightning` with an escaped underscore, so the id is easy to
  copy wrong (it is `nvidia/Nemotron-3_5-Lightning`).
- Which models support JSON schema output is only a "JSON mode" tag on the model card; none of
  the Nemotron entries in the model info carries it.

**4. Onboarding.** Not tried live.

**5. Again?** We would switch the moment we have a key. The switch is `.env` plus one command.

## Nebius Sandboxes (contree-sdk; not tried live)

**1. What we used it for.** A sandbox plug-in (`SANDBOX_PROVIDER=nebius`). Each scenario is a child
snapshot of the venue image (base → venue → attack → fix), and the branches run in parallel.
`make verify-nebius-sandbox` checks the token, runs one code job and one network call that must
be stopped. It is tested with a fake client only: we had no access.

**2. What worked well.** Not tried live. The image-as-snapshot model maps directly onto red-team
branching: our branch tree is that snapshot tree.

**3. What needs work** (from building against the SDK).
- **Outbound network is on by default**, and contree-sdk 0.3.6 (the latest release) has no
  argument to turn it off. The REST spawn request has `networking.enabled`, so our runner adds
  `{"networking": {"enabled": false}}` to each spawn request through a private seam. For
  AI-written code this matters most: we'd ask for `run(..., network=False)` in the SDK, and for
  off as the default.
- **The project ID is easy to miss.** The SDK sends a `Project` header from `NEBIUS_PROJECT_ID`.
  `Contree(base_url=..., token=...)` accepts no project argument, and if the variable isn't
  exported, the header holds the variable's name. We found this only by reading `auth.py`. A
  `project_id=` argument, or a clear error, would save people a failed first run.
- We confirmed the other calls against the SDK source: `images.oci`,
  `image.run(shell=..., files=..., disposable=False)` and `image.read(path)`.
- Memory and CPU can't be set per run, so our static check and the in-sandbox budgets protect
  there.
- Access is gated (beta).

**4. Onboarding.** Not tried live: no access.

**5. Again?** Yes, for parallel what-ifs from one saved crowd state.

## Nebius AI Cloud (not tried)

We did not use a VM.

## Tavily (not tried live)

**1. What we used it for.** A search plug-in that the agents use:
- The **red team** searches for incidents like the venue's, and may cite only URLs that came back.
- The **evidence desk** looks up capacity and guidance for the brief.

Every source is labelled with its origin (live web or incident dataset), cached, and capped per
session. It is tested with a fake client only: we had no key.

**2. What worked well.** Not tried live. Without a key, the app says "Web search is off (add a
Tavily key to switch on)" and cites the incident dataset instead.

**3. What needs work.** Not tried live.

**4. Onboarding.** Not tried live. `make verify-tavily` will run one search that must come back
with a cited result.

**5. Again?** Yes. It is the missing piece for current, cited evidence on every attack.
