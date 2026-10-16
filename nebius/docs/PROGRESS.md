# Progress log

Newest entries at the bottom. Each entry: what was built, commands run, results, open issues.

---

## 2026-10-08 — M0: environment and probes

**Machine:** Linux 7.0 (Ubuntu), 16 cores, 14 GiB RAM, **no swap**; NVIDIA RTX 5060 Ti 16 GB
(sm_120), driver 580.178, CUDA toolkit 13.3. Docker 29.7 via **Docker Desktop** (VM with
3.3 GiB RAM, 16 CPUs, no NVIDIA runtime).

**Decisions**

- Everything stays inside the project folder (owner's instruction). `scripts/env.sh` puts
  `.tools/bin` on PATH and keeps uv, Python, Hugging Face and npm caches in `.tools/`
  (gitignored, excluded from VS Code watching). Model weights live in `./models/` instead of
  `~/models/showtime/`.
- No GPU in Docker, so `llama-server` runs natively (brief §18 fallback). `git clone` of
  llama.cpp kept failing on this network (HTTP/2 stream resets), so I used the official
  prebuilt release `b11476` (`llama-b11476-bin-ubuntu-cuda-13.4-x64.tar.gz`), which links
  against the local CUDA 13.3 libraries in `/usr/local/cuda/lib64`.
- Docker Desktop's VM has only 3.3 GiB, below the brief's 4 GB per simulation. Sim containers
  use `SIM_MEM_LIMIT=2g`; the web container must serve a built bundle, not a dev server.

**Model:** `dominguesm/NVIDIA-Nemotron-Nano-9B-v2-GGUF` → `nemotron-nano-9b-v2-q4_k_m.gguf`
(6.5 GB), sha256 `62df2498…4f80` verified against the Hub.

**Probe (`scripts/probe_llm.py`)**

| Check | Result |
| --- | --- |
| VRAM with model loaded, ctx 8192 | 6,427 MiB (budget ≤ 7 GB) ✅ |
| llama-server RSS | ~600 MB; system RAM available 9.9 GB ✅ |
| Plain chat (`/no_think`) | ✅ ~45 tok/s on first call |
| JSON schema via `response_format: {type: json_schema}` | ✅ valid on first try **[VERIFY resolved]** |
| Reasoning toggle | ✅ `/think` → `message.reasoning_content`; `/no_think` → none **[VERIFY resolved]** |

---

## 2026-10-08 — M1: plugin core, contracts, templates, patch ops, validation

- `api/models/`: Venue, VenuePatch, Attack, Fix, RunRequest/RunResult, SessionEvent,
  Countdown (Pydantic v2). Patch ops and scenario events carry an open `op`/`type` string and
  are validated by the plugin registered for it.
- `api/core/extensions/`: 12 extension points as `Protocol`s, a registry, pluggy hookspecs and a
  small geometry SDK for plugins. `api/core/plugins.py`: folder discovery
  (`plugins/*/plugin.toml`) + entry points, feature flags (`config/features.yaml`,
  `FEATURE_<ID>` env), per-plugin Pydantic config, failure isolation.
- Plugins: `ops_core` (12 edit ops, each with validate/apply/invert) and `events_core`
  (7 events with schema, id checks and Tier 1 effect).
- Templates (`scripts/build_templates.py` → `api/data/templates/`): festival field (6,000),
  conference hall with mezzanine (1,200), school wing (400), T-alley (1,700; 3.2 m × 45 m alley
  from the Wikipedia article on the Seoul Halloween crowd crush).
- Geometry validation: duplicate ids, exits outside/not on a wall/too narrow, overfull zones,
  zones that cannot reach an open exit (including across stairs), stairs off the floor.

**Tests:** `uv run pytest` → 31 passed (templates validate, every op applies and undoes exactly,
every event passes conformance, atomic patches, new geometry errors rejected).

Bug found by the conformance suite: undo of `remove_*` re-appended items at the end of their
list; fixed with an `index` parameter on `add_*` ops.

---

## 2026-10-08 — M2: simulation image and engine

- `sim/Dockerfile`: python:3.12-slim, JuPedSim 1.4.2 (installed `--no-deps`: its PySide6/VTK
  deps are only for the desktop visualiser), PedPy 1.5.1, locked with `uv pip compile`.
  Non-root, `--network=none`. Image 730 MB.
- Verified JuPedSim API **[VERIFY resolved]**: `switch_agent_journey` (mid-run block/redirect
  works, no t=0 fallback needed), `agent.model.desired_speed` is writable (mid-run slowdown and
  holding people with speed 0), `switch_geometry` takes a Shapely polygon and refuses when a
  new obstacle would cover a person, `agents_in_range` returns an always-truthy iterator.
- Engine (`sim/plugins/engine_jupedsim.py`): per-floor sims, upper floors first, stair queue
  (travel = length / STAIR_SPEED, throughput = width × STAIR_FLOW), events (block/unblock exit,
  surge, slowdown, counterflow, one_way, staggered release, marshal redirect), time travel
  (`intervention_at_s` with layout switch and late exits), progress file, wall-clock watchdog.
- Doors are modelled as 1.2 m passages through the wall with the exit area at the far end.
  Without this, people slipped into exit areas from the side and flow through a 2 m door was
  5.6 people/s (unphysical); with passages it is 2.6–2.9 people/s.
- Metrics (`sim/metrics.py`): Gaussian-smoothed 1 m density grid normalised by walkable area,
  hotspots (connected cells over the warning threshold), RSET p95/max, per-exit flow, PedPy
  classic density in a 2 m band in front of each exit, compact binary artifacts
  (`traj.bin` int16 at 2 cm + uint16 ids; `density.bin` uint8 at 0.05 people/m²).

**Calibration**

| Agent radius | Door flow (people/m/s) | Hall peak density |
| --- | --- | --- |
| 0.18 m | 1.43 | 6.4 |
| 0.20 m | 1.25 | 5.6 |
| **0.22 m (chosen)** | 1.07–1.10 | 4.6 |

0.22 m makes the jam density match Weidmann's 5.4 people/m², so "danger" means real jamming
rather than any queue. Time step: hall p95 = 199 s (Δt 0.01) / 206 s (0.025) / 215 s (0.05):
Tier 3 uses 0.025 s up to 2,500 people, otherwise 0.05 s (≈8 % conservative).

**Benchmarks (Tier 3, 4 CPUs)**

| Venue | People | p95 evacuation | Peak density | Wall time |
| --- | --- | --- | --- | --- |
| School wing | 400 | 124 s | 4.2 | 5 s |
| Conference hall (2 floors) | 1,200 | 215 s | 4.6 | 15 s |
| T-alley baseline | 1,700 | 189 s | 4.4 | 13 s |
| T-alley + counterflow 300 | 2,000 | gridlock, 890 trapped | 6.0 | 87 s |
| Festival field | 6,000 | 524 s | 5.5 (gates) | 206 s |

**Tests:** `sim/tests/test_sim.py` → 9 passed (everyone leaves, blocking raises RSET,
determinism, time travel identical before t, multi-floor conservation, surge/slowdown,
one-way stops counterflow, Δt calibration, readable error on bad input).

Open issues: CFSM can gridlock in head-on counterflow (intended for the counterflow attack,
but it is a model property; see BACKLOG: evaluate JuPedSim's AnticipationVelocityModel).

Update (later in M2–M6): doors became 0.6 m passages with the exit stage *inside* the doorway,
plus three engine fixes for model artefacts, each found by watching replays:
"doorway capture" (people who reach the doorway of an exit they were not assigned to leave
through it instead of blocking it), a squeeze rule (radius 0.15 after 4 s without flow at a
converging junction) and a sidestep waypoint for isolated two-person corner deadlocks.
AnticipationVelocityModel was tried and gridlocked more often; CFSM stays the default.

---

## 2026-10-08 — M3: Tier 1, countdown, weather, stage check

- Tier 1 (`api/core/tier1.py`): geodesic walking distance on a 0.5 m grid (scipy csgraph
  Dijkstra), min-cost-flow exit assignment (NetworkX) with binary search on the finish time,
  fluid queue per exit, stairs as capacity-limited links. 3–20 ms on all templates.
- Calibration (`make calibrate`, Tier 1 / Tier 3 p95): school 1.10, hall 1.11, alley 0.62,
  festival 0.63. Stored in `api/data/calibration.json`, printed in every report. Tier 1 is
  optimistic for open-air crowds that must queue across a wide front (documented).
- Countdown: `T_latest = T_hazard − (pre-movement + RSET × safety factor)`; tests for no
  hazard, already too late, and outdoor/indoor hazards.
- Stage check (Pynite frame, ASCE 7 velocity pressure): uplift, sliding and overturning
  governors; tests prove more ballast raises the limit and more area lowers it.
- Open-Meteo forecast and archive endpoints verified (`wind_gusts_10m`, `wind_speed_unit=ms`);
  disk cache; a weather snapshot can be stored in a project so demos replay offline.

## 2026-10-08 — M4: walking skeleton in the real app

- SQLite (SQLModel + Alembic 0001): projects, venue versions (snapshot + patch + base version
  for undo/redo), runs, red-team sessions, session events, audit log, user settings.
- Web: Vite 7 + React 19 + TS strict, Tailwind 4 tokens from §4A.5, Radix controls, Public Sans
  self-hosted. Projects, Onboarding, Workspace (Plan / Simulate / Red Team / Report), Settings,
  Help. R3F scene with section-cut walls, exit gates with arrows, stage truss, zones, stairs,
  exploded floors, N8AO + bloom; instanced agents fed from binary trajectories; density shader
  (cividis) with danger contour; drag edit with TransformControls; draw barrier/zone/exit;
  measure; "Break it yourself" with instant estimate then "Confirm with simulation".
- Verified: projects and versions survive an API restart; undo/redo across drag and text edits.

## 2026-10-08 — M5: LLM adapter, Venue agent, cost meter

- `api/adapters/llm.py`: OpenAI SDK; role → model/price; json_schema response format
  (llama-server grammar) with prompted-JSON fallback; one repair call; record/replay cache keyed
  on provider, model, messages, schema *content* and temperature; token and cost meter events.
- Venue agent eval (`scripts/eval_venue_agent.py`): 6/10 → **10/10** after making the op tag
  the first, required property of each op schema (the 9B model otherwise picked the wrong op)
  and fixing a stale cache key.
- Memory incident: two OOM kills. Cause: llama-server mmap'd the 6 GB model (RSS 4.4 GB) and
  reserved an 8 GB prompt cache. Fix: `--load-mode dio --cache-ram 512` → RSS 0.88 GB.
  Added `scripts/memguard.sh` (logs `logs/mem.log`, stops sims/Vite below 1.5 GB free).

## 2026-10-08 — M6: Red Team Night

- Red team: venue features + filtered incidents (388 Feliciani records + seed list); every
  card cites a URL or the dataset DOI + row; "already tested" list so later rounds escalate.
- Blue team: AI fixes plus rule-based standard responses (one-way flow, staggered release,
  marshal redirect, extra exit); `check_fix` validates the patched venue and operational events.
- Orchestrator: baseline → attacks (Tier 1 ranked, Tier 2 simulated) → fixes → accept when the
  break disappears or the primary metric improves ≥ 10 % without hurting the baseline → next
  round on the fixed venue → Tier 3 before/after confirmation → judge (number-checked).
- Break = sustained danger density ≥ 5 s, trapped people, people not evacuated, or
  evacuation × safety factor over the target (indoor 300 s, outdoor 480 s).
- Real session on the hall: worst attack 311 s / peak 5.29 / 38.5 s above danger →
  after the AI east exit + marshals 169 s / 4.94 / 0 s.
- SSE stream with replay (`?after=`), branch tree, scoreboard, activity feed, final card.

## 2026-10-08 — M7–M8: P1 features and Nebius adapters

- Time travel (fix from t), split-screen compare on one clock, marshal bubbles, two-floor
  chaining, rules pack (IBC 2021 example values, labelled), wind panel, Ask the venue,
  printable report, SVG evacuation map, JSON bundle, project export/import (.showtime.zip).
- DXF (jps-* layers, ezdxf) and JSON importers.
- NebiusRunner built from the contree-sdk 0.3.6 source (base image → venue image → attack →
  fix child images); tested with a fake client; `make smoke-nebius` skips without a key.
- Tests: 81 passed, 1 skipped (Nebius live) in `api/tests`; 9 passed in `sim/tests`.

## 2026-10-08 — M9 (in progress): demos and handoff

- Demo packs precomputed with real Nemotron sessions (`make demo-precompute`):
  T-alley (351 s session, scoreboard 1 → 0, one-way kept), conference hall (218 s, kept F1_1
  and F2_1), Wellington festival (stage wind story with a stored forecast snapshot).
  Packs are LZMA-compressed and installed as sample projects on first start.

## 2026-10-08 — M9: self-review, fixes found by testing, final verification

**Screenshot self-review** (`make screenshots` → `docs/screenshots/`, 16 screens, light and
dark, filled, empty and error states). Findings and fixes:

| Found | Fix |
| --- | --- |
| Hotspot labels stacked on top of each other in the alley | one label per 10 m cluster; rings stay |
| Wind chart: two days of hourly ticks ran together; markers could land on the wrong day | axis keyed on full timestamps, event day only |
| Branch tree zoomed to unreadable in the side panel | indented vertical tree at full size |
| Final card green with "–" when 1,925 people never got out | amber "still at risk"; "1,925 still inside" |
| AI text used machine ids ("street_w", "door_e1") | ids replaced by venue names in cards, judge text, tree, report, marshal bubbles; new exits get names ("East door") |
| Red team titled an attack "Staircase congestion" on an open field (9B model borrowed it from the incident) | titles naming features the venue lacks are rebuilt from the events (audit-logged); festival demo regenerated |
| Missing project offered "Try again" | explains and links back to projects |
| Chip and report showed different "start evacuating" times without saying why | both name their evacuation-time basis |

**Bugs found by the smoke test and journeys**
- "Add a 2 m exit on the east side" failed on the school wing: the model confused x and y and
  the repair round got an error without a range. `add_exit` now defaults to the middle of the
  side, errors give the valid range, the venue summary names each wall's coordinate. Venue
  agent eval 12/12 (two new phrasings).
- "Stress test finished" toast was never wired (and cached results gave no feedback).
- During an API restart the browser showed a JSON parse error; now "server isn't reachable",
  queries retry ~30 s, and the web container waits for a healthy API.
- Re-importing a `.showtime.zip` lost its run history (content-addressed run ids already
  existed); deleting a project left session events behind.
- The API container's view of SQLite was corrupted while a host script wrote the same file
  (WAL across the Docker Desktop file share). Host scripts now use scratch databases.
- /tmp is RAM here: pytest's temp dirs held 2.1 GB. Moved to `cache/tmp/pytest`.

**Demo packs**: delta-coded trajectories at 6 cm (lossless coding of a visually lossless
quantisation), 43 MB → 18 MB; packs tracked by hash so updates replace unedited samples.

**Final verification (compose stack, local Nemotron)**

| Check | Result |
| --- | --- |
| `make check` (ruff + format + import-linter, eslint, mypy --strict, tsc, fast tests) | green |
| `make test` (API + Docker sim tests) | 96 passed, 1 skipped (Nebius live) |
| `make test-web` (vitest) | 10 passed |
| `make e2e` (Playwright journeys) | 3 passed |
| `make smoke` | OK in 40–80 s; lowest free RAM 4.28 GB |
| `make probe` | all green; Tavily skipped (no key) |
| Venue agent eval | 12/12 |
| Peak memory during demo precompute (6,000 people) | ≥ 3.7 GB free; llama-server ≤ 2.2 GB RSS |

## 2026-10-08 — M10: fresh-clone verification

`git clone` into a scratch folder (toolchain, model and dataset symlinked to avoid a 6 GB
re-download), then `make setup && make check && make test`, `vitest`, `vite build`.

- First run failed: `.gitignore` patterns `models/`, `data/` and `state/` (meant for weights,
  datasets and the database at the root) also matched `api/models/` (contracts),
  `api/data/` (templates, calibration) and `web/src/state/` (UI stores), so they had never
  been committed. Patterns are now anchored to the root and the files are committed.
- Second run: pytest's temp folder needed a parent that a fresh clone lacks; fixed.
- Third run: setup OK, `make check` green, `make test` 96 passed / 1 skipped, vitest 10
  passed, production web build OK.

## 2026-10-08 · Post-0.1: describe-it and real-place venues, hosted models

- **Hosted models:** `LLM_PROVIDER=openai` (any OpenAI-compatible API). Tested live with OpenRouter's
  free Nemotron 3 Super. Found and fixed: a judge call hung for minutes (gateway keep-alive) → total
  deadline; Nemotron 3 spent its whole reply length reasoning and returned nothing → `LLM_EXTRA_BODY`
  `{"reasoning":{"enabled":false}}`; free models were priced at Nebius rates → 0 for `:free`.
  AgentRouter was evaluated and rejected: it refuses every client except its listed coding tools.
- **Describe it:** designer agent → `VenueSpec` → solver (`api/core/venue_builder.py`) → geometry checks →
  one repair round. Live: 4 descriptions (two-floor hall, open-air concert, wedding hall, arena) built
  valid venues in 2–15 s; one bug found (balcony people counted twice) and fixed in prompt and solver.
- **Real place:** Nominatim search + Overpass features → `api/core/osm_venue.py`. Simulated on real data:
  BUET ME building (800 people, 95% out 131 s), BUET area (2,500 people; first 191 then 176 stuck in
  0.5 m slivers between buildings, fences and the edge → gaps < 1.2 m closed, pockets filled →
  everyone out, 95% in 171 s), Ramna Park with its lake (5,000 people, 95% out 723 s; the last 32
  still walking at the 15-minute cap: a real finding, not a stuck crowd).
- **Checks:** `make check` green; `make test` 114 passed, 1 skipped; `make test-web` 10 passed;
  `make e2e` 3 passed; `make smoke` OK on OpenRouter (212 s, lowest free RAM 4.9 GB); browser run of
  both new tabs with no console errors.

## 2026-10-11 — P2-01: scene snapshot and spatial facts implementation

- Added typed, lossless scene snapshots over the existing Venue; source version, complete
  scene hash, existing layout hash, units, stable object references, and optional provenance.
- Added read-only `/projects/{id}/scene` and `/projects/{id}/scene-facts` endpoints,
  including historical versions and explicit invalid-input responses.
- Added computed areas, component geometry with holes, per-part zone reachability,
  directed stair connectivity, representative-point clearances, and bounded route lengths.
- Added contract registration for schema export, interface documentation, and prepared
  analytical/unit/API acceptance tests.
- Static checks: changed Python files parse successfully; Ruff 0.16.10 lint passes;
  code formatted with Ruff; `git diff --check` passes. These are not runtime tests.
- The user reported all 29 scene unit/API cases passing. Live scene endpoints were also
  checked on the synthetic room: 80 m² usable floor, 20 people, reachable exit, and a
  7.79 m representative-point route. The sample zone was then enlarged to 8 m² to
  satisfy the existing placement-density limit, with the unit fixture updated to match.
- The automated suite has not been rerun after that fixture correction. The existing
  regression suite and live simulation/source-consistency check remain pending.

## 2026-10-12 — P2-02: constrained bundles and complete plan persistence

- Added typed organizer plans in `Venue.extensions.organizer_plan`, preserving geometry,
  constraints, actions, source, approvals, staff/equipment allocations, and dependencies
  in the existing version history. Undo/redo, duplicate, and ZIP import/export retain them.
- Added plan read/configuration, bundle preview/application, and evidence-applicability
  endpoints. Bundles support action additions, replacements, and removals alongside
  geometry changes. Invalid proposals never create a partial project version.
- Enforced fixed/locked geometry, locked floors, permitted operations, declared
  existing/proposed exits, construction permissions, access, action references and
  dependency order/cycles, resource availability, and overlapping allocation limits.
  Recorded approvals require source/attribution; their authenticity is not verified.
- Added transactional expected-version checks and HTTP 409 for stale/concurrent writes.
  Preview does not reserve a version. Direct geometry patches/full replacements cannot
  bypass saved constraints; explicit organizer configuration/history commands can change policy.
- Runs/estimates automatically consume saved events. Complete plan fingerprints affect
  cache IDs, with evidence labeled current/stale/unknown independently of run status.
  Candidate-fix and pre-feature evidence remain conservatively unknown.
- Agent geometry bundles no longer skip conflicting edits individually. Accepted fixes
  update the working state before later targets are evaluated. Applying a finished
  session preserves its measures and refuses to overwrite a newer project version.
  Legacy measures retain an explicit unallocated/unenforced state until organizer migration.
- Added backend documentation, actual synthetic request JSON files, and the one-command
  Docker check `make m1-test-p2-02`. UI integration and structured agent proposal generation
  remain Person 3 work. Administrative action/resource validation does not simulate
  installation work or establish sufficient staffing; geometry material needs are not inferred.
- Verification used isolated macOS ARM64 Python 3.12 in the ignored cache because Docker
  Desktop was manually paused. Dependencies installed with `uv sync --project api --frozen`
  and an isolated `UV_PROJECT_ENVIRONMENT`; no global packages or local `.env` were changed.
- **Fast API suite: 185 passed, 1 skipped** via
  `../cache/m1-plan-native-env/bin/pytest -q -m "not slow" --tb=short
  --basetemp=/private/tmp/showtime-p2-02-native` from `api/`. This includes P2-01's corrected
  scene fixture and the previously pending geometry/API/persistence/red-team regressions.
- **Static checks:** Ruff check and format across API/plugins/scripts/sim passed;
  strict mypy passed on 41 backend source files; all three import-boundary contracts
  passed. Schema export generated 61 definitions, and the actual room/setup/bundle
  example JSON files validated together. `make -n m1-test-p2-02` and `git diff --check` passed.
- Gate cleanup: resolved existing scene/agent typing errors found against the committed
  baseline; provider-test settings now ignore the private `.env`; M1 launcher received a
  formatting-only wrap. These changes were covered by the final fast suite/static checks.
- **Pending:** Docker-image execution, live browser testing of the new endpoints, and a
  real selected-plan simulation/source-consistency run after Docker is unpaused. Fake
  provider/native tests do not establish physics accuracy or live model performance.

## 2026-10-12 — P3-01: three-screen journey and collaborative editor

- Guided journey Describe (`/`) → Check your venue (`/p/:id/describe`) → AI at work
  (`/p/:id/work`) → Your plan (`/p/:id`); the studio is Expert view (`/p/:id/expert`), old
  workspace URLs redirect. Details: [P3_01_GUIDED_JOURNEY.md](P3_01_GUIDED_JOURNEY.md).
- Collaborative editor: numeric and drag door/barrier edits, existing vs proposed, provenance
  through the P2-01 scene contract, locks, AI patch preview (dry run, 3D outlines, lock
  conflicts), stale-evidence detection by simulation hash.
- Backend: organizer-only `set_annotation` op hidden from agents; annotations dropped/restored
  with removed objects; `POST /projects/{id}/patch/preview`; `apply_final` refuses stale plans and
  keeps current annotations; `/edit` returns 503 instead of 500 when the model is unavailable.
- Checks: ruff/format/import-linter green; pytest 166 passed, 1 skipped; vitest 22 passed;
  Playwright 5 passed (fake LLM and fake sandbox); `vite build` OK. mypy's 15 errors are in
  `api/core/scene.py` and predate this change. No real simulation or live model was run.

## 2026-10-13 — P2/P3 integration work-in-progress snapshot

- Shared bundle validation, typed agent/rules fixes, operational planning forms and new
  pipeline regressions added in the isolated review checkout.
- Docker schema generation and cached dependency setup succeeded. The initial focused
  Docker test command timed out during collection; latest full pipeline verification is
  incomplete.
- User requested a snapshot on the new `ridwan` branch before further implementation/tests.
  See [current branch status](P2_P3_BRANCH_STATUS.md) for exact verification and remaining work.

## 2026-10-14 — Integration branch `integration/p2-p3` verified (Linux x86_64)

- Branch merges `main` (P2-01), `ridwan` (P2-02 + P3-01 combined review) and
  `feat/p3-01-guided-journey` (already contained in `ridwan`; recorded as merged).
- Fixed: fix measures were validated before the fix's own edits, so a fix adding an exit
  and redirecting people to it was rejected (`apply_fix_bundle`); long project names widened
  the home page on phones; ruff lint/format. Browser test fixes: dropdowns selected by role;
  15 s waits for save confirmations because software-rendered WebGL can stall the page.
- Checks: `make lint` and `make typecheck` green; fast pytest 239 passed, 1 skipped
  (includes the 50 ms instant-estimate gate); Docker simulator tests 9 passed (24 s);
  vitest 33 passed; `vite build` OK; Playwright 6 passed (fake LLM, fake sandbox; the
  operational-plan journey passed 8/8 repeats).
- Real Docker/JuPedSim, fake LLM (rule-based fallbacks): every step of
  [P2_02_TESTING.md](P2_02_TESTING.md) passed — preview/apply, stale 409, construction and
  over-allocation refusals, saved action exactly once in a real run, evidence current →
  stale → current with undo, export/import with identical plan hash and actions. A
  conference_hall_2f session found 1 break, accepted fix F1_R1 (new north exit; peak
  5.32 → 4.27 people/m², p95 292 → 192 s), applied as proposed construction; re-applying
  or applying after an edit returns 409 `stale_plan`.
- Live OpenRouter (`nvidia/nemotron-3-super-120b-a12b:free`, cache off) + real Docker:
  `make smoke` passed in 67 s — text edit applied, Tier 3 run, session with 1 break and a
  blue-team fix confirmed by simulation, judge, report and map; 4 model calls, all HTTP 200,
  9,249 tokens.
- Fixed (pre-existing on `main`): applying a session that kept no fixes saved an identical
  new version and could be repeated; the API now refuses it (409 `no_plan`). Both UIs
  already hid the accept button in that case.

## 2026-10-14 — Simple organizer UI and a demo-ready Docker stack (`ui/simple-organizer`)

- Bright light theme by default; Home asks "Where is your event?" (map, describe, sample);
  full-page map picker (`/new/place`) with numbered steps; Check screen as three questions
  with drag-and-drop doors, fences, crowds and stalls and direct grab-to-move; progress bar
  while the AI tests; Help and Expert view always in the header. See [DEMO.md](DEMO.md).
- Fixed: large map areas failed to build (automatic headcount above the 100,000 zone limit;
  now capped at 10,000 with a note); the selected place was never outlined on the map.
- Fixed the Docker stack on Linux: an empty `.env` value followed by an inline comment is
  read by Docker Compose as the comment (`HOST_RUNS_DIR`), so every simulation failed to
  start and sessions silently fell back to instant estimates; and the root API created
  run folders the non-root simulator could not write to (now handed to the sim user).
- Checks: lint, types, fast pytest 243 passed / 1 skipped, vitest 39, Playwright 6/6 (fake
  providers). `make up` stack with live OpenRouter: map flow and a conference-hall session
  (2 breaks, 2 fixes kept, peak 6.95 → 4.6 people/m², p95 279 → 168 s, 9 Docker runs).

## 2026-10-14 (evening) — Remaining core work, merged on `ui/simple-organizer`

Built in parallel git worktrees, each feature on its own branch, merged with `--no-ff`:

- **Typed evidence (P2-03):** every run has a `basis` (instant estimate, partial or completed
  simulation, preview, unknown); a failed simulation stays visible next to a separate linked
  estimate; fixes are kept only on simulation evidence; sessions carry an `evaluation`
  (confirmed only when the before/after full simulations ran to the end) and a `cost` record.
  All "confirmed by simulation" wording now comes from the basis (report, Expert view, score,
  countdown, ask answers, glossary).
- **Autopilot (N13):** `POST /autopilot` from a sentence or a project through the LangGraph
  graph and a red-team session to a tested plan, eight plain steps with SSE replay, stop,
  outage notes; never applies fixes. Home → Describe it → **Plan it for me**; `/autopilot/:id`.
- **Ask or change anything (N15):** `POST /projects/{id}/ask-anything` routes edit / question /
  what-if / navigate with the fast model, keyword fallback (20/20 on the fixture set with the
  model down); edits are previews until confirmed. Fast-model answers that stay invalid are
  escalated once to the main model.
- **Your plan (P3-03/05/06, N16):** choose which kept fixes to accept (`{fix_ids}`; subsets
  are labelled "tested one by one"), cost card, printable handover checklist exporter
  (`/sessions/{id}/checklist`), ask box, one next step per state.
- **UI polish:** Projects, Settings, Help, Onboarding, NotFound, Copilot and Expert view
  (View menu, cost in the provider badge, "Plan for the day"), dark mode and phone widths.
- **Nebius readiness:** self-healing requests (no JSON mode, rejected extras, reasoning that
  used every token), `make use-nebius|use-openrouter|use-local`, `make smoke-nebius` per role;
  Token Factory endpoint and auth verified. CI workflow and root licence restored.
- Checks: lint, mypy, import contracts; pytest 425 passed / 1 skipped; vitest 94; Playwright
  6/6 (fake providers).
- **Live on the rebuilt `make up` stack** (OpenRouter Nemotron 3 Super, real JuPedSim):
  Autopilot from a sentence → designed school hall, 4 model calls, plan held up, evaluation
  "unconfirmed: nothing to fix", nothing applied; ask box: what-if, question and edit routed
  by the model, edit saved only on confirm; Autopilot on the conference hall → 2 of 3 attacks
  broke it, 2 fixes kept, evaluation **confirmed** (peak 6.95 → 4.6 people per m², 95%
  evacuation 4 min 39 s → 2 min 48 s, 0 inside), subset accepted with the "tested one by one"
  note, checklist and report generated; no browser page errors.

## 2026-10-15 — Sandboxes made essential (`SANDBOX_SCOPE.md`)

- AI-written scenario scripts run inside the simulation sandbox (`script` event, `view`/`act`
  API, static pre-check plus an in-sandbox re-check and per-call budgets); every test includes
  one (the model's, or the built-in example). AI crowd analyst and user scripts run as sandboxed
  code jobs (`run_code`: no network, read-only inputs, caps, timeout). Rewind saves the crowd at
  the worst second and branches responses from it (single-floor venues); attacks/fixes and
  stress tests fan out over parallel sandboxes. Nebius runner: per-run folders (fixes a branch
  reading its parent's result), resume-from-snapshot, code jobs.
- Checks: lint, mypy, import contracts; pytest 524 passed; real-Docker tests 21 passed (scripts,
  checkpoint/resume, no network, read-only, endless loop stopped); vitest 108; Playwright 7/7.
- Live (OpenRouter Nemotron 3 Super + real JuPedSim, school wing): the model wrote "Dynamic exit
  blockage based on real-time queue", which closed the West stairwell at 25 s (168 people
  rerouted); analyst answers with checked numbers ("longest queue 13 people at 62 s", "203 via
  stair_w, 197 via stair_e"); rewind at 101 s compared do nothing (2 min 37 s) with two
  responses; stress test 8/8; `import socket` refused before running.
- Known: rewind's "best" weighs overall risk, so a response can win on lower density while
  emptying a few seconds slower; multi-floor venues can't be rewound yet.

## N10 Validation lab: simulator vs the Jülich 2006 bottleneck experiment

- `make get-data` downloads the archive metadata and trajectories (DOI 10.34735/ped.2006.2,
  CC BY 4.0, sha256-checked); `make validate` simulates the b-series (10 widths, 3 seeds, app
  defaults, about 3 min) and measures both with the same PedPy code -> `api/data/validation.json`,
  `GET /api/v1/validation`, Help › How good is the simulator?, one line in the HTML report.
- Result: simulated bottleneck flow is 50–60% lower than measured at every width (median
  |error| 55.4%; target 15% missed). Simulated specific flow is about 0.87 /(m·s), measured
  1.8–2.2. The cause is the CFSM 1 s time gap. Details in `docs/VALIDATION.md`.
- Calibration (2026-10-15): one parameter, the time gap to the person ahead, fitted on widths
  0.9/1.1/1.4/1.8/2.2 (0.25 s: mean -0.5%) and checked on the other five (median |error| 4.4%).
  New default `AGENT_TIME_GAP=0.25`; published result over all 10 widths: median |error| 4.0%,
  mean -0.3%. `AGENT_TIME_GAP=1.0` stays documented as the cautious option.

## 2026-10-15 — Browser test as a new organizer: wedding hall (indoor), Suhrawardy Udyan (open air)

Headless Chromium against the built stack (`make up`), screenshots after every step.
- Indoor (Autopilot, 450 guests): verdict, AI-written scenario and fixes worked. Fixed: change
  card hidden under 3D labels; designer ignored door walls and names (prompts v3/v4, not yet
  re-tested live: the OpenRouter key expired).
- Open air (map import, 566 x 757 m, 3,200 people): headcount, fence and crowd drops saved
  (versions 1 -> 4); AI test on the rule-based fallback, 4 attacks, 7 min 16 s, "This plan
  holds" (95% out in 6 min 5 s, peak 2.5 people per m²); stress test at scale 8/8, breaks 0;
  checklist opens; the analyst says plainly that the AI is not answering.
- Fixed on the way: the check screen grew to 2,300 px with 11 gates so the park was framed
  below the fold (screen now fills the window, panel scrolls); camera zoom and fog limits grow
  with the site; `removeChild` crash when leaving any 3D page (drei labels re-mounted during
  teardown; one stable label layer now); mapped fences along the edge became invalid polygons
  and the scene check refused the venue; numbered "Building N" labels hidden; Help text now
  says the calibrated simulator matches; e2e journey picked a project menu instead of the
  template.
- Checks: `make check` (530 passed), vitest 110, Playwright 7/7 with fake providers.
- Open: the AI parts need a new key to re-test live (designer door walls, Autopilot,
  analyst). Projects imported before the fence fix keep their bad fences (re-import to clear);
  `/scene` then returns 422 and the check list shows fewer details.

## 2026-10-15 — Generic venues (branch `shahraz`)

Organizer feedback: the app was template-bound (map buildings arrived as one ground floor, no
rooms, no third floor, no patients or marches, no per-floor replay). Full write-up:
`docs/GENERIC_VENUES.md`; remaining work allocated in `TEAM_TASK_ALLOCATION.md` §11.
- New OpenRouter key installed in `.env` (masked, never committed); live model checks: the
  designer puts doors on the named walls, text edits apply or ask, the analyst answers with
  computed numbers. Health now detects a rejected or empty key.
- Merged into `shahraz`: `ui/simple-organizer`, review fixes (error shape, sandbox hardening,
  Docker-test skips, key masking), building ops (11, with conformance tests), designer feature
  sliding, editor and replay groundwork.
- Added: building generator (storeys, stair cores, rooms grouped into wards, IBC occupant
  loads), map import options and `/places/at` levels/use, `/event-kinds`, map form controls,
  floor switcher and one-floor view, label-based edit summaries.
- Bugs fixed: reachability gave up after five stair hops (people above the sixth storey "could
  not leave"); L-shaped buildings put stairs outside the outline; long wings gave 40 one-person
  rooms per floor; rooms in a corner were refused (walls straddle the edge); the floor switcher
  sat under the toolbar and over the before/after toggle; `/event-kinds` 404.
- Verified: 4-storey hospital drawn on the map → live AI test "This plan holds, confirmed by
  full simulations" with floor-aware attacks; three-floor hall built by ops simulated in the
  hardened Docker sandbox (1,260 people, all out). Checks: 580 Python, 129 vitest, 18 sim,
  Playwright 7/7 with the real model (guided journey intermittent once, see G3-06).
- Open: Overpass servers were down all afternoon (building clicks fail, "Draw an area" works);
  groups, pre-movement and routes are not simulated yet (G2-01..03).

## 2026-10-15 — Everything on one branch, tested

- Merged the last parked branches into `shahraz`: `feat/handover-extras` (seed check:
  `POST/GET /sessions/{id}/seeds`; one conflict in `routes_runs.py`, both sides kept) and
  `feat/day-of` (day-of observation and share-link tables, migration 0003). No branch on
  GitHub or local has work missing from `shahraz` now.
- Fixed before: three type errors that failed CI's `tsc -b` and `npm run build` (`tsc -p .`
  checks nothing in `web/`).
- Checks in a clean clone, as CI runs them: ruff, format, import contracts, mypy, pytest 583
  passed / 1 skipped; eslint (0 warnings), `tsc -b`, vitest 129, production build; sim image
  rebuilt, 18 sim tests. Migration 0003 on a fresh database and on a copy of the live one (25
  projects kept; downgrade and upgrade). Live stack migrated to 0003.
- Live: seed check on the 4-storey hospital test (key run after fixes, 3 extra seeds): 95% out
  in 4 min 29 s – 4 min 42 s over 4 runs, peak 1.2–1.5 people per m², nobody left inside.
  Playwright 7/7 with the real model and Docker.
- Work split updated (TEAM_TASK_ALLOCATION.md §12): seed check backend done; its screen is
  Saif's S-09; Ridwan takes the real-life examples (R-01).

## 2026-10-17 — Saif: building tools in the editor (G3-01)

- Expert view › Plan: the tool rail has a Building group (wall W, door D, room O, stairs S,
  walking route P) and a floor button (floor to edit, add a floor on top, remove a floor). Tools
  act on `editFloor`; on a multi-storey venue the 3D view shows that floor alone while a tool is
  active, and picking a floor in the floor switcher makes it the edit floor.
- Rules for each click live in `web/src/lib/buildTools.ts` (pure, 11 vitest cases) on top of the
  tested `venueOps.ts` builders. Walls and routes: click corners, Enter or double-click to
  finish, Backspace removes a corner. Rooms: two corners, or typed south-west corner and size.
  Stairs: click the middle, or type it; the panel says which floors they connect. Clicks on
  doors, walls and crowd areas count as clicks on the floor while a building tool is active.
- Right-hand panel shows the hint, the tool's options (door width, room door side, stair
  width/length/direction, route width and name) and the typed forms. Selected stairs show
  their floors and size with "Remove stairs". The simple check screen has a "Floors and
  rooms" card (add or remove a floor, link to the drawing tools). Help lists the new keys.
- Every change is a patch: a new version, a toast with Undo, Ctrl+Z / Ctrl+Shift+Z.
- Also: `ScriptCode.tsx`/`scriptCode.ts` and `AskAnything.tsx`/`askAnything.ts` clashed on
  case-insensitive disks (macOS `tsc -b` failed); helpers renamed `scriptSource.ts`, `askModel.ts`.
- Checks: eslint 0 warnings, `tsc -b`, vitest 140; Playwright `e2e/building-tools.spec.ts`
  (add floor → stairs → room → undo → redo, checked through the API) passes against the app
  with fake providers.

## 2026-10-17 — Saif: zone profile and event kind (G3-02)

- A crowd area's card (check screen and Expert view) edits who is there: groups with shares in
  percent (older people, children, wheelchair users, patients in beds, staff), the rest shown as
  general adults, a refusal above 100%; when they start moving (run default or a delay in
  seconds, with the event kind's usual delay when one is cited); and the route they walk (routes
  on the area's floor, or none). Each save is a `set_zone_profile` patch.
- The check screen has "Kind of event" (`useEventKinds`, offline fallback noted) with the usual
  mix and "Use the usual people mix in every area", which patches only areas with people that
  differ, in one version.
- Helpers in `web/src/lib/zoneProfile.ts` (7 vitest cases). Playwright `e2e/zone-profile.spec.ts`
  (hospital kind → usual mix on 2 areas → shares, delay and route on one area, checked through
  the API) passes against the app with fake providers.
