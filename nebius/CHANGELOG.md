# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
