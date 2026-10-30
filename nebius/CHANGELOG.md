# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed and added (finishing round; Oct 30, afternoon)
- **One honest verdict for tall buildings.** A quick (tier 2) run stopped at 180 s, so a
  seven-storey building was judged "fails, 42 people still inside" while the fix loop said "no
  attack broke the plan". A quick run now lasts as long as the building needs: its instant
  estimate times `TIER2_HORIZON_FACTOR` (3: an instant estimate underrates stairs), at least `TIER2_MAX_SIM_S`, at most `MAX_SIM_S`.
- **Simulations really run side by side.** One machine-wide lock file let a single simulation run
  at a time whatever `SANDBOX_MAX_PARALLEL` said; it is now that many lock slots (default 2; 3 fit
  a 16 GB machine).
- **Redesign a saved plan in words** (`POST /projects/{id}/redesign`, Check your venue: "Not
  right yet? Tell the AI what to change"): the designer revises its own stored design in the same
  rounds, and the result is a new version you can undo.
- **A final plan confirmed by full simulations:** every retest of "Let the AI fix it" confirms its
  kept fixes with full runs, and a plan no attack broke counts as confirmed when its worst attack
  was simulated to the end with everyone out.
- **The plan critic gets each floor's exact counts** (people, exits, stair flights, fixtures) with
  the drawing, so it no longer reports labels it misread ("45 people drawn as 35").
- **Tests never touch the app's database.** A test that built the app state marked the running
  app's live test as "stopped"; every test session now has its own database and run folder.
- `make live-case CASE=…` runs any real case end to end through the running app (build, test, let
  the AI fix it) and writes the record next to the case file.

### Added (an AI design loop, real sites, and AI fixes until the plan holds; Oct 30)
- **Design rounds** (`DESIGN_ROUNDS`, default 3): the designer draws the venue from words, a plan
  checker measures it (`api/core/design_review.py`: ways out, walking distance, crowding, the
  fit-out the use needs, an instant evacuation estimate), a model that reads images looks at the
  drawn plans (`api/agents/plan_critic.py`, `MODEL_VISION`; off when empty), and the designer
  revises. The best round is kept and every round is shown in "How the AI designed this" (Check
  your venue and the describe preview). Building-code limits (one stair for 45 people) are noted,
  never "fixed": a real case stays the building it was.
- **The real site** (`api/orchestrator/site.py`): a description or case that names a place has
  its building looked up on OpenStreetMap; its real size goes back to the designer, and the notes
  say when the map had no outline.
- **Change it in words:** under a described preview, "Not right? Tell the AI what to change"
  revises that layout and keeps the rest (`POST /venues/design` with `request` and `previous`).
- **Let the AI fix it** (`POST /sessions/{id}/improve`, `IMPROVE_ROUNDS`, default 3): the
  simulator-proven fixes become a new version, the plan is tested again, and the loop repeats until
  no attack breaks it or no fix holds; each test is a normal session and version (Your plan).
- **Buildings that read as buildings:** dining fit-outs (kitchen, tables, toilets, lift) and
  enclosed stairwells, sizes from `api/data/fitouts.json`; an `add_stairwell` fix the blue team may
  propose; facades, slabs and fixtures in 3D.
- Real cases show their design round while they build (`GET /real_cases/{id}/progress`).

### Fixed (found by building Bailey Road from scratch; Oct 30)
- The plan critic could invent requirements ("add a street exit on floor 6"). The designer
  followed them, and the round that drifted furthest from the description was kept because its
  estimate was one second better. Now each critic issue must quote the description (others are
  dropped and listed), the critic is told which floors the image shows, and rounds are ranked by
  how well they match the description, never by a faster evacuation.
- The critic's plan image drew only stair landings, so it reported "no stair"; flights and their
  treads are drawn now.
- A fix that declared its new door as proposed construction (`new_objects`) was refused with
  "Configure the organizer plan first" on any venue without an organizer plan.
- The blue team never learned that the upper floors queue at one stair: its brief now has the
  simulator's notes (where people clogged) and the building's ways down, so it proposes a second
  stairwell where one is needed.
- A scenario script that read the crowd every step could crash the simulation (`unknown Agent`)
  once people left; scripts now read positions from the simulation itself.
- A layout that placed its own lifts got a second lift from the dining fit-out.
- Stairs in generated buildings: one flight per storey in a scissor core with a walkable pitch
  (they were 49° and stacked), the floor's own flights highlighted in the one-floor view, square
  kitchens and toilets, toilets with cubicles, and the camera fitting tall buildings.

### Removed (Nebius and the demo video; Oct 30)
- **Nebius:** the Token Factory LLM provider (`LLM_PROVIDER=nebius`), the Nebius Sandboxes
  runner (`SANDBOX_PROVIDER=nebius`, `api/adapters/nebius_sandbox.py`) and the `contree-sdk`
  dependency, every `NEBIUS_*` setting, the Nebius preset in `api/data/llm_presets.json`,
  `make smoke-nebius`, `make deploy-nebius` (`deploy/nebius_vm.sh`), `make use-nebius`,
  `make verify-nebius-llm` / `verify-nebius-sandbox`, `docker-compose.nosocket.yml`, and the
  Nebius-only docs (`NEBIUS_SWITCH.md`, `WHEN_YOU_GET_THE_KEYS.md`, `FEEDBACK.md`). The AI runs
  on NVIDIA Nemotron through OpenRouter (or any OpenAI-compatible API) or a local llama.cpp
  server; simulations run in local Docker. The provider registries stay, so another provider is
  still one module in `api/adapters/providers/` ([docs/PROVIDERS.md](docs/PROVIDERS.md)).
  If your `.env` has `NEBIUS_*` lines, delete them (they are ignored).
- **Demo-video tooling:** `scripts/demo_cut.py`, `web/e2e/record-demo.mjs`, `web/e2e/demo-tour.mjs`,
  `web/e2e/explore-scripts-beat.mjs`, `docs/VIDEO_SCRIPT.md` and the hackathon submission
  checklists. `docs/REVIEW.md` and `docs/PROGRESS.md` moved to `docs/archive/`.

### Added (sandboxes, evidence, providers, any venue; Oct 25–26)
- **Sandboxes you can see:**
  - a header badge with what each sandbox guarantees;
  - a live sandbox feed on AI at work (queued, running, finished, refused, killed, restarted);
  - a Sandboxes tab on the plan, with the AI-written scenarios, their code and outcome, Rewind
    and Stress test at scale;
  - Help › Sandbox shows `make sandbox-proof`'s recording: 14 attacks on the real container
    and what stopped each.
- **Evidence:** the red team can search the web (Tavily) and may cite only URLs that came back;
  every source carries an origin badge (incident dataset or live web); an Evidence panel on
  the plan; an evidence desk for the brief; the agents' tool calls on AI at work.
- **Key-ready providers:** LLM, sandbox and search providers are plug-ins in registries, one
  file each (`api/adapters/providers/`).
  - `make verify-live` (and `make verify-<service>`) makes one real call per service and writes
    `docs/LIVE_STATUS.md`.
  - A missing key gives a clear "not configured" state; an unconfigured sandbox falls back to
    Docker and says so.
- **A designer for any venue** (prompt v11, a neutral site model): metro stations, mosques,
  malls, airports, markets; new feature kinds and event kinds; the brief's headcount is held;
  real cases pass their documented crowd.
- **Rules standing in are recorded:** when the model doesn't answer, the plan and the report say
  which parts built-in rules wrote (`stood_in`).

### Changed
- **Switching to Nebius is `.env` only:**
  - `LLM_PROVIDER=nebius` plus the key; model ids left from another provider take the Nebius
    preset on their own.
  - Nebius Sandboxes need `NEBIUS_PROJECT_ID`, and start every run with the network off.
- **The quickstart needs three `.env` lines**, and `make setup` skips the 6 GB local model when a
  hosted one is configured.
- The number check covers red- and blue-team titles and rationales.
- Incident search terms and the template order come from data files.

### Fixed (Chrome, Oct 26)
- **Script outcomes:**
  - a script crash reads "Failed: error in its code", not "Stopped by a limit";
  - exit 137 reads "out of memory, or stopped from outside";
  - a run restarted after its container stopped says so.
- **Error messages:**
  - a paused hosted model with no local model is reported as unavailable, with when it ends;
  - a rejected key is named in errors and toasts.
- **Layout and accessibility:**
  - the floor switch no longer covers the sticky header;
  - the Rewind table fits its panel;
  - AI at work no longer scrolls sideways on phones;
  - the feed's state words meet WCAG AA contrast.
- **Content:**
  - a real case shows its sources while the first test runs;
  - Tavily is asked for publication dates.

### Fixed (live browser check, Oct 25)
- Autopilot: the venue now holds the event's headcount. The Brief agent's layout text can leave
  the number out, and the designer then filled the floor to capacity (1,500 asked, 2,800 built).
  The brief's headcount now goes to the designer, and a layout more than 5 % off is sent back for
  repair (designer prompt v8, which also keeps a walkable ramp as a way out).
- Red team: a title that only repeats the failure-map target ("Adaptive scenario (code) · West
  side: exits …") is sent back for a real name; if the model keeps it, the rationale names it.
- Autopilot's "Confirming the fixes" step reports time above danger density next to the
  evacuation time, so a fix that trades a few seconds for no danger doesn't read as worse.
- Verdict badge says which worst case stopped early ("without the fixes" / "with the fixes").
- Scenario cards show "N still inside" instead of a blank when a run stopped with people inside.
- Per-floor chart ends at zero when the run reports everyone out.
- No 404 requests for an estimate's replay, for the pressure grid of runs simulated before it
  existed, or for the failure map of sessions saved before it existed.
- Check page: floor chips wrap instead of hiding upper floors in a side scroll; estimated sides
  of the before/after rows read "~4:44" next to their "Estimate" badge instead of wrapping.

### Added
- **Crowd pressure and turbulence** (Helbing, Johansson & Al-Abideen 2007): every simulation writes
  `pressure.bin` / `pressure_index.json` (same layout as the density grid, GET
  `/runs/{id}/pressure`) and reports `peak_pressure`, `time_turbulent_s` (pressure ≥ 0.02/s² in a
  crowd of at least the warning density) and turbulent hotspots. Fruin level of service A–F as
  shares of person-seconds (`los_share_A` … `los_share_F`).
- **Scenario library**: 18 named what-ifs (GET `/api/v1/scenarios?project_id=…`) with targets
  picked from the venue, including multi-storey ones (stairwell lost to smoke, smoke on the fire
  floor, phased evacuation, firefighters on the stairs, lift out of service, more
  mobility-impaired people). The sweep accepts `{"scenarios": [...]}`; the default is still the
  original six.
- Scenario events: `block_exit`, `unblock_exit`, `counterflow` and `one_way` take a stair id;
  `slowdown` takes a `floor_id`; new `mobility_share` (a share of people at a given speed, slower
  on stairs too).
- **Venues with storeys from a description**: the designer can now describe buildings with
  several storeys and basements, people per floor (or per named level such as "Lobby"), rooms off
  a corridor (with a room count), an atrium, stair cores near named walls or in the centre, exits
  on other levels, and basement exits that are stairs up to a street door. The solver builds them
  with the map's storey generator and places exactly the headcount described on each level.
  A stage can stand in the centre; repeated exit names are numbered ("South gate 1, 2, 3").
  Repair messages name the zone and level instead of internal ids (designer prompt v5).
### Changed
- **Your plan is tabbed and visual**: Overview (traffic-light verdict ring, four key numbers with a
  target bar, the density scale, the people-inside curve and the time needed, before vs after
  fixes as paired bars, the worst moment replaying in 3D), Replay (before, after or side by side on
  one clock, every scenario), Scenarios (cards, the scenario library and sweep, deeper checks as
  tiles), Fixes (cards with before → after numbers and a switch each), Floors (one small plan per
  storey with stair use and when it clears) and Hand over (report, map, checklist, data, cost). The
  AI's prose sits behind "Read the AI's summary"; the tab is in the URL (`?tab=`).
- **Buildings of 3+ storeys open on one floor in focus** with the others ghosted (outlines, faint
  plates, no labels), every stair highlighted, room walls cut low, and a lift-style floor switcher;
  "All floors" draws clean floor plates, "Spread apart" stays. People on other floors stay as faint
  markers in replays. Map neighbours standing on the venue's own footprint are no longer drawn.
- **AI at work is a live pipeline** (red team → screen → simulate → fix → judge) with a scoreboard,
  an AI usage meter and attack cards dealt in.
- **Home** adds "Events like yours" (concert, hospital fire drill, school drill, stadium, festival
  pandal, mall, nightclub, street party, conference): tested samples open with results, the others
  fill in "Describe it". **Check your venue** has floor tabs, door chips and people steppers.

### Added
- Turbulence layer toggle on the replay (GET /runs/{id}/pressure, same encoding as density) and the
  scenario library (GET /scenarios, POST /projects/{id}/sweep with chosen ids); both stay hidden on
  servers that answer 404. A slot for the red team's failure map in Scenarios.

### Fixed
- **Basements in the simulation**: floors now run in stair order, so people climbing out of a
  basement reach the street level instead of arriving after it was simulated; stairs leading up
  are drawn and labelled the right way in 3D and counted in safe capacity.
- **Instant estimate in buildings of 3+ storeys**: routes now follow chains of stairs, so upper
  floors are no longer "stranded"; the 4-storey hospital sample went from 298 people with no route
  to 95% out in 200 s (simulation: 223 s). Each stair's capacity window starts when people reach it.
- **Safe capacity with stacked stairwells**: the tightest storey's stairs govern instead of the sum
  of every flight (4-storey block: 960, not 1,560).
- **Simulation with every exit blocked** reported 0 people, all evacuated, "ok": people who could
  not be placed because no exit was open now count as not evacuated and trapped.
- **Countdown**: a scenario or user-set hazard (seconds after the alarm) no longer prints a wrong
  "start evacuating by" clock time, and is never compared with a forecast hazard measured from the
  event start. Wind: gusts already over the limit when the window opens hit at the start, and the
  "no hazard" text quotes the peak inside the window.
- **Undo**: removing a zone restores its people mix, start delay and route; undoing a first start
  time clears it.
- **Scenario sweep** from the API skipped every scenario ("no running event loop").
- **Red-team sessions** could stay "running" forever on an LLM replay miss or a failure while
  finishing, locking the project; attack ids could repeat across rounds; session config could
  override budgets (and `"lots"` gave a 500, now 422).
- Runs and sessions left running by a server restart are marked failed / stopped at startup;
  stopping one user of a shared run no longer cancels it for the others; reports of imported
  projects keep their baseline and final runs; `GET /weather` with a bad date gives 422.
- Forecast cache refreshes after 3 h (kept as a fallback when offline); Nebius sandbox no longer
  uploads a stale `result.json`; trajectories of sites over ~650 m are no longer clamped.
- Web: clearing a number field no longer saves 0; shortcuts no longer fire in dropdowns; the 3D
  view stays on the run you picked during a live session; geometries are disposed; Autopilot "Try
  again" no longer shows "Stopping…"; Undo toasts always undo their own edit; Ask shows the answer
  for the hotspot asked about; "Not all% of" wording; event streams back off and stop on 404.

### Added
- **How sure are these numbers?** (P2-04) on Your plan: the run the verdict rests on again with
  20% fewer and more people and walking 15% slower and faster (same seed, layout and scenario),
  with the range, which assumptions break the plan, and every run's basis
  (`/sessions/{id}/sensitivity`, `docs/ASSUMPTIONS.md`).
- **Chosen changes tested together** (P2-04): accepting only some kept changes simulates exactly
  those under the worst attack; the version counts as tested together, and can be confirmed, only
  after that run (`/sessions/{id}/together`).
- **Guided journey** (P3-01): Describe → Check your venue → AI at work → Your plan, with the
  studio kept as Expert view. Collaborative editor with existing/proposed openings, provenance,
  locks, AI patch preview and stale-evidence banners; `set_annotation` op and
  `POST /projects/{id}/patch/preview`.
- Event Copilot rebuilt as a **LangGraph** state graph, drawn live in the Copilot window; new
  **scenario sweep** node (six what-ifs in sandbox branches) and **Safety officer** agent.
- Planning score (A–F, explained), what-if lab, scenario matrix in Simulate, safety officer card
  in Plan, Showtime lights night scene, narrated tour, automatic fallback to the local model.
- **Event Copilot**: one sentence → brief → real site or designed venue → event layout →
  estimates → project → stress test, streamed live from the Projects page.
- **Plan for the day** estimates with cited planning ratios (`api/data/planning_ratios.json`):
  safe capacity, exit width, stewards, first aid, toilets, fencing, barrier, budget; in Plan and
  in the report. Editable event details (`set_event`: duration, alcohol, audience, start) and
  unit prices (Settings).
- **Site layout solver**: stage, crowd barrier, front-of-house, toilet blocks, bars and crowd
  bands placed on real sites.
- MapLibre 3D map (OpenFreeMap) with one-click selection of buildings and areas; Overpass
  queries race several servers with a vector-tile fallback; real neighbouring buildings and
  OpenStreetMap ground in the 3D view; balconies with columns and railings; water obstacles.
- **Describe it:** create a venue from a plain-language description. The designer agent writes a
  layout specification (sizes, walls, regions; never coordinates), a solver places stage, exits,
  stair, features and zones, and the geometry checks run with one repair round.
- **Real place:** search OpenStreetMap, pick a building (indoor) or a park, square, campus or a
  drawn box (open-air). Buildings, water and fences become obstacles, paths and gates crossing
  the edge become exits, and location and time zone are set for the wind check.
- `LLM_PROVIDER=openai` for any OpenAI-compatible API (OpenRouter, DeepSeek, GLM …) with its own
  badge label, `LLM_EXTRA_BODY` for provider options, and zero cost for `:free` models.

### Fixed
- Accepting a red-team plan no longer discards edits or locks made after the test started; a plan
  for an older geometry is refused (`409 stale_plan`).
- Text edits return `503 llm_unavailable` instead of a server error when the model is down.
- New exits never overlap existing ones; a slow map lookup can no longer replace a newer selection.
- Answers that echo the JSON schema's shape are unwrapped instead of failing.
- Hosted model calls have a total deadline (a gateway that keeps a slow request alive no longer
  hangs a red-team session).

## [0.1.0] - 2026-10-08

### Added
- Projects with versioned venues (every save is a version), undo/redo, restore, duplicate,
  import and export as `.showtime.zip`, autosave, and three sample projects with finished
  red-team sessions.
- 3D workspace (React Three Fiber): Plan, Simulate, Red Team and Report modes; section-cut
  walls, exit gates, stage truss and roof, zones, stairs, exploded two-floor view.
- Editing by text (Venue agent on NVIDIA Nemotron → validated patch) and by drag and draw
  (barrier, zone, exit, measure); live geometry checks and an example rules pack.
- Instant estimate (Tier 1: geodesic distances, min-cost flow, queues) and "Break it yourself".
- Crowd simulation with JuPedSim in a network-less sandbox (Tier 2 screening, Tier 3
  confirmation): density heatmap with danger contour, hotspots, evacuation time (95%), exit
  flows, two-floor stair chaining, scenario events, time travel.
- Red Team Night: red team grounded in 388 recorded crowd accidents (plus optional Tavily
  search), blue team fixes, measured acceptance, multi-round escalation, Tier 3 before/after
  confirmation, number-checked judge, live branch tree, scoreboard, agent activity, cost meter.
- Wind hazard: Open-Meteo gusts vs a Pynite stage frame wind limit; countdown to the latest
  safe time to start evacuating.
- Ask the venue (Explainer agent with number check).
- Report (printable HTML/PDF), SVG evacuation map, JSON bundle.
- Provider adapters: local llama.cpp or Nebius Token Factory; Docker or Nebius Sandboxes;
  Tavily; Open-Meteo. Switch with `.env` only.
- Plugin architecture with 12 extension points, conformance tests, `make new-plugin`.
- Docker Compose stack, Makefile, memory watchdog, smoke tests, ADRs and docs.
- Guardrails found by testing: attack titles cannot name features the venue lacks; machine
  ids are shown as venue names; Plan prefers a confirmed simulation over the formula; the
  countdown names its evacuation-time basis.
- Compact demo packs (delta-coded trajectories) tracked by hash; vitest, Playwright journeys,
  screenshot self-review, CI workflow and pre-commit hooks.
