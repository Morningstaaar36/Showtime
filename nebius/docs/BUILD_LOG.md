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
- **Fixed** in commit 6fed98e.
- **Guard:** `i18n/keys.test.ts` checks that every literal string key exists. It failed without the
  fix and named every missing key.

**Not done (needs a key):** recording the demo's searches into `cache/tavily/`. It must come from real
results, so with no key nothing was recorded or faked.

Wider checks:
- `make check`: 843 passed, 1 skipped.
- web: `tsc -b`, `eslint` and vitest 232 pass.
- e2e `evidence.spec.ts` 1/1 and `sandbox.spec.ts` 4/4 in Chrome.

Live calls in Step 4: 0.

## Step 5: a designer for any venue

| Item | What changed | Tests | Commit |
| --- | --- | --- | --- |
| 5a | Baseline with prompt v8: `scripts/design_probe.py` on 8 descriptions (convocation, concert, mall, pandal, airport concourse, mosque, metro, street market). The probe now scores each against what it asked for (`EXPECT`: levels, zones, exits, features, headcount) | — | 77fedbc |
| 5b | `venue_designer.md` rewritten around a neutral site model: the site, where people are, ways out, things on the floor, routes and areas, upper levels. "Front" is defined for any venue; the stage is optional. The tunnel and heading wording is now corridor/concourse/platform/ramp wording. Version 8 → 11 | prompt version test | 77fedbc |
| 5c | Examples: gym, metro, mosque (gallery), mall (atrium), airport departures hall, park concert, street market. Each one builds | guard test passes | 77fedbc |
| 5d | `FeatureKind` + ticket_gate, shop, check_in, security, kiosk, stall. `BuildingUse` + airport, campus. `EventKind` + airport, market, campus. Event profiles, building tags, the web `EVENT_KINDS` and strings follow; `make types` was re-run. (Platforms are passages; stadiums are `sports`.) | `test_kinds_in_step.py` | 77fedbc |
| 5e | Template order from `api/data/templates/index.json`. The incident search reads `api/data/incident_kinds.json`, keyed by event kind, using only settings and keywords the dataset has; the old list asked for nightclub, concert and school, which the dataset does not have. A red-team title that names a tunnel or bridge the venue itself has is kept. The tunnel-only builder error is now neutral. Exit headings match plurals ("Tunnel ends") | `test_generic_venues.py` 4 | 3c5f8ba |
| 5f | Real cases give their documented headcount to the designer (`people` in `real_cases.json`), held within 5 %. A short headcount now names the passages and end areas with no zone | 2 + 1 | 6c074cb, 77fedbc |
| 5g | Re-run with prompt v11: see below | — | — |

**Fidelity probe (live, OpenRouter Nemotron):**

| Prompt | Built cleanly | Asked for | Live calls |
| --- | --- | --- | --- |
| v8 (before) | 8/8 | 32/32 | 10 |
| v10 | 8/8 | 32/32 (v9 had 31/32: it flattened the concourse's upper floor onto the street; the v10 rule fixed it) | 8 + 2 |
| v11 (after) | 8/8 scored, 13/13 built (5 prompts have no `EXPECT`) | 32/32 | 14 |

Each row is **one live run per prompt**, not an average.

**Real cases with v11 (no case text in the prompt):**
- **Itaewon (2,400): built.** v10 drew one 800-person crowd and dropped the 1,200 on the upper street
  and the 400 in the alley, even after the headcount repair. With v11 and the area hint, it draws
  three zones adding up to 2,400. Itaewon-ro and the upper street are at the two ends of the alley.
  **Still approximate:**
  - the alley is drawn south of Itaewon-ro, not north (mirrored);
  - the upper street gets one extra end exit (5.8 m) beside its west and east ends.
- **Love Parade (3,000): built.** The tunnel is the main floor, open at its west and east ends, and
  the ramp joins its north wall up to the festival grounds, as described. **Still approximate:** the
  ramp is drawn as wide as the tunnel (26 m), and the fences are two narrowings.
- **Hillsborough: not re-built with v11.** The free OpenRouter quota ran out on every key during the
  run, and the local model was not running. The v10 build was fine (3,000 people, p95 1,616 s).

Wider checks:
- `make check`: 852 passed, 1 skipped.
- web: `tsc -b`, `eslint` and vitest 232 pass.

Live calls in Step 5: 10 + 8 + 2 (probes), 6 + 7 (real cases with v10), 3 (Itaewon with v11),
14 (probe v11), 2 (Love Parade). The free daily quota ran out at the end.

## Step 7: test in Chrome (in progress, saved 2026-10-25 evening)

The hosted model (OpenRouter free tier) ran out of daily quota on every key; it resets at 00:00 UTC
(06:00 GMT+6). The flows below ran on the **local Nemotron Nano 9B fallback** (`make llm-up`; the badge
reads OPENROUTER → LOCAL), or on replies cached from the hosted model.

**Full Playwright suite in system Chrome:** 20 passed and 6 failed on the first run. Each failure:

| Failure | Cause | Now |
| --- | --- | --- |
| WCAG AA (light) on AI at work | the sandbox feed's state words used the bright safety green (3.3:1) | fixed 37d551a, passes |
| Phone width 320 px on AI at work (419 px) | a single `auto` grid column grew to the 3D canvas | fixed 8f7c291, passes |
| Rewind | the spec still looked for Rewind on the Scenarios tab (moved to Sandboxes in step 3) | spec updated 9c18407, passes |
| Text edit with no model | the hosted model was paused and the local model was not running, yet health said "using the local model" and the hint said only `make llm-up` | fixed eec6e6d; passes with the local model running |
| Toast column (test-plan-click) | the 4 s toast was gone before the check under software rendering | spec reads the toaster's column the moment the toast appears (9c18407), passes; assertions unchanged |
| Report preview on a sample | passes alone (7 s); a load flake in the full suite | re-check in the step 9 full run |

Also found in Chrome and fixed: the Rewind table's last column was cut off on the Sandboxes tab
(202e95c; the guard failed without the fix: 897 > 792 px). `make setup` no longer downloads the
6 GB local model when `.env` uses a hosted one (5b718c6).

**Flows** (screenshots in `docs/screenshots/step7/`):

| # | Flow | Result |
| --- | --- | --- |
| 1 | Describe a venue | metro PASS (2 levels, 3 stairs, 800), market PASS (3 exits, stalls, 1,800), both replayed from the hosted cache. **Mosque FAIL with the local 9B model:** 300 gallery people duplicated on the ground (1,800 for 1,500), one of two east doors, named "New venue". Re-test on the hosted model after the reset |
| 2 | Guided journey | PASS: AI at work with the sandbox feed and tool calls ("Web search is off…", "8 similar real incidents found"), the plan with the Evidence panel |
| 3 | AI-written scenario | PASS: Show the code shows the `on_step` script; the Scripts `import socket` refusal shows its reason (e2e `scripts.spec.ts`) |
| 4 | Stress test and Rewind | PASS: rewind table; the stress test's live counter reached "Finished: 8 of 8 done" |
| 5 | Real case | PASS: an Itaewon double click opens its project once (e2e `real-cases.spec.ts`), the case card with sources |
| 6 | Test modes and AI team | Standard and Offline PASS (journey, `sandbox.spec.ts`); the mode switch is sent (e2e `test-mode.spec.ts`); Quick not yet run end to end; Team page PASS |
| 7 | Export and handover | PASS: the checklist (18.5 KB) and the report (27.5 KB) both carry the disclaimer |
| 8 | Error paths | no Tavily key PASS ("Web search is off"); no model PASS after eec6e6d; a stopped sandbox and a bad LLM key not yet run |

**To resume:**
1. Quick mode end to end; flow 8 (stop Docker mid-run; a bad key on a second API instance).
2. After 06:00, on the hosted model: the mosque; a fresh `work-sandbox-feed.png` with the feed in
   view for the README; preparing the demo project `Spring open day`.
3. The full suite again.
4. Step 8: README (root and app), PITCH, DEMO, VIDEO_SCRIPT, FEEDBACK, JUDGE_GUIDE and QA are
   drafted and committed. Re-check every claim against the screens, then the clean-clone check
   (step 9).

Live calls in step 7 so far: 1 (the hosted call that hit the quota); the rest ran on the local model.

## Step 7, resumed 2026-10-26 (OpenRouter quota reset; Chrome; Docker)

Every flow below ran on the hosted model (OpenRouter Nemotron 3 Ultra and 3.5 Lightning) unless
it says otherwise.

| # | Flow | Result |
| --- | --- | --- |
| 1 | Describe a venue | **Mosque PASS on the hosted model**: 1,500 people (1,200 on the ground, 300 in the gallery), two east main doors and a north side door (`describe-mosque-hosted.png`). The earlier failure was the local 9B fallback |
| 6 | Quick mode end to end | PASS: 3 attacks, 2 broke the plan, 124 s (`work-sandbox-feed-quick.png`) |
| 8a | A sandbox stopped mid-run (`docker kill`) | The run restarted once and the test finished, but the feed showed nothing of it → fixed |
| 8b | A bad model key (a second API on :8001 with an invalid key) | The badge and the Expert banner named the 401; the plan hid that rules stood in → fixed |

**Bugs found in these flows and fixed** (each with a test that failed first):

| Commit | What was wrong |
| --- | --- |
| 42ecfa9 | An AI script that crashed (`ValueError … max() iterable argument is empty`) was labelled "Stopped by a limit"; it is now "Failed: error in its code" |
| 785e5ad | Red-team prompt v6: a filtered list can be empty (the cause of that crash) |
| 85d1543 | The 3D view's floor switch drew over the sticky header when scrolled (new spec `header-on-top.spec.ts`; it failed without the fix) |
| b8632e6 | A run restarted after its container stopped now says so in the feed |
| c50b3a8 | Exit 137 was always "out of memory"; it now says "out of memory, or stopped from outside" |
| cf4cc4d | With the model down, rules wrote the attacks and the summary while the plan looked like an AI test, and the rules' script was logged as "AI-written". The summary now records `stood_in`; the plan and the report say "The AI didn't answer, so built-in rules wrote …" |
| 7fddbc7 | The "model isn't answering" hint names a rejected key; Home's error toasts include the hint and stay up 12 s; the banner's doubled full stop is gone |

**Checked against the Nebius and Tavily docs** (user request: switching must be `.env` only):

| Commit | Finding | Fix |
| --- | --- | --- |
| ae14871 | Sandboxes need `NEBIUS_PROJECT_ID` (the SDK's `Project` header), and we never passed it | A setting, a requirement and an explicit `ContreeConfig(auth=IAMAuth(...))` |
| ae14871 | Outbound network is **on** by default in Nebius Sandboxes, and contree-sdk 0.3.6 (the latest) has no argument for it | Every spawn request carries `{"networking": {"enabled": false}}`; the runner claims a network-off sandbox only when that seam exists; `make verify-nebius-sandbox` proves it live |
| ae14871 | Switching LLM_PROVIDER left OpenRouter's `:free` ids in place | Leftover preset values, or an empty MODEL_FAST, take the active provider's preset; your own ids are kept. The Nebius preset ids match the public model info |
| 2be6b75 | Tavily returns `published_date` only with `include_published_date` | Requested on every search |
| eab5c51 | The quickstart needed `make use-openrouter` | Three `.env` lines; a test builds settings from `.env.example` plus those lines |

Two old tests changed on purpose:
- an empty MODEL_FAST on Nebius takes the preset instead of failing at startup;
- selecting Nebius Sandboxes needs the project ID.

**Full Playwright suite in system Chrome on OpenRouter + Docker: 28 passed, 0 failed (23.5 min)**,
including the sample report preview that had flaked under load. `make check`: 875 passed,
1 skipped. vitest: 241 passed.

## Step 9: final check (2026-10-26)

| Check | Result |
| --- | --- |
| `make test` (all Python tests, including the 19 slow simulator tests) | 917 passed, 1 skipped |
| Full Playwright suite in system Chrome, on the final code | 28 passed (20.2 min) |
| `make check` | 875 passed, 1 skipped; ruff, mypy and import contracts clean |
| `make smoke` (live: OpenRouter Nemotron + Docker) | SMOKE OK: a red-team session in 62 s, 21,341 tokens, report and map with the disclaimer |
| `make verify-live` | OpenRouter PASS, Docker PASS (network call stopped); Nebius Token Factory, Nebius Sandboxes and Tavily SKIPPED (no keys) |
| CI workflow, its exact commands, in a clean clone with no `data/` or `cache/` | api job: lint, import contracts, mypy, 875 tests pass; web job: eslint, `tsc -b`, 241 vitest, `npm run build` pass; sim tests pass in `make test` |
| Clean clone, following the README (three `.env` lines) | `make setup` 92 s (Docker build cache warm; a first build takes longer); `make up` 21 s; health green; badge OPENROUTER with the preset ids |
| Fresh install, real cases | Itaewon built in 22 s and Love Parade in 12 s, each opened once on a double click; the case card shows while the first test runs (fixed 3bbf8ca) |
| Hillsborough with the current designer | built: 3,000 people, pens 3 and 4 behind 0.8 m gates, the radial fence, the tunnel to the concourse (3 live calls) |
| The 3-minute demo as one take (`web/e2e/explore-demo.mjs`) | all six beats pass in order; the screenshots are `docs/screenshots/step7/demo-*.png` |
| Older docs (handoff, user, testing, contributing, exercises) | updated to the hosted-model setup and the `.env`-only Nebius switch (a50348f) |

**Left, and needing a person or a key:**
- the live Nebius Token Factory and Sandboxes runs, and Tavily (`docs/WHEN_YOU_GET_THE_KEYS.md`);
- recording the video;
- a public demo URL;
- the feedback form;
- pushing and merging.
