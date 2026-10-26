# When you get the keys

Today Showtime runs on **OpenRouter** (free Nemotron models) and **local Docker** sandboxes, and web
search is off (the red team uses the incident dataset).

Three services are built and tested with fake clients, but **have not been run live**:
- Nebius Token Factory;
- Nebius Sandboxes;
- Tavily.

Each one switches on with `.env` alone, with no code edits.

`make verify-live` shows the state of all of them at any time, and writes `docs/LIVE_STATUS.md`.

---

## 1. Nebius Token Factory (Nemotron in the cloud)

**Why it matters most:** the hackathon requires the project to run on Nebius Token Factory or AI
Cloud (requirement R1).

1. Get an API key from the Token Factory console.
2. In `.env`, set `NEBIUS_API_KEY=...`.
3. Run `make verify-nebius-llm`. This makes one authenticated request and one tiny chat, using the
   Nebius preset model ids, even while another provider is active.
   - **A pass looks like:** `| llm | Nebius Token Factory | PASS | NEBIUS: ...; nvidia/... answered 'ready' |`.
   - **If it fails:** the row says why.
     - `rejected the API key (HTTP 401)` → the key is wrong.
     - A model error → the model id has changed. Check the
       [catalog](https://tokenfactory.nebius.com/model-catalog.md) and edit the preset in
       `api/adapters/providers/llm_nebius.py`.
     - A warning in `/api/v1/health` (`model_warnings`) also names any id the provider does not
       serve.
4. In `.env`, set `LLM_PROVIDER=nebius`. That is the whole switch:
   - Model ids, prices and request extras that are empty, or still hold another provider's
     preset values (for example OpenRouter's `:free` ids), take the Nebius preset on their own.
   - Ids you chose yourself are kept.
   - The preset ids are the ones in Nebius's public model info:
     `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3_5-Lightning`,
     `nvidia/nemotron-3-super-120b-a12b` and `nvidia/Nemotron-3-Ultra-550b-a55b`.
   - If you'd rather see the values in `.env`, `make use-nebius` writes them (it keeps your keys
     and backs up `.env` to `.env.bak`).
5. Run `make up` (restart), then `make smoke-nebius` (every model role, plain and JSON, with time,
   tokens and cost).
6. Run one real test in the app: open "Sandbox demo: school wing", then "Test this plan" (Standard).
   The AI badge should read NEBIUS.

**Then update:**
- `docs/FEEDBACK.md`, Token Factory section: what worked, errors, time to the first answer.
- `docs/VIDEO_SCRIPT.md`: the evidence table, and say "Nebius Token Factory" in the voice-over only
  now.
- `README.md` and `docs/PITCH.md`: the provider status line.
- `docs/NEBIUS_SWITCH.md`: Status table.

## 2. Nebius Sandboxes

1. Request Sandboxes access (the Sandboxes page on tokenfactory.nebius.com). It uses the same
   `NEBIUS_API_KEY`, plus the project that has the access: in `.env`, set `NEBIUS_PROJECT_ID`
   (Token Factory › Project settings, under the project name). The SDK sends it as the
   `Project` header.
2. Run `make verify-nebius-sandbox`. It checks the token, runs one tiny code job (it must answer
   `{"sum": 2}`), and runs one network call that must be stopped.
   - **A pass looks like:** `| sandbox | Nebius Sandboxes | PASS | ran a script in ... s; a network call was stopped: ... |`.
   - **If it fails:**
     - `not reachable` → check the access and `NEBIUS_SANDBOX_BASE_URL`.
     - "a script reached the network" → the run is **not** safe for AI-written code. Keep
       `SANDBOX_PROVIDER=docker` and report it in FEEDBACK.md.
3. In `.env`, set `SANDBOX_PROVIDER=nebius` and `SANDBOX_MAX_PARALLEL=4`, then `make up`. The
   sandbox badge should read NEBIUS, with no fallback note.
4. Nebius sandboxes have outbound network **on** by default. Showtime starts every run with it
   off (`networking.enabled = false` in the spawn request), and step 2's network call proves
   it.
   - Memory and CPU can't be set per run there; the static check and the in-sandbox budgets
     protect instead.
   - `make sandbox-proof` attacks the local Docker runner only.

**Then update:**
- FEEDBACK.md, Sandboxes section.
- VIDEO_SCRIPT.md: say "Nebius Sandbox" only now.
- NEBIUS_SWITCH.md Status.
- The README provider status line.

## 3. Tavily web search

1. Get a free key at tavily.com.
2. In `.env`, set `TAVILY_API_KEY=...`. `SEARCH_PROVIDER=tavily` is the default.
3. Run `make verify-tavily`: one search that must come back with a cited result.
   - **A pass looks like:** `| search | Tavily web search | PASS | 2 results, first: ... (https://...) |`.
   - **If it fails:** an empty result or an error → check the key and its monthly quota (the free
     tier is limited; Showtime caches every search under `cache/tavily/` and caps calls per
     session with `TAVILY_MAX_CALLS`).
4. Run `make up`. In AI at work, the red team's tool calls should include a web search, and the
   Evidence panel should show a "Live web (Tavily)" group next to "Incident dataset".

**Then update:**
- FEEDBACK.md, Tavily section.
- VIDEO_SCRIPT.md: the evidence beat.
- The README provider status line.

---

## If you get none of the keys

Everything works as it does today. The UI says what is off:
- the AI badge;
- the sandbox badge, which shows a fallback note if `SANDBOX_PROVIDER` names one without a key;
- "Web search: off" in the evidence views.

Nothing claims a live Nebius or Tavily result.
