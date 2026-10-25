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
write there, and `DiskCache.put` raises, which fails the whole weather lookup. Fixed in Step 2 (2i).

Live calls in Step 1: 2 (probe chat + JSON).
