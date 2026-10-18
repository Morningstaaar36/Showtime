# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Venues with storeys from a description**: the designer can now describe buildings with
  several storeys and basements, people per floor (or per named level such as "Lobby"), rooms off
  a corridor (with a room count), an atrium, stair cores near named walls or in the centre, exits
  on other levels, and basement exits that are stairs up to a street door. The solver builds them
  with the map's storey generator and places exactly the headcount described on each level.
  A stage can stand in the centre; repeated exit names are numbered ("South gate 1, 2, 3").
  Repair messages name the zone and level instead of internal ids (designer prompt v5).

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
