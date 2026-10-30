# Showtime: Red Team Night

[![Licence: Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)

> This is the full feature tour. Start with the [main README](../README.md) (what it does, the
> Bailey Road example, quickstart, architecture); a 5-minute path is in
> [docs/JUDGE_GUIDE.md](docs/JUDGE_GUIDE.md).

**AI agents try to break your event plan. The red team can write attacks as code, and that code
only ever runs in a sealed sandbox. A physics simulator, not the AI, decides what breaks. Then the
AI proposes fixes, and only the fixes the simulator confirms are kept.**

- **Agents that act:** twelve NVIDIA Nemotron agents. They build the venue from one sentence
  (designing, checking and revising it in rounds),
  attack it (menu attacks, plus at most one scenario written as code per round), look up real
  incidents, propose fixes and write their own analysis code.
- **Sandboxes at the core:** every simulation and every AI-written script runs in a throwaway
  container. It has no network, a read-only system, memory, CPU and process limits, and no keys.
  [14 attacks on it, and what stopped each](docs/SANDBOX_PROOF.md).
- **Evidence:** attacks cite real crowd accidents (395: the Feliciani dataset's 388 plus 7
  well-known ones). Numbers come from the simulator, formulas and cited data, and every number in
  AI text is checked against the computed results. Calibrated on a real bottleneck experiment, the
  simulator's flow is within about 6 % of it at every width; calibration and check come from that
  same experiment ([validation](docs/VALIDATION.md)).

![AI tests it: the red team's attacks running in sandboxes, live](docs/screenshots/step7/work-sandbox-feed.png)

**Run it:** [quickstart](#quickstart) · **Status:** it runs on local Docker sandboxes and on
NVIDIA Nemotron through OpenRouter (or a local llama.cpp server). Tavily web search is built as a
plug-in but **not run live** (no key yet: [live status](docs/LIVE_STATUS.md)).

> Planning aid, not a safety certification.

## Why

Crowd crushes happen about once a month worldwide (Feliciani et al., *Safety Science* 2023).
Itaewon (2022): 159 deaths in a 3.2 m alley where two flows met. Indiana State Fair (2011): a
stage roof collapsed in a 59 mph gust; nobody had checked its ballast against the forecast.
Professional crowd modelling is expensive and needs specialists, so most events never get
stress-tested. Showtime makes "what happens if…?" a two-minute question for any organizer.

## What you see

![Your plan: a 4-floor hospital with its patients and staff, tested by the red team](docs/screenshots/overhaul/hospital-overview.png)

| **Failure map**: every way the plan broke, by hazard and floor (Rainbow red teaming) | **Fixes**, each simulated on its own; none may make an outcome worse |
| --- | --- |
| ![Failure map](docs/screenshots/overhaul/failure-map.png) | ![Fixes](docs/screenshots/overhaul/school-fixes.png) |
| **Floors**: when each storey clears and how many use each stair | **Scenarios** the AI and the rules tried, with the incident that inspired each |
| ![Floors](docs/screenshots/overhaul/school-floors.png) | ![Scenarios](docs/screenshots/overhaul/hospital-scenarios.png) |
| **Start from your event**: map, one sentence, or a use case | **AI tests it**: the red team, the simulator and the judge, live |
| ![Home](docs/screenshots/overhaul/home.png) | ![AI tests it](docs/screenshots/overhaul/work-live.png) |
| **The AI team**: the Nemotron agents, the model each runs on, the tools each may use | **Real cases**: our descriptions of published reports, built by the designer and simulated (illustrations, not evidence) |
| ![AI team](docs/screenshots/overhaul/ai-team.png) | ![Real case](docs/screenshots/overhaul/real-case-itaewon.png) |
| **Test modes**: Quick, Standard, Deep or Offline | |
| ![Test modes](docs/screenshots/overhaul/test-modes.png) | |
| **The real site in 3D**, laid out for the event | **Event Copilot**: one sentence to a tested plan |
| ![Site](docs/screenshots/site-3d.png) | ![Copilot](docs/screenshots/copilot.png) |

## What it does

The core loop, in the order you meet it:

- **Failure map** (Red Team Night): the red team attacks the plan, each attack runs as a crowd
  simulation in its own sandbox, and the map shows every way the plan broke, by hazard and by
  floor, exit or side. Attacks cite real accidents (the Feliciani dataset's 388, 1900–2024, plus 7 well-known ones with
  Wikipedia sources).
- **Rainbow search**: how the red team fills the failure map. It is asked for the empty cells,
  and a cell is kept only on simulated metrics, so the search cannot flatter its judge (after
  Rainbow Teaming, NeurIPS 2024: [docs/RAINBOW.md](docs/RAINBOW.md)).
- **AI-written scenarios**: besides its menu attacks, the red team may write one new failure per
  round as a small Python program ("close the stairwell when its queue passes 40 people").
  **Show the code** displays it. A static
  check refuses unsafe code before it runs, and the sandbox stops what slips past.
- **Fixes the sandbox proves**: the blue team proposes fixes, each fix is simulated again, and
  only measured improvements are kept. Every number in the judge's text must appear in the
  computed results.
- **Rewind the worst moment**: the crowd is saved at its most dangerous second. "Do nothing" and
  each response then run from that same second, side by side.
- **Stress test at scale**: every attack against your plan, and each kept fix against several
  random crowds, fanned out over sandboxes with live counters.
- **Evidence panel**: what each attack is grounded in, with its origin (incident dataset or live
  web), and the agents' tool calls in *AI tests it*. Web search switches on with a Tavily key
  (built and tested with a fake client; not run live).
- **Real cases**: Love Parade, Hillsborough and Itaewon. We wrote each case's description
  (sizes, gates, crowd groups and where they walk) from published reports; the designer builds
  the venue from that text, and it is simulated. They are illustrations, not evidence
  ([docs/REAL_CASES.md](docs/REAL_CASES.md)). Add your own with **Add a real case** on Home: it is
  saved, and opens the same way.

Around it:

- **Three ways to start a venue**: a **real place** (search, then click a building for an indoor
  event or a park, square or campus for an open-air one, on a MapLibre 3D map), **describe it**
  (the Designer agent writes sizes, levels, zones and routes; a solver places every wall, exit,
  stair and zone and the checks run), or a **template**.
- **Event Copilot** (a LangGraph agent graph): one sentence → brief → the real site or the
  Designer → layout solver → planning ratios → project → simulation → a **scenario sweep** (what-ifs
  from an 18-scenario library, each in its own sandbox) → a **Safety officer** agent with
  prioritised, number-checked actions. The graph is drawn live as nodes run.
- **Plan for the day**: safe capacity (floor space × planning density; exits by the Green Guide
  width × flow × time method; stairs), exit width needed, stewards, first aiders, toilets (Purple
  Guide table by duration and alcohol), fencing, barrier and a budget. Every ratio is cited.
  A **planning score** (A–F) and a **what-if lab** recompute instantly.
- **3D venue** (React Three Fiber): section-cut walls, exits with direction arrows, stage truss
  and roof, zones, stairs, several floors. Edit by **typing** ("add a 3 m exit on the east wall";
  the Venue agent turns it into a validated patch) or by **dragging**. Every save is a version
  with undo/redo.
- **Instant estimate** (milliseconds): geodesic walking distances, min-cost-flow exit
  assignment and queues. Powers **Break it yourself**: click an exit to block it and see the
  effect immediately.
- **Confirmed by simulation**: every person simulated with **JuPedSim**; density on a 1 m grid,
  hotspots, evacuation time (95%), exit flows; replayed in 3D with a colour-blind-safe heatmap
  and an outlined danger contour (5 people per m²). Bodies are hard discs; the squeeze rule
  shrinks them at a clogged door so the model does not deadlock, so peaks above about 6 per m²
  flag a severe jam, not a measured crush density ([ASSUMPTIONS](docs/ASSUMPTIONS.md)).
- **Wind hazard**: Open-Meteo gust forecast versus the stage's wind limit from a **Pynite**
  structural frame model (uplift, sliding, overturning) → *start evacuating by 10:56* in the
  Wellington sample.
- **Ask or change anything**: "why is this red?" quotes only numbers from the run; the analyst
  answers questions by writing code that runs in the sandbox on the simulation data.
- **Report and handover checklist**: printable HTML/PDF with verdict, countdown, evacuation map
  (SVG with exit arrows), attacks with sources, fixes, assumptions with sources; a checklist with
  open conditions, staff actions and a sign-off line.
- **Test modes**: Quick, Standard, Deep, and Offline (no model: rule-based attacks and fixes,
  still simulated).

Honest by design: **the language model never produces a number shown as a measurement.** A
number check rejects AI text that quotes a number missing from the tools' output (it cannot tell
whether a number that is there was quoted in the right place).
Densities, times, forces and wind limits come from the simulator, formulas or cited data; the
UI always says whether you are looking at an *instant estimate* or a result *confirmed by
simulation*.

## How it works: Nemotron agents decide, sandboxed tools measure

Showtime is a multi-agent system. Eleven NVIDIA Nemotron agents make the decisions, in five
stages: **build** (Brief, Designer, Editor, Router), **attack** (What-if planner, Red team),
**defend** (Blue team), **judge** (Judge, Safety officer) and **explain** (Explainer, Analyst).
The AI team page lists twelve entries because the Analyst's planning and answering steps are
shown separately; the Router is a small classifier with a keyword fallback. Tools produce every
number: a layout solver turns a design into exact geometry, an instant estimate screens ideas in
milliseconds, and the JuPedSim crowd simulator tests every scenario and every fix in its own
sealed sandbox (a Docker container with no network). A number checker rejects agent text that quotes a number the tools did
not produce. Venues come from a sentence, a map, a template or a real case's description (the
templates and real-case descriptions are written by hand); the agents and tools do the rest. The
live team, with the model each agent runs on, is at `/team` in the app and `GET /api/v1/agents`.

**Models.** Roles map to models in `.env` (`MODEL_FAST`, `MODEL_LONG`, `MODEL_MAIN`,
`MODEL_JUDGE`, `MODEL_VISION`), filled from the provider presets in `api/data/llm_presets.json`:

| Role | Agents | OpenRouter preset (runs live) |
| --- | --- | --- |
| fast | Red team, What-if planner, Router | Nemotron 3.5 Lightning (free) |
| long | long incident texts | Nemotron 3.5 Lightning (free) |
| main | Brief, Designer, Editor, Blue team, Explainer, Analyst | Nemotron 3 Ultra (free) |
| judge | Judge, Safety officer | Nemotron 3 Ultra (free) |
| vision | Plan critic (reads the drawn floor plans) | Nemotron 3.5 Super VL (free) |

Results logged up to 2026-10-19 used Nemotron 3 Super on OpenRouter, until its free endpoint
returned 404. `MODEL_FALLBACK` is tried when a role's model fails at the provider, and
`OPENAI_COMPAT_API_KEY_FALLBACK` when a key runs out. JSON is asked for in the prompt (the
preset sets `LLM_SUPPORTS_JSON_SCHEMA=false`), validated with Pydantic and repaired with one extra
call. Model replies are cached: with the default `LLM_CACHE_MODE=record_replay`, a call identical
to an earlier one is replayed from `cache/llm/`, and Your plan › *How this plan was made* says
how many were.

**Test modes** (above *Test this plan*): **Quick** (one round, a few attacks), **Standard** (the
AI attacks and fixes; the default), **Deep** (three rounds on the improved plan, findings
confirmed in full) and **Offline** (no model: rule-based attacks and standard fixes, still
simulated).

## Engineering novelty (and the papers behind it)

| Idea | What Showtime does | Measured here |
| --- | --- | --- |
| **Rainbow red teaming with a physics judge** (Samvelyan et al., *Rainbow Teaming*, NeurIPS 2024; *RainbowPlus*, 2025) | The red team fills a **failure map**: a MAP-Elites archive of hazard kind × place (floor, exit or side), keeping the two worst attacks per cell. Nemotron is asked to fill the empty cells. The fitness is a severity score from **simulated metrics only**, so the search cannot flatter its judge, the failure mode Rainbow Teaming reports for LLM judges. | Matched two-round sessions with Nemotron (mock simulator, same budget): the school wing's map went from 29 % to 57 % coverage and from 4 to 6 of 6 hazard kinds. Live with JuPedSim, a 3-storey school filled 8 of 14 cells, every one a confirmed break. [docs/RAINBOW.md](docs/RAINBOW.md) |
| **Crowd pressure, the turbulence warning** (Helbing, Johansson & Al-Abideen, *Phys. Rev. E* 75, 046109, 2007) | Every simulation computes crowd pressure P = ρ·Var(v) per cell and time, the measure that rose before the 2006 Mina crush, with their 0.02/s² threshold. It shows as a **Turbulence** layer in the replay, together with Fruin level-of-service shares (A–F). The layer is **indicative**: the model has no pushing forces. | A 0.8 m bottleneck: 28 s of turbulence, against none for a 6 m exit. A 3-storey school with 960 children: 40 s of turbulence on its stairs. |
| **Describe → solve → check → repair for whole buildings** (in the spirit of Text2BIM, *J. Comput. Civ. Eng.* 2026) | One sentence becomes a multi-storey building: storeys and basements, people per floor, wards or classrooms off a corridor, atriums, stair cores. Nemotron writes only the structure; a solver builds the geometry and the checks send errors back once. | Live with Nemotron 3 Super (OpenRouter, 2026-10-19, one run per description): 12 of 12 test descriptions built correctly (a 5-storey office, a 4-floor hospital, a 3-level mall, a basement nightclub, a 10-storey hotel, a metro platform, …). Before this, every multi-storey description collapsed to one floor. |
| **Who is in the crowd** | Older people, children, wheelchair users and patients in beds walk at cited speeds and take their real width, down the stairs too. The replay draws each kind with its own shape. | The 4-floor hospital takes 207 s to get 95 % out with its patients and staff, against 109 s if everyone moved like a healthy adult. |
| **Scenarios for buildings** | 18 named what-ifs with targets picked from the venue: a stairwell lost to smoke, firefighters climbing the stairs, phased evacuation, a power cut, a gate closed, a late surge… | 3-storey office, 300 people: losing one stairwell raises the time to get 95 % out from 104 s to 174 s (+68 %). |

## Technology used

| Technology | Role in Showtime |
| --- | --- |
| **NVIDIA Nemotron** (Nano 9B v2 locally; Nemotron 3.5 Lightning, 3 Ultra and 3.5 Super VL hosted on OpenRouter) | Twelve agents (see *How it works*), among them: **Brief** (one sentence → event brief for the Copilot), **Designer** (description → layout spec that a solver builds and the checks verify, revised in rounds), **Plan critic** (reads the drawn floor plans; may only raise what the description states), **Editor** (text → validated edit ops; 12/12 on our scripted edits with the local model), **Red team** (attacks grounded in incidents), **Blue team** (fixes), **Judge** (final plan text, number-checked), **Explainer** ("Ask the venue"). Roles map to models as in the table above. JSON is asked for in the prompt, validated with Pydantic and repaired once. |
| **LangGraph** | The Event Copilot is a compiled `StateGraph` with conditional routes, checkpointing and custom streaming; `GET /api/v1/copilot/graph` serves its structure, which the UI draws live. |
| **Tavily** | A search plug-in: the red team searches (basic depth, up to 5 results) for incidents like the venue's and may cite only URLs that came back; the evidence desk looks up capacity and guidance for the brief. Cached, capped per session, every source labelled with its origin. Built and tested with a fake client only; **not run live** (no key; `make verify-tavily`), so we claim no live results. Without a key the app says web search is off and the red team cites the incident dataset. |
| **JuPedSim, PedPy, Pynite, Open-Meteo** | Crowd simulation, crowd metrics, stage frame model, gust forecasts. |
| **OpenStreetMap, OpenFreeMap, MapLibre** | Real sites: place search (Nominatim), buildings, water, paths and entrances (Overpass, with OpenFreeMap vector tiles as fallback), the 3D picking map and the street-map ground in the 3D view. |

Every simulation and every AI-written script runs in a local Docker container with
`--network=none`, a read-only system, memory, CPU and process limits
([docs/SANDBOX_PROOF.md](docs/SANDBOX_PROOF.md)). Providers and keys:
[docs/PROVIDERS.md](docs/PROVIDERS.md); hosting on any Linux server:
[docs/HOSTING.md](docs/HOSTING.md).

## Quickstart

Needs only Docker (with Compose v2) and `make`. A free key from openrouter.ai gives the AI
(NVIDIA Nemotron); without one, choose **Offline** above *Test this plan*.

```bash
cp .env.example .env    # then set OPENAI_COMPAT_API_KEY=<your OpenRouter key> in .env
make up                 # builds the sandbox image, the API and the web app, fetches the incident data
# open http://localhost:5173
```

Four sample projects install automatically with their finished red-team sessions, so you can
explore immediately. A 5-minute path is in [docs/JUDGE_GUIDE.md](docs/JUDGE_GUIDE.md); the guided
tour for organizers is in [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md); the presenter script is
in [docs/DEMO.md](docs/DEMO.md). Stop with `make down`. To host it on a server (HTTPS and a
password): [docs/HOSTING.md](docs/HOSTING.md).

**Another provider or Tavily:** `.env` only, then `make verify-live`
([docs/PROVIDERS.md](docs/PROVIDERS.md)).

### Developer setup

For `make check`, `make dev` or the local model, install the host toolchain (uv, Python 3.12, web
deps, the sandbox image and the incident dataset, all inside this folder):

```bash
make setup            # host Python and Node toolchain
make dev              # API + Vite natively (stop: make dev-down)
make verify-live      # optional: one real call per service, written to docs/LIVE_STATUS.md
```

The local model instead of OpenRouter: set `LLM_PROVIDER=local`; `make setup` then also fetches
llama.cpp and Nemotron Nano 9B v2 (≈ 6 GB), started with `make llm-up` (≈ 6.4 GB VRAM). Other
targets: `make test`, `make test-web`, `make e2e`, `make smoke`, `make calibrate`, `make plugins`,
`make mem`, `make help`. Apple Silicon test profile: [docs/archive/README_INTERNAL_SECTIONS.md](docs/archive/README_INTERNAL_SECTIONS.md).

## Architecture

A modular monolith with 12 plugin extension points (edit ops, scenario events, hazards, rules,
incident sources, exporters, importers, engines, agents, tools, providers, hooks); built-in
features are plugins too. FastAPI + SQLite (Alembic) + SSE; React 19 + R3F + React Flow +
TanStack Query; JuPedSim in a sandbox image. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/EXTENDING.md](docs/EXTENDING.md), decisions in [docs/adr/](docs/adr/).

## Numbers you can trust (and their limits)

Every default (walking speed, body size, flows, thresholds, wind coefficients) is listed with
its source in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) and printed in each report. The engine
was calibrated against published flows (door flow 1.1–1.5 people per metre per second) and its
known artefacts were measured and fixed (doorway plugs, corner deadlocks), see
[docs/archive/PROGRESS.md](docs/archive/PROGRESS.md). The time gap to the person ahead was calibrated on the
Jülich 2006 bottleneck series and checked on other widths of the same series
([docs/VALIDATION.md](docs/VALIDATION.md)). Instant estimates are compared with simulations per
template (`make calibrate`) and the ratio is printed in reports.

## Tests

`make check` (lint, types, import boundaries, fast API tests), `make test` (all Python tests,
including the simulator; needs Docker), `make test-web` (vitest) and `make e2e` (Playwright
journeys, against the running app). CI runs the same checks: `.github/workflows/ci.yml`.

## Docs

[Judge's guide](docs/JUDGE_GUIDE.md) · [Pitch](docs/PITCH.md) · [Hard questions](docs/QA.md) ·
[Demo script](docs/DEMO.md) · [Testing guide](docs/TESTING_GUIDE.md) · [User guide](docs/USER_GUIDE.md) ·
[Architecture](docs/ARCHITECTURE.md) · [Extending](docs/EXTENDING.md) ·
[Assumptions](docs/ASSUMPTIONS.md) · [Providers](docs/PROVIDERS.md) · [Hosting](docs/HOSTING.md) ·
[Real cases](docs/REAL_CASES.md) · [Validation](docs/VALIDATION.md) · [Live status](docs/LIVE_STATUS.md) ·
[Handoff](docs/HANDOFF.md) · [Security](SECURITY.md) · history: [progress log](docs/archive/PROGRESS.md), [archive](docs/archive/) ·
[Licences](docs/LICENSES.md)

## License

Apache-2.0 (see [LICENSE](LICENSE)). Third-party licences: [docs/LICENSES.md](docs/LICENSES.md).
