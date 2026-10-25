# Build log (session of 2026-10-25)

One entry per step: what changed, the micro-tests and their real output (trimmed), the result.
Live calls are counted. Values from `.env` are never printed; only names and whether they are set.

## Before Step 1: live browser check (branch `fix/live-browser-check`, merged into this branch)

The UI was crawled in headless Chromium (Playwright): 146 page views over 8 app pages plus 5 projects ×
13 views, at 1440×900 and 390×844. No page errors, no horizontal overflow and no broken images.
Two new venues were built and tested live through the UI:

| Journey | What happened | Live calls (approx.) |
| --- | --- | --- |
| "Plan it for me": market in a two-level car park, 1,500 people | built, simulated, 4 attacks, 1 fix kept, confirmed by full simulations, ~6 min. **Bug: venue held 2,800 people** | ~25 |
| "Just draw my venue": 5-storey mall, 300 per floor, atrium, 2 stair cores, Quick mode | built in 10 s exactly as described; Quick test in ~2 min; tabs, report, expert views | ~10 |
| Same market again after the fix | 1,500 people (750 per level), ramp kept as a 4 m way down; 0 console errors, 0 failed requests | ~25 |
| Ask "why is the upper level the worst?" | analyst code ran in the Docker sandbox in 0.9 s; numbers checked | 2 |

Sandboxes checked while running: one `showtime-sim-r_…` container per run, `--network none`, read-only
root, `cap-drop ALL`, `no-new-privileges`, pids 256, 2 GiB memory, user 1000:1000, and no API keys
among its environment variables.

Fixed and committed (4 commits): designer headcount (prompt v8), red-team titles that repeat their
target, autopilot confirm wording, and web honesty fixes (verdict badge, quick-simulation verdict,
"N still inside", floor chart end, 404s for estimates and old runs, floor chips wrap).

## Step 1: baseline (branch `feat/sandbox-core`)

`.env` (names and shapes only):
- `LLM_PROVIDER=openai` with an OpenRouter base URL.
- `SANDBOX_PROVIDER=docker`.
- `MODEL_FAST` / `MODEL_LONG` = `nvidia/nemotron-3.5-lightning:free`.
- `MODEL_MAIN` / `MODEL_JUDGE` = `nvidia/nemotron-3-ultra-550b-a55b:free`.
- `MODEL_FALLBACK` = lightning.
- Primary and spare OpenRouter keys set; `TAVILY_API_KEY` empty; `NEBIUS_API_KEY` empty.

| Check | Result |
| --- | --- |
| `make check` (ruff, mypy --strict 59 files, import-linter 3 contracts, pytest not slow) | 744 passed, 1 skipped, 4 deselected |
| web `tsc -b` | exit 0 |
| web `eslint . --max-warnings=0` | exit 0 |
| web `npx vitest run` | 37 files, 211 tests passed |
| web `npm run build` | built in 7.9 s |
| `make build-sim` | built (image created 15:18 +06) |
| `make probe` | 10 ok, Tavily skipped (no key), **Open-Meteo FAIL: `Permission denied: cache/weather/58/tmp….tmp`** |
| full `make test` (incl. sim tests in Docker), run just before | 771 passed, 1 skipped |

Micro-test, `GET /api/v1/health`:
```
health ok: True | llm ok: True openai | sandbox: docker True | search live: False
```

Already failing: `make probe` (Open-Meteo). Cause: the API container runs as root and writes
root-owned folders into the bind-mounted `cache/` (344 folders) and `runs/`. A host process can't
write there, and `DiskCache.put` raises, which fails the whole weather lookup. Fixed in Step 2 (2h).

Live calls in Step 1: 2 (probe chat + JSON).

## Step 2: known bugs (each verified in the code first; one commit each)

| Item | Verified? | Fix | Micro-test: before → after | Commit |
| --- | --- | --- | --- | --- |
| 2a pause | Yes: any error that survived the spare key and spare model paused the hosted model for 10 min | pause only for 429/quota, connection failures and 3 × 5xx in a row; `/health` shows `pause_reason`, `paused_until`; the log names the end time | 6 tests: 4 failed → 23/23 pass | 77ce8ee |
| 2b timeouts | Yes: 120 s × SDK retries × 4 attempts × spare key × spare model, unbounded | `AGENT_STEP_TIMEOUT_S` (300 s) bounds call + repair + escalation | hanging stub: waited 30 s (fail) → cut at 0.3 s | 06ce970 |
| 2c empty model id | Yes: reached the provider as `""` | settings validator names `MODEL_FAST` / `LOCAL_LLM_MODEL` | 3 tests: fail → pass | e526d33 |
| 2d real cases | Yes: no lock; list loaded every venue 3× | per-case lock, `CASE_BUILD_DEADLINE_S` 360 s, one-pass index cached per (project, version) | double click, hanging build, load count: 3 fail → 20/20 | 564a954 |
| 2e web | Partly: no fetch timeout (true); HandOver:53 and Scripts save/run already caught errors; the upload handler did not | reads 60 s, writes 330 s, binaries 120 s, `code: "timeout"`; upload error toast | vitest 2 fail → 3 pass | 46bd52c |
| 2f e2e | Could not reproduce | none needed in code | alone in Chrome: pass (2.1 min); whole file: 5/5 pass, API latency max 0.28 s over 312 samples. The old failure was in the full 19-spec run; re-checked in Step 7 | none |
| 2g comments | Yes: said "hybrid" where the code uses "model" | comments corrected | 3 tests pin the behaviour (comments cannot fail a test) | 177ef12 |
| 2h sweep | Partly: sandbox.py:419/427 and osm_venue.py:103 are benign retries/parses; state.py:190 already logged | real ones: hazard source failure (log + session event), report map plan (log), samples install (in `/health`), CORS from settings; **plus the root-owned cache found by `make probe`** | hazard test fail → pass; cache, CORS, samples tests pass | e8369a0, a1ee1c9, e90c358, 3aeefeb |

The ownership fix, checked live:
- `make up` gave 490 root-owned entries back to the user.
- The API runs as `uid=1000 groups=1000,973(docker)`.
- A tier-2 sandbox run finished `ok` (400 people, folder owned by the user).
- `make probe`: **All checks passed** (Open-Meteo 24 hourly gusts).

Wider checks after Step 2:
- `make check`: 766 passed, 1 skipped.
- web: `tsc -b`, `eslint`, vitest 214 passed, build ok.

Live calls in Step 2: about 8 (guided journey alone), about 12 (journeys file), 2 (probe).

## Step 3: sandboxes as the core feature

| Item | What changed | Micro-tests (real output) | Commits |
| --- | --- | --- | --- |
| 3a proof | `test_sandbox_attacks_docker.py` sends 14 escapes through the production path (8 scenario scripts, 6 code jobs), each to the static check and the real container. It found **two real gaps**: an 8 GB allocation got the whole simulation OOM-killed (exit 137); `act.slow_down` had no floor (crowd could be frozen). Fixed: a heap cap set just before untrusted code runs, and a floor on total slow-down | 28 passed (Docker); see `docs/SANDBOX_PROOF.md`, tables generated from the recording | 8d4d9d1, 22a1303 |
| 3b badge | Runners state `Isolation` facts; `/health` and `/agents` report them; header badge with the facts; Help › Sandbox | pytest 4; vitest 3; e2e 3 (Chrome) | 6b8cd53, 7259dd0, 71e107c |
| 3c feed | Run service publishes `sandbox` lifecycle events (queued → running → finished / refused / killed / failed / reused, elapsed, limits, script outcome and reason; never container output); the session streams its own; AI at work shows the feed | pytest 6 (outcome rules + session stream); vitest 5; e2e: Offline test in Chrome, rows appear live | 15cb821, f11cab7 |
| 3d reach | "Sandboxes" tab on Your plan (scripts with code and outcome, Rewind, stress test, every run); "Watch the sandboxes" on the verdict; code on scenario cards | vitest 2; e2e continues into the tab and opens the code | d64914e |
| 3e AI script in the main path | Checked in the database: every model-mode session since 15 Oct has ≥1 AI-written script. Found and fixed: the red team copied the example title from my repair message | 20 red-team tests | c772843 |
| 3f seams | `runner.parallel` replaces `sandbox_provider == "nebius"` in sweep and seeds; NEBIUS_SWITCH.md says plainly what protects runs on Nebius; "not run live" | 2 capacity tests | b57b463 |

**"Don't hardcode" pass, after your message:**
- These moved into settings, sent with every script run (other run ids unchanged):
  - the guards: process limits, script time/line/action budgets, slow-down floor, memory share;
  - the LLM pause length and error threshold;
  - the case deadline;
  - the web timeouts.
- The Help attack table is rendered from `api/data/sandbox_proof.json`, written by `make sandbox-proof`.
- Commits 5dad264, a0f8619, 168fed3.

**A real bug the e2e test found** (commit 546344c):
- What happened: after a plain `docker compose up -d web`, the API lost the Docker group I had added in Step 2h (via `DOCKER_GID`, set only by make), and every simulation failed with "permission denied".
- Fix: the API entrypoint now reads the owner of `runs/` and the socket's group from its mounts and drops to them.
- Checked live: the app process has `Uid 1000, Groups 973 1000, CapEff 0`; a sandbox run finished `ok`.
- Test: `test_api_image_user.py`.

Wider checks after Step 3:
- `make check`: 800 passed, 1 skipped.
- web: `tsc -b`, `eslint`, vitest 226, build ok.
- e2e `sandbox.spec.ts`: 4/4 in Chrome.

Live calls in Step 3: 0 (Offline mode and recorded sessions only).

## Step 6: key-ready architecture (done before Step 4, which builds on its SearchProvider)

| Item | What changed | Tests | Commits |
| --- | --- | --- | --- |
| 6a | Characterization tests pinned the behaviour of local, nebius, openai, fake LLMs; docker, nebius, fake sandboxes; Tavily on/off | 10 passed before the refactor | 206cb7e |
| 6b | `api/adapters/providers/`: three registries, one module per provider; settings validate names and list the valid ones; `LLMClient`, `build_runner` and the search setup look up the provider; no empty or made-up key is ever sent | the 6a tests pass unchanged; 819 fast tests | f84a71c |
| 6c | `/health` gives each provider's title and capabilities; badges, Settings and the Team page read them; no code compares provider names to choose behaviour (data labels such as a stored run's `provider == "fake"` remain) | provider registry 6, providerWhere 2 | af3ba94 |
| 6d | Requirements and `not_configured` per provider; an unconfigured sandbox falls back to `SANDBOX_FALLBACK` (Docker) and says why; search without a key is ok and "not configured" | readiness 3 | bdc356d |
| 6e | `make verify-live`, `verify-nebius-llm`, `verify-nebius-sandbox`, `verify-tavily`: smallest real call per service; SKIPPED without a key; latest result per service kept in `docs/LIVE_STATUS.md`; another provider is checked with its own preset model ids | verify-live 3 | 45f69fd, 3d7716a |
| 6f | Presets live in the provider modules; `make use-%` is generic (`make use-list`); `.env.example` documents every setting and provider variable (`scripts/env_example.py`, a test fails on drift); unserved model ids are named at startup | env/presets 2, model check 2 | 3ff153d |
| 6g | A test-only provider of each kind is selectable by name with no other file edited; Nebius (LLM, sandbox) and Tavily are selectable by settings alone with fake clients (**not live**) | 5 | da24327 |
| 6h | `docs/ADDING_A_PROVIDER.md`, `docs/WHEN_YOU_GET_THE_KEYS.md`, NEBIUS_SWITCH.md | — | 48ebaad |

**One deliberate behaviour change:**
- **Before:** `SANDBOX_PROVIDER=nebius` without a key used to build a Nebius runner that failed every run.
- **Now:** it falls back to Docker and says so (6d asks for that).
- **The test:** the 6a test now pins selection of a *configured* provider, and the unconfigured
  case is pinned in `test_provider_readiness.py`.

**`make verify-live` (real output):**
```
| llm (in use now) | OpenAI-compatible API | PASS | OPENROUTER: ...ultra...; nvidia/nemotron-3.5-lightning:free answered 'ready' |
| sandbox (in use now) | Local Docker | PASS | ran a script in 0.31 s; a network call was stopped: OSError: [Errno 101] Network is unreachable |
| search (in use now) | Tavily web search | SKIPPED | SKIPPED: set TAVILY_API_KEY |
| llm | Nebius Token Factory | SKIPPED | SKIPPED: set NEBIUS_API_KEY |
| sandbox | Nebius Sandboxes | SKIPPED | SKIPPED: set NEBIUS_API_KEY |
```

**`make smoke` on Docker + OpenRouter:**
```
session finished · scoreboard [{'round': 1, 'breaks': 0, 'attacks': 3, ...}] · tokens 11041
report 26 KB, map 11 KB (disclaimer present)
SMOKE OK · lowest free RAM during test 8004 MB
```

Wider checks:
- `make check`: 826 passed, 1 skipped.
- web: `tsc -b`, `eslint` and vitest pass.

Live calls in Step 6: 4 (verify-live twice), about 10 (smoke).

## Step 4: agents and evidence (Tavily as a plug-in; the incident dataset when keyless)

| Item | What changed | Tests | Commits |
| --- | --- | --- | --- |
| 4a | Adapter tests with a fake Tavily client: cache hit, call cap, no key, offline, errors give `[]`, extract cached; a `fake` search provider whose results say "[test data]" and point at example.org; a `SearchBudget` per session | 6 | cc7cf54 |
| 4b | Red team gets a `search` tool. With live search the session runs `SEARCH_QUERIES_PER_SESSION` queries from the venue's features and event kind and lists hits as citable rows (origin `tavily`) next to the dataset. Streams `tool_call {tool: search}`. A `source_url` can only be a hit's or a dataset row's. `InspiredBy.origin`. Web rows never claim a death count | 6 (session with fake client, keyless, report labels, AI team, tools) | ea1fca7 |
| 4c | Evidence desk after the brief: capacity, attendance and guidance searches give cited suggestions in the autopilot result, never applied | 3 | e23b00d |
| 4d | Report and Ask label each source's origin; Tavily credited when used; the dataset cites itself through its plugin | (in 4b tests) | ea1fca7 |
| 4e | Evidence panel (Live web / Incident dataset groups, sentence, what it grounds), origin badges on every source, the agents' tool calls on AI at work, sources to check on the autopilot page | vitest 4; e2e `evidence.spec.ts` in Chrome | 3af8ab6, e952d89 |
| 4f | Keyless is the normal state: "Web search is off (add a Tavily key to switch on)" in the tool calls and the panel; the web group appears only with results | e2e | — |
| 4g | Number check for red- and blue-team titles and rationales (they were unchecked: titles are shown everywhere). Tool lists corrected (analyst → `code_sandbox`, editor without `solver`, brief with `search`); the AI team shows live tool labels (dataset size, search on/off) | 3 + 1 | 62f0264 |

**A bug found in Chrome:** the Evidence strings had never been inserted, so the badge showed
`evidence_panel.origin_dataset`.
- **Fixed** in commit d1-series.
- **Guard:** `i18n/keys.test.ts` checks that every literal string key exists. It failed without the
  fix and named every missing key.

**Not done (needs a key):** recording the demo's searches into `cache/tavily/`. It must come from real
results, so with no key nothing was recorded or faked.

Wider checks:
- `make check`: 843 passed, 1 skipped.
- web: `tsc -b`, `eslint` and vitest 232 pass.
- e2e `evidence.spec.ts` 1/1 and `sandbox.spec.ts` 4/4 in Chrome.

Live calls in Step 4: 0.
