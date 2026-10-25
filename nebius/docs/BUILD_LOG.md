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
