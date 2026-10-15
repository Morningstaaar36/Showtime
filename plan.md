# Showtime: Red Team Night — End-to-end plan to win the Nebius x NVIDIA Global AI Hackathon

> **Audience:** a Claude Code agent (or a human) who will implement the remaining work.
> **Read first:** `nebius/CLAUDE.md` (the original build brief, its hard rules still apply), then this
> file top to bottom. This plan **extends** CLAUDE.md; where they disagree, this plan wins for the
> items it names, and CLAUDE.md wins for everything else.
> **Paths:** all paths are relative to `nebius/` unless they start with `/` or `./` (repo root).
> All `make` targets run from `nebius/`.
> **Written:** 2026-10-09 (Friday). **Hackathon deadline:** 2026-10-30 23:00 GMT+6 (17:00 UTC).
> **Our submission target:** 2026-10-29 18:00 GMT+6. 2026-10-30 is reserve only.

> **Update 2026-10-15 (branch `shahraz`): generic venues.** Organizer testing showed the app was
> template-bound. Any building picked on the map now becomes every storey it has (stairs, rooms
> or open floors, occupant loads), venues can be built and edited floor by floor (11 new edit
> operations), and every 3D view can show one floor alone. People groups (patients, children,
> wheelchair users), pre-movement and march routes are in the contract; simulating them, a
> building's surroundings, the editor tools and the scenario viewer are allocated in
> [TEAM_TASK_ALLOCATION.md §11](TEAM_TASK_ALLOCATION.md#11-generic-venues-push-15-october-2026).
> **Same day:** all remaining work is re-split: Shahraz does the Nebius work only (Token Factory,
> Sandboxes, public demo); Ridwan and Saif share everything else, see
> [TEAM_TASK_ALLOCATION.md §12](TEAM_TASK_ALLOCATION.md#12-all-remaining-work-split-on-15-october-2026).
> Details and verified results: [nebius/docs/GENERIC_VENUES.md](nebius/docs/GENERIC_VENUES.md).

---

## Contents

- [The story (read first)](#the-story-read-first)
0. [How to work (rules for the implementing agent)](#0-how-to-work-rules-for-the-implementing-agent)
1. [What wins: requirements and judging criteria mapped to work](#1-what-wins-requirements-and-judging-criteria-mapped-to-work)
2. [Audit of the current state (verified 2026-10-09)](#2-audit-of-the-current-state-verified-2026-10-09)
3. [Human actions and accounts (blocking items)](#3-human-actions-and-accounts-blocking-items)
4. [Existing features: outline, acceptance criteria, tests](#4-existing-features-outline-acceptance-criteria-tests)
5. [New features: detailed specifications](#5-new-features-detailed-specifications)
   - [5A. Ease-of-use specification (every screen)](#5a-ease-of-use-specification-every-screen)
6. [The test system](#6-the-test-system)
7. [Milestones and schedule (Oct 9 – Oct 30)](#7-milestones-and-schedule-oct-9--oct-30)
8. [Deployment on Nebius (public demo)](#8-deployment-on-nebius-public-demo)
9. [Submission package: README, feedback, video, Devpost text](#9-submission-package-readme-feedback-video-devpost-text)
10. [Risks, fallbacks and the cut order](#10-risks-fallbacks-and-the-cut-order)
11. [Final pre-submission checklist](#11-final-pre-submission-checklist)
12. [Double-check log (what was verified while writing this plan)](#12-double-check-log-what-was-verified-while-writing-this-plan)

---

## The story (read first)

**The problem.** Planning a safe event is slow, expensive and specialist work. Someone draws the site, works
out capacity, exits, stewards and toilets from planning guides, and, for the few events that can afford it, a
consultant builds a crowd model in licensed simulation software and runs a handful of scenarios. That takes days
to weeks, so most organizers skip the simulation entirely, and on the night they manage the crowd by instinct.

**Our answer.** Showtime lets AI do that work. Describe the event in one sentence; AI agents running on
**NVIDIA Nemotron via Nebius Token Factory** build the venue (from OpenStreetMap or a description), estimate
capacity and staffing from cited guides, **drive existing, proven simulation software** (JuPedSim from
Forschungszentrum Jülich for crowds, PedPy for crowd metrics, Pynite for the stage frame, Open-Meteo for wind),
try what could go wrong (Red Team Night), fix the weak spots, re-simulate to prove each fix, and hand over a plan,
steward cards and a day-of console. The AI does the tedious parts; the simulators do the physics; no number is a
guess.

**Cost efficient by design.** Cheap, fast models for everyday calls (Nemotron Nano), a bigger one for edits and
fixes (Super), the biggest only for the final judgement (Ultra). Millisecond instant estimates screen every
scenario before any simulation runs; only promising ones get a quick simulation and only finalists a full one.
Results are cached by content, sandboxes branch from snapshots instead of rebuilding, and every run has a budget.
The app shows the **measured** cost of each plan (N16).

**One-line pitch:** *"Describe your event. AI builds it, simulates it, breaks it, fixes it, and hands you the plan,
in minutes, at a measured cost of cents."* (Say "cents" only after N16 measures it; otherwise quote the measured
number.) Tagline stays: *"Run the disaster before the gates open."*

**What this means for the product.**

1. **Simple by default.** Three screens: *Describe* → *AI at work* → *Your plan* (N14). Everything the studio can do
   today stays available in an **Expert view**, but a first-time user never needs it.
2. **One button does everything.** *Autopilot* (N13) chains the agents and simulators end to end.
3. **Cost is visible.** Every plan shows what it cost and how much work the AI saved by screening (N16).
4. **Honest.** "Planning aid, not a safety certification"; instant estimate vs confirmed by simulation is always
   labelled; cost and model claims come from measurements.

**Rule for the implementing agent:** every feature, screen and sentence in the video must serve this story. If a
feature does not make planning faster, cheaper, safer or more trustworthy for an organizer, it goes to Expert view
or to the cut list.

---

## 0. How to work (rules for the implementing agent)

1. **One milestone at a time** (section 7). Do not start the next milestone until the current one's
   "Done when" list is fully green. If a milestone runs over its dates, apply the cut order (section 10.3)
   instead of silently slipping.
2. **Gates after every change:** `make check`. After every feature: the feature's tests from section 5 and
   `make test`. After every milestone: the milestone gate in section 6.3, then an entry in
   `docs/PROGRESS.md` (what, commands, results, open issues) and a local commit (Conventional Commits,
   e.g. `feat(evidence): wire Tavily into the red team`). **Do not push** unless the human asks.
3. **Keep all of CLAUDE.md's hard rules** (section 2 there). The ones most at risk in the new work:
   - The LLM never produces a number shown as a measurement. Every new agent output that contains
     numbers goes through the number check in `api/agents/numbers.py`.
   - Every LLM output is JSON validated by Pydantic, one repair call, then a safe fallback.
   - Application code calls providers only through `api/adapters/`. No `import tavily`, `openai`,
     `contree_sdk` or `docker` anywhere else.
   - Everything is a plugin where an extension point exists (RulesPack, Exporter, HazardSource, …).
     Import boundaries are enforced by `.importlinter` (run inside `make lint`).
   - No secrets in git. Keys only in `.env` (gitignored). The browser never receives a key.
4. **Verify before you trust.** Items marked **[VERIFY]** are facts this plan could not confirm offline
   (model ids, SDK parameters, service limits). Write a 10-line probe in `scripts/`, run it, record the
   real answer in `docs/PROGRESS.md`, and follow the real API if it differs from this plan.
5. **Never claim a result you did not observe.** If a live test could not run (no key, no access),
   write `untested: <reason>` in HANDOFF, README and FEEDBACK. Judges test claims.
6. **Memory budget** (CLAUDE.md section 3) still applies on the 16 GB development machine: one simulation
   at a time locally, `make mem` before heavy steps, long jobs in the background with logs.
7. **Contracts first.** Any new API shape is a Pydantic model in `api/models/`, then `make types` to
   regenerate `web/src/types/generated.ts`. Any new table is an Alembic migration in
   `api/db/migrations/versions/`. Any new UI string goes into `web/src/i18n/en.json`.
8. **Product vocabulary** (CLAUDE.md 4A.4) is mandatory in UI copy: "people per m²", "evacuation time
   (95%)", "peak density", "exit", "blocked exit", "stress test", "red team", "fix", "instant estimate",
   "confirmed by simulation", "latest safe time to start evacuating".
9. **Designed states** for every new screen or panel: loading, empty, error, partial, offline
   (CLAUDE.md 4A.4). Every new feature is reachable by keyboard and has an accessible name.
10. **When blocked more than 3 attempts:** use the fallback in section 10.2, log it in `docs/BLOCKERS.md`,
    move on.

---

## 1. What wins: requirements and judging criteria mapped to work

### 1.1 Hard submission requirements (from the Devpost page, pasted by the human on 2026-10-09)

| # | Requirement | Current status (verified) | Work item |
| --- | --- | --- | --- |
| R1 | Runs on **Nebius Token Factory** or **Nebius AI Cloud** | Adapter exists, **never run live** (no key) | N01, N06 |
| R2 | Uses at least one **NVIDIA open model** (Nemotron) | Yes locally (Nemotron Nano 9B v2 GGUF); cloud untested | N01 |
| R3 | Track chosen | Not yet: choose **Best Apps and Agents** | M19 |
| R4 | Project description (what, why, how) | Draft material in `nebius/README.md` and `nebius/showtime-red-team-night.md` | M19 |
| R5 | **Working demo URL** (hosted app or test build) | None | N06 |
| R6 | **Demo video ≤ 3 min**, public YouTube, shows Token Factory + Nemotron use | None | M19 |
| R7 | **Public repo** with an open-source licence **visible at the top of the repo page** | Repo `github.com/Morningstaaar36/Showtime`; `LICENSE` only in `nebius/`, **not at the root**, so GitHub will not show it | N12 (M11) |
| R8 | README with setup steps; highlight Nemotron, Token Factory, other Nebius services | Root README exists (minimal); full one in `nebius/README.md` | N12 |
| R9 | **Feedback** on Token Factory, AI Cloud, NVIDIA models (required, and a $100 prize ×10) | `docs/FEEDBACK.md` exists but written without live use | N12, M19 |
| R10 | If the project existed before the submission period, explain what changed | Built 2026-10-08 onward (PROGRESS.md); git history is one squashed commit | N12 (state it plainly in Devpost) |
| R11 | City Winner Award: name the Builders & Brews city if attended | Unknown | Human (section 3) |

### 1.2 Judging criteria and how we answer each

| Criterion | What judges look for | Our answer (existing + new) |
| --- | --- | --- |
| **Technological implementation** | Built well; effective use of Token Factory and Nemotron | One Autopilot (N13) orchestrating Nemotron Nano/Super/Ultra by role (N01) and existing simulators (JuPedSim, PedPy, Pynite) as tools; tiered screening and caching for cost (N16); Nebius Sandboxes snapshot branching (N04); multi-seed ranges (N05); every number computed and checked; validation against real experiments (N10); green CI (N12) |
| **Design** | A complete, coherent product, not a proof of concept | Three-screen simple flow *Describe → AI at work → Your plan* (N14) with one "Ask or change anything" box (N15); Expert view keeps the full studio; plan → operate (N07) → hand over (N08, N09) |
| **Potential impact** | Credible, specific case for a real audience; demonstrated | Turns days of specialist work into minutes at a measured cost (N16); named disasters (Itaewon 2022, Indiana 2011); named users (organizers, venue managers, permit officers); real places (Ramna Park, BUET); Bangla steward cards (N08); cited local rules (N03); one actionable number: latest safe time to start evacuating |
| **Quality of the idea** | Creative, non-obvious use of Nemotron + Token Factory; understanding of the problem | AI as the operator of validated simulation software, not a replacement for it; adversarial red/blue planning grounded in real incidents; fixes proven by simulation; model size matched to task to keep cost low |
| **Best Use of Tavily** ($3,000) | Tavily is central, not decorative | Evidence Desk (N02): live sources on every attack card, pre-event web brief; local rules research with verified quotes (N03); sources section in every report |
| **Most Valuable Feedback** ($100 ×10) | Specific, named, actionable | Feedback log kept during N01/N04/N02 work with timestamps, error messages and time-to-hello-world (N12) |

### 1.3 Track

**Best Apps and Agents.** The Devpost text for this track literally says "Reach for Nemotron 3 Ultra when
you need serious reasoning, and let Nano or Super handle the fast, everyday calls". Our role routing does
exactly that; make it visible (N01 model routing panel, video, README table). Nebius Serverless Endpoints /
Jobs are encouraged but not required; see N06 (deployment) for where they could fit **[VERIFY]**.

---

## 2. Audit of the current state (verified 2026-10-09)

Source: code, tests and docs in this repo, read on 2026-10-09. Commands used are listed in section 12.

### 2.1 What exists and works (per `docs/HANDOFF.md` and `docs/PROGRESS.md`, spot-checked in code)

- Backend: FastAPI (`api/app/`), 65 routes under `/api/v1`, SQLite + Alembic (one migration
  `0001_initial_schema.py`), SSE session stream, plugin system with 12 extension points and 12 built-in
  plugins (`config/features.yaml`), LangGraph Event Copilot (`api/orchestrator/copilot_graph.py`).
- Agents (`api/agents/`): event_brief (main), venue_designer (main), venue (main), red_team (fast),
  blue_team (main), judge (judge), explainer (main, in `judge.py`), safety_officer (judge).
  Rule-based fallbacks in `api/orchestrator/fallbacks.py`.
- Simulation: JuPedSim 1.4.2 + PedPy 1.5.1 sandbox image (`sim/`), Tier 1 (`api/core/tier1.py`),
  Tier 2/3, two floors, events, time travel, calibration (`api/data/calibration.json`).
- Hazards: Open-Meteo + Pynite stage check + countdown.
- Web: Vite 7 + React 19 + R3F; pages Projects, Copilot, Workspace (modes plan/simulate/redteam/report),
  Settings, Help, Onboarding, NotFound; 22 panel files in `web/src/panels/`.
- Providers: LLM `local | nebius | openai | fake` with hosted→local fallback (`LLM_FALLBACK`), sandbox
  `docker | nebius | fake`, Tavily adapter, weather, OSM.
- Tests: 96 test functions in `api/tests` + 9 in `sim/tests` (counted by `def test_`; PROGRESS records
  114 passed because some are parametrized), 10 vitest cases in 3 files, 3 Playwright journeys. Last recorded
  results: `make check` green, `make test` 114 passed / 1 skipped, `make test-web` passed, `make e2e` 3 passed, `make smoke` OK.

### 2.2 Gaps found (these drive the plan)

| # | Gap | Evidence | Fixed by |
| --- | --- | --- | --- |
| G1 | No `LICENSE` at the repo root; GitHub shows the licence only from the root | `ls ./` shows `README.md`, `requirements.txt`, `nebius/`; licence is `nebius/LICENSE` | M11 |
| G2 | No CI workflow, although `CHANGELOG.md` line 69 says one was added | No `.github/` in the repo (`git ls-files`) | M11 |
| G3 | **Tavily is never called.** `TavilySearch` is constructed in `api/app/state.py` and only used for `/health`; no agent or orchestrator calls it. `nebius/README.md` claims "live web evidence for attack cards and rules" | `grep -rn "st.search" api` → only `routes_core.py` health lines | N02, N03 |
| G4 | Token Factory, Nebius Sandboxes and Tavily have **never run live** | HANDOFF "Unverified items", NEBIUS_SWITCH status table | N01, N04, N02 |
| G5 | The `long` model role is configured but no agent uses it | `grep role=` in `api/agents` shows only fast/main/judge | N03 (rules extraction uses `long`) |
| G6 | No public-demo protections: `PUT /api/v1/settings` open to anyone, no rate limits, no per-visitor isolation, `LLM_FALLBACK=local` by default (a cloud server has no local GPU model) | `api/app/routes_core.py`, `api/core/settings.py:72` | N06 |
| G7 | No hosted demo URL | — | N06 |
| G8 | `docs/TESTING_GUIDE.md` starts with `cd /home/lucifer/BUET/nebius` (stale path; the project now lives at `…/Showtime/nebius`) | TESTING_GUIDE line 8 | M11 |
| G9 | Test gaps: no tests for exporters' content, `/ask`, `/projects/{id}/sweep`, `/copilot/graph`, places routes, DXF import, weather cache, safety officer, event brief, SSE `?after=` replay, settings validation (e.g. danger density −1 refused), plugin failure isolation, `FEATURE_*` env override; frontend components largely untested; no accessibility checks | test name list (section 12) | Section 6, M11 + each milestone |
| G10 | Validation against real experiments (Jülich/Wuppertal) not done (P2 in BACKLOG) | HANDOFF status table | N10 |
| G12 | **The UI is too complicated for a first-time organizer.** Home shows a Copilot box, 3 samples, 4 templates, the project list and a 3-tab New project dialog; the workspace has 4 modes (Plan, Simulate, Red Team, Report), a tool rail, an inspector, a timeline, a command bar and a top bar with undo, redo, versions, countdown, cost, provider and lights; 22 panel files, ~4,000 lines of page/panel code. Getting from a sentence to a finished, stress-tested plan takes many steps across screens | `web/src/pages/Projects.tsx`, `web/src/pages/Workspace.tsx`, `web/src/panels/*`, `docs/TESTING_GUIDE.md` sections 0a–7 | N13, N14, N15 |
| G11 | Git history is one squashed `initial` commit, which hides the build story | `git log` | Commit per feature from now on; Devpost text states the start date |

---

## 3. Human actions and accounts (blocking items)

The agent cannot do these. Ask the human on day 1 and track them here.

| # | Action | Needed by | Blocks |
| --- | --- | --- | --- |
| H1 | Create a Nebius Token Factory account, claim hackathon credits, create an API key; put `NEBIUS_API_KEY` in `nebius/.env` | Oct 10 | N01 |
| H2 | Copy exact model ids for Nemotron 3 Nano, Super, Ultra (and a long-context model if listed) and their prices from the Token Factory console | Oct 10 | N01 |
| H3 | Request **Nebius Sandboxes** beta access (it is gated) | Oct 10 (request today) | N04 |
| H4 | Create a Tavily account and key (free tier); put `TAVILY_API_KEY` in `.env` | Oct 11 | N02, N03 |
| H5 | Nebius AI Cloud account with credits for one CPU VM (8 vCPU / 32 GB recommended) and a public IP | Oct 18 | N06 |
| H6 | Optional domain name (or use the VM's IP with a free DNS name **[VERIFY]**) | Oct 21 | N06 |
| H7 | Record voice-over and upload the video to YouTube (public) | Oct 28 | M19 |
| H8 | Submit on Devpost (only the human can) | Oct 29 | M20 |
| H9 | Tell us whether you attended a Builders & Brews event (city) | Oct 28 | R11 |
| H10 | Make the GitHub repo public before submitting; check it in a logged-out browser | Oct 29 | R7 |

---

## 4. Existing features: outline, acceptance criteria, tests

After N14 these features live in two places: the simple flow uses them through Autopilot and the *Your plan*
screen; the **Expert view** keeps today's workspace with all of them. Nothing here is deleted.

Format per feature: **purpose · code · acceptance criteria · existing tests · tests to add** (new test ids
`T-Fxx-n`). "Tests to add" close gap G9 and are scheduled in M11 (backend) and M18 (frontend/a11y).

### F01 Projects, versions, undo/redo, duplicate, import/export

- **Purpose:** nothing is lost; every save is a version; `.showtime.zip` round-trips with history.
- **Code:** `api/app/routes_projects.py`, `api/orchestrator/projects.py`, `api/db/*`, `web/src/pages/Projects.tsx`.
- **Acceptance:** create → edit → undo → redo → restore → duplicate → export → import gives identical venue
  hashes and run history; survives API restart.
- **Existing tests:** `test_persistence.py` (create_and_version, undo_redo_chain, new_edit_clears_redo,
  restore_and_duplicate, export_import_roundtrip, persists_across_service_instances), `test_api.py::test_project_lifecycle`,
  `test_export_import`, `test_redteam.py::test_reimporting_an_export_keeps_its_history`.
- **Tests to add:** `T-F01-1` delete removes versions, runs, sessions and session events (bug class fixed in
  M9, guard it); `T-F01-2` import of a corrupted zip returns `{code, message, hint}` 400, never 500;
  `T-F01-3` import rejects a zip over `UPLOAD_MAX_BYTES`.

### F02 Templates (conference hall 2F, school wing, festival field, T-alley)

- **Code:** `api/data/templates/*.json`, `scripts/build_templates.py`.
- **Acceptance:** all validate; headcounts as documented; T-alley dimensions cited in ASSUMPTIONS.
- **Existing tests:** `test_venue_core.py::test_four_templates_validate`, `test_template_headcounts`, `test_api.py::test_templates`.

### F03 Event Copilot (LangGraph): one sentence → brief → site → layout → ratios → project → simulation → sweep → safety officer

- **Code:** `api/orchestrator/copilot.py`, `copilot_graph.py`, `api/agents/event_brief.py`, `safety_officer.py`,
  `api/app/routes_places.py` (`/copilot/plan`, `/copilot/graph`), `web/src/pages/Copilot.tsx`, `web/src/panels/AgentGraph.tsx`.
- **Acceptance:** example sentences produce a project with a valid venue, estimates, a started simulation and a
  safety-officer card; graph structure served at `/copilot/graph` matches nodes drawn in the UI.
- **Existing tests:** `test_venue_sources.py::test_copilot_plans_a_designed_venue_end_to_end`.
- **Tests to add:** `T-F03-1` `/copilot/graph` returns every node and edge of the compiled graph;
  `T-F03-2` brief agent: 10 scripted sentences (fake LLM fixtures) map to the expected `place, date, time,
  people, duration_h, alcohol` fields; `T-F03-3` OSM failure (mock 503) routes to the designer branch with a
  visible note; `T-F03-4` safety officer output passes the number check or falls back to the template.

### F04 Plan-for-the-day estimates, planning score, what-if lab

- **Code:** `api/core/estimates.py`, `score.py`, `api/data/planning_ratios.json`, routes `/projects/{id}/estimates`, `/whatif`.
- **Acceptance:** every ratio has a source; what-if recomputes in < 200 ms.
- **Existing tests:** `test_estimates.py` (toilets Purple Guide rows, exit width monotonic, score parts and caps), `test_api.py::test_what_if_scales_crowd_closes_exits_and_scores`.
- **Tests to add:** `T-F04-1` every key in `planning_ratios.json` has a non-empty `source` URL or citation;
  `T-F04-2` `/whatif` p95 < 200 ms over 20 calls on the festival template.

### F05 Venue from a description (designer agent + solver)

- **Code:** `api/agents/venue_designer.py`, `api/core/venue_builder.py`, `/venues/design`, `web/src/pages/newproject/DescribeTab.tsx`.
- **Existing tests:** `test_venue_sources.py::test_spec_builds_a_valid_two_floor_hall`, `test_stage_on_any_wall_gives_valid_open_air_site`, `test_designer_builds_from_model_spec_and_repairs_once`.

### F06 Venue from a real place (OpenStreetMap)

- **Code:** `api/adapters/osm.py`, `api/core/osm_venue.py`, `api/orchestrator/venue_sources.py`, `/places/*`, `/venues/from-map`, `web/src/pages/newproject/MapTab.tsx`.
- **Existing tests:** `test_venue_sources.py` (buildings as obstacles, mapped entrance, two assumed exits, too-large area refused, water not walkable, furnish, area in m²).
- **Tests to add:** `T-F06-1` `/places/search` and `/places/features` with a mocked OSM adapter (no network)
  return the documented shapes; `T-F06-2` OSM timeout → designed error with hint, never 500;
  `T-F06-3` OSM responses are cached (second call makes no HTTP request).

### F07 3D plan editor (drag, draw barrier/zone/exit, measure, showtime lights, tour)

- **Code:** `web/src/scene/*`, `web/src/panels/ToolRail.tsx`, `Tour.tsx`.
- **Existing tests:** Playwright journey 2 (create, edit, undo, stress test, block an exit).
- **Tests to add (M18):** `T-F07-1` Playwright: drag an obstacle → new version appears in the version menu;
  `T-F07-2` draw a barrier with clicks + double-click → patch op `add_barrier_line`; `T-F07-3` keyboard
  shortcuts `/`, `R`, `Space`, `X`, `Ctrl+Z` work (assert state changes).

### F08 Text edits (Venue agent)

- **Code:** `api/agents/venue.py`, `prompts/venue.md`, `/projects/{id}/edit`, `scripts/eval_venue_agent.py`.
- **Acceptance:** ≥ 11/12 scripted edits valid on every provider we claim (local 12/12 recorded).
- **Existing tests:** `test_api.py::test_invalid_edit_has_designed_error`, venue eval script.
- **Tests to add:** the eval becomes part of `make eval` (section 6.2.4) and runs on Nebius in M12.

### F09 Geometry checks and rules pack

- **Code:** `api/core/geometry.py`, `plugins/rules_generic/`.
- **Existing tests:** `test_venue_core.py` (validation flags problems, zone without exit, mezzanine reaches exit via stair, stage cannot be removed, new geometry errors rejected, exit defaults/overlaps).

### F10 Tier 1 instant estimate and "Break it yourself"

- **Code:** `api/core/tier1.py`, `/venues/{id}/tier1`.
- **Existing tests:** `test_estimates.py` tier1_* (hand calculation, wider door faster, split by capacity, block reroutes, staggered/surge, all templates fast, multi-floor, trapped), `test_api.py::test_tier1_and_break_it_yourself`.

### F11 Tier 2/3 simulation and heatmap replay

- **Code:** `sim/*`, `api/adapters/sandbox.py`, `api/orchestrator/runs.py`, `web/src/replay/*`, `web/src/scene/ReplayLayers.tsx`.
- **Existing tests:** `sim/tests/test_sim.py` (9), `test_trajpack.py` (2), `test_persistence.py` run tests (idempotent, attack/fix change results, failed sandbox), vitest `trajectory.test.ts`.
- **Tests to add:** `T-F11-1` `/runs/{id}/trajectory` and `/density` return `application/octet-stream`
  and an index whose frame count matches; `T-F11-2` invalid `run_id` (e.g. `../x`) returns 404, not a file
  read (path traversal guard; important for the public demo).

### F12 Two-floor venues

- **Existing tests:** `sim/tests::test_multi_floor_conserves_people`, `test_tier1_multi_floor_routes_through_stair`, `test_venue_core::test_mezzanine_reaches_exit_via_stair`.

### F13 Scenario sweep + Safety officer

- **Code:** `api/orchestrator/sweep.py`, `/projects/{id}/sweep`, `web/src/panels/ScenarioMatrix.tsx`, `OfficerCard.tsx`.
- **Tests to add:** `T-F13-1` sweep with the fake runner creates six child runs with the right parent and labels;
  `T-F13-2` `GET /projects/{id}/sweep` reports progress then results; `T-F13-3` a failed child run marks only
  that card failed.

### F14 Red Team Night (red/blue/judge, rounds, Tier 3 confirmation, SSE)

- **Code:** `api/orchestrator/session.py`, `api/agents/red_team.py`, `blue_team.py`, `judge.py`, `api/app/routes_agents.py`, `web/src/panels/RedTeamPanel.tsx`.
- **Existing tests:** `test_redteam.py` (15: citations, DOI fallback, invalid JSON, fix validation, check_fix rules, judge number check, break reasons, session completion and stream, LLM outage, budget, sandbox failure, budget object, titles cannot name missing features, sample packs).
- **Tests to add:** `T-F14-1` SSE `?after=<seq>` replays only later events and ends with `event: end`;
  `T-F14-2` `/sessions/{id}/stop` finishes with `stopped_reason="stopped by user"` and partial summary;
  `T-F14-3` `/sessions/{id}/apply` creates exactly one new version equal to the session's final venue.

### F15 Branch tree, scoreboard, activity feed, cost meter

- **Code:** `web/src/panels/BranchTree.tsx`, `Metrics.tsx`, `TopBar.tsx`.
- **Tests to add (M18):** `T-F15-1` Playwright on a sample: branch tree shows baseline + attacks + fixes + final and
  clicking a node loads its run; `T-F15-2` cost meter shows `$0.00` on local and a non-zero value on a recorded
  Nebius session.

### F16 Time travel, split compare, marshal bubbles

- **Existing tests:** `sim/tests::test_intervention_identical_before_t`, `test_persistence::test_compose_events_shifts_fix_to_intervention`.
- **Tests to add:** `T-F16-1` marshal events in a fake session produce `marshal` SessionEvents with speech text that
  passes the id-to-name replacement (no machine ids).

### F17 Wind hazard, stage check, countdown

- **Code:** `plugins/hazard_wind/`, `plugins/hazard_timer/`, `api/core/countdown.py`, `api/adapters/weather.py`, `/weather`, `/stage-check`, `/projects/{id}/countdown`.
- **Existing tests:** `test_estimates.py` (countdown formula, no hazard, too late, stage check monotonic and sqrt ballast, first crossing, wind hazard forecast/calm/manual, timer hazard), `test_api.py` countdown tests.
- **Tests to add:** `T-F17-1` weather adapter caches by (lat, lon, date, hours) and the second call makes no HTTP
  request; `T-F17-2` Open-Meteo 500 → UI-facing error offering manual gust input.

### F18 Ask the venue (Explainer)

- **Code:** `api/agents/judge.py` (explainer), `/ask`, `web/src/panels/AskDialog.tsx`.
- **Tests to add:** `T-F18-1` `/ask` with a fake LLM returns `numbers_checked=true` and a `camera_target`;
  `T-F18-2` an answer quoting a number not in the run is regenerated once then replaced by the template answer;
  `T-F18-3` question about data the run lacks yields "I don't know".

### F19 Reports (HTML/PDF), SVG evacuation map, JSON bundle

- **Code:** `plugins/export_html_report`, `export_svg_map`, `export_json_bundle`, `api/orchestrator/reports.py`.
- **Tests to add:** `T-F19-1` report HTML contains "Planning aid, not a safety certification", the verdict, the
  countdown, assumptions with sources and the calibration ratio; `T-F19-2` SVG parses as XML, has one arrow per
  assigned exit and exit names (not ids); `T-F19-3` bundle JSON validates against the Pydantic models and contains
  no secret values (scan for `NEBIUS_API_KEY`, `TAVILY_API_KEY` values from settings).

### F20 Sample projects / demo packs

- **Existing tests:** `test_redteam.py::test_sample_packs_install_once_update_and_respect_deletes`.
- **Tests to add (M17):** re-record the three packs on **Nebius** models so the cost meter and model badges in
  samples show Token Factory, not local (keep the local packs as a fallback in `cache/demos/local/`).

### F21 Importers (DXF with `jps-*` layers, JSON)

- **Tests to add:** `T-F21-1` a tiny DXF fixture (walkable rectangle + one exit + one zone) imports to a valid venue;
  `T-F21-2` DXF without required layers → designed error listing the missing layer names.

### F22 Provider adapters, fallback, record/replay cache

- **Existing tests:** `test_llm_provider.py` (9), `test_nebius.py` (3, live one skipped).
- **Tests to add:** see N01 and N04.

### F23 Plugin system and feature flags

- **Existing tests:** `test_venue_core::test_plugins_loaded`, conformance suites in `api/tests/conformance/suites.py`.
- **Tests to add:** `T-F23-1` a plugin whose `__init__` raises is marked unhealthy in `/health` and skipped, the app
  still starts; `T-F23-2` `FEATURE_HAZARD_WIND=false` removes it from `/features`; `T-F23-3` invalid plugin config
  disables only that plugin with a readable log line.

### F24 Settings, Help, Onboarding, theme, i18n

- **Tests to add:** `T-F24-1` `PUT /settings` with `density_danger_ppm2=-1` returns 422 with a reason;
  `T-F24-2` `GET /settings` never contains key values (only "set"/"not set"); `T-F24-3` every string key used in
  `web/src` exists in `en.json` (small node script in `make lint`).

### F25 Health and probe

- **Existing tests:** `test_api.py::test_health_and_features`.
- **Tests to add:** `T-F25-1` health reports provider label `NEBIUS` when `LLM_PROVIDER=nebius` (fake client).

---

## 5. New features: detailed specifications

Priority: **P0** = required to submit or to be credible; **P1** = what makes us win; **P2** = cut first.

| Id | Feature | Priority | Milestone |
| --- | --- | --- | --- |
| N12 | Repo and submission compliance (root LICENSE, CI, README, feedback) | P0 | M11, M19 |
| N01 | Nemotron on Token Factory, live, with role routing and a model routing panel | P0 | M12 |
| N16 | Cost efficiency: measured cost per plan, screening funnel, model escalation | P0 (story) | M12 (metering), M13 (UI) |
| N13 | Autopilot: one click from a sentence to a stress-tested, fixed plan | P0 (story) | M13 |
| N14 | Simple UI: three screens (Describe → AI at work → Your plan) + Expert view | P0 (design) | M13 |
| N02 | Evidence Desk: live Tavily evidence for the red team + pre-event web brief | P0 (Tavily prize) | M14 |
| N03 | Local rules research with verified quotes | P1 | M14 |
| N18 | Event research: web-sourced, cited input suggestions (attendance, capacity, gates) | P1 (Tavily prize, story) | M14 |
| N19 | Fix guidance: blue team fixes cite trusted safety guidance | P2 | M14 if time |
| N15 | "Ask or change anything": one box with an intent router | P1 | M14 |
| N04 | Nebius Sandboxes live, parallel branches | P0 attempt (fallback allowed) | M15 |
| N05 | Ranges across seeds (multi-seed ensembles) | P1 | M15 |
| N06 | Public demo mode + hosted deployment on Nebius | P0 | M15 (early deploy), M17 |
| N07 | Live Ops console (day-of mode) | P1 | M16 |
| N08 | Steward briefing pack with translation (Bangla) | P1 | M16 |
| N10 | Validation lab: simulator vs real bottleneck experiments | P1 | M16 |
| N09 | Share link for permit offices (read-only report + QR) | P2 | M16 if time |
| N11 | Judge landing and 90-second tour (part of the N14 Home screen) | P0 (small) | M13, polished M18 |
| N17 | Open formats: export a scenario to run in the user's own JuPedSim setup | P2 | M18 if time |

---

### N01 — Nemotron on Nebius Token Factory, live, with role routing (P0)

**Why:** R1/R2 and the "Technological implementation" criterion. The Devpost track text asks for Ultra for
reasoning and Nano/Super for everyday calls.

**Target routing** (ids copied by the human into `.env`, never hardcoded):

| Role | Model (target) | Used by |
| --- | --- | --- |
| `fast` | Nemotron 3 Nano **[VERIFY id]** | red team drafting, pre-event brief summarising (N02), steward text (N08) |
| `long` | long-context Nemotron if listed, else Nemotron 3 Super **[VERIFY id]** | rules extraction from long pages (N03) |
| `main` | Nemotron 3 Super **[VERIFY id]** | event brief, venue designer, venue edits, blue team, explainer, translation (N08) |
| `judge` | Nemotron 3 Ultra **[VERIFY id]** | judge, safety officer |

**Steps**

1. Probe (`scripts/probe_tokenfactory.py`, new, ≤ 60 lines, uses the adapter not the SDK directly):
   for each role, (a) plain chat, (b) JSON with `response_format: {type: "json_schema"}`, (c) reasoning off.
   Record per model: works yes/no, latency, tokens, how reasoning is switched off **[VERIFY: system prompt
   `/no_think`, or `LLM_EXTRA_BODY` such as `{"chat_template_kwargs": {"enable_thinking": false}}`, or a
   `reasoning` field]**, whether `json_schema` is honoured **[VERIFY]**. If `json_schema` is not supported,
   set `LLM_SUPPORTS_JSON_SCHEMA=false` (prompted JSON + repair path already exists).
2. If different models need different extra bodies, add per-role overrides `LLM_EXTRA_BODY_<ROLE>` to
   `Settings` (fallback to `LLM_EXTRA_BODY`). Unit test it.
3. Set `LLM_FALLBACK=none` for any deployment without a local GPU model (see N06).
4. Run `make eval PROVIDER=nebius` (section 6.2.4) and fix prompts until thresholds pass. Prompts must keep
   working on the local 9B model too (re-run local eval; do not regress below 11/12 venue edits).
5. **Model routing panel** (UI): Settings › Providers shows a table role → model id → agents using it →
   price in/out → calls/tokens/cost this session. Backend: `GET /api/v1/models` returning
   `[{role, model, label, agents: [...], price_in, price_out, provider}]` (no keys). The activity feed and
   attack/fix cards already show the model per call; make sure Nebius ids render readably (strip vendor
   prefixes for display, keep the full id in a tooltip).
6. Record new LLM fixtures for tests in `replay` mode from Nebius (do not overwrite the local fixtures:
   cache keys include provider and model, so both sets coexist).
7. Update `docs/NEBIUS_SWITCH.md` status table with real results, `docs/FEEDBACK.md` with live notes
   (time from account to first successful call, any error text verbatim).

**Tests**

- `T-N01-1` (unit) per-role extra body override is sent only to that role's calls.
- `T-N01-2` (unit) `/models` lists all four roles and never includes key material.
- `T-N01-3` (unit) `LLM_FALLBACK=none` + hosted failure → `AgentUnavailable`, session continues with rule-based
  attacks (existing behaviour), UI badge shows the outage.
- `T-N01-4` (live, marker `nebius`) one call per role returns valid JSON for a tiny schema; usage tokens > 0;
  cost = tokens × configured price.
- `T-N01-5` (live eval) thresholds in section 6.2.4 met on Nebius; results saved to `docs/evals/`.
- `T-N01-6` (smoke) `make smoke-nebius` passes the LLM part.

**Done when:** all six tests green; the provider badge shows `NEBIUS`; one full Red Team Night on a sample
venue completes on Token Factory with every role used at least once (activity feed shows Nano, Super, Ultra);
NEBIUS_SWITCH and FEEDBACK updated with real observations.

---

### N02 — Evidence Desk: live Tavily evidence (P0 for the Tavily prize)

**Why:** fixes gap G3 (README claims Tavily use that does not exist); "Best Use of Tavily" prize; makes attack
cards more credible ("this happened last month at a similar venue").

**Behaviour**

1. **Red team evidence.** Before each red-team round, build up to 3 queries from venue features and the incident
   query (`api/agents/red_team.py::incident_query` already produces keywords). Examples:
   `"crowd crush narrow sloped alley" incident`, `"stage roof collapse wind" festival`, `"<city> event crowd
   safety"`. Call `TavilySearch.search(query, max_results=5, search_depth="basic")` through a new budgeted
   helper; pass the hits to the red-team prompt next to dataset rows. Attack `inspired_by.source_url` must be in
   *hits ∪ dataset rows* (validator already rejects unknown URLs for dataset rows; extend it to hits).
   Every search emits `tool_call` `{tool: "search_web", args: {query}, summary: "5 results (cached)"}`.
2. **Pre-event web brief** (Copilot node "Evidence desk", after the brief node, before the layout): searches for
   the event place + date: road closures, other large events the same day, protests, weather warnings, recent
   incidents at that venue (`topic="news"` and a recency window **[VERIFY parameter names in tavily-python
   0.8.5: `topic`, `days` or `time_range`]**). The `fast` role summarises hits into at most 6 "Things to check"
   items, each with `{text, source_url, published}`; `source_url` must come from the hits. Label in UI:
   "From the web, not verified". N18 extends this node from "things to check" to input suggestions the
   organizer can accept.
3. **Evidence panel** (Red Team tab and Report): every source used, grouped by "Live web (Tavily)" vs "Incident
   dataset", with domain, date, title, which attack/rule used it; budget line "Live searches: 7 of 20".
4. **Report:** a "Sources" section listing every cited URL with what it supports.
5. **Offline / no key:** cached results only; banner "Live search is off. Attack cards use the incident dataset."
   (existing copy). The session never fails because of Tavily.

**Contracts**

- `api/models/evidence.py`: `EvidenceSource{url, title, snippet, published?, origin: "tavily"|"dataset"|"cache",
  used_by: list[str]}`, `WebBriefItem{text, source_url, published?}`, `WebBrief{items, queries, live: bool}`.
- Session summary gains `sources: list[EvidenceSource]` (additive; bump `schema_version` per CLAUDE.md 7A.3).
- New SessionEvent type is **not** needed; reuse `tool_call`.

**Code**

- `api/orchestrator/evidence.py` (new): `gather_attack_evidence(st, venue, features, budget) -> list[SearchHit]`,
  `web_brief(st, brief) -> WebBrief`. Uses `st.search` only (adapter boundary).
- `api/agents/red_team.py`: accept `hits` and add them to the prompt; validator accepts hit URLs.
- `api/agents/prompts/red_team.md`: add the hits section and "cite only these URLs" rule; bump prompt version.
- `api/agents/web_brief.py` + `prompts/web_brief.md` (new, role `fast`).
- `api/orchestrator/copilot_graph.py`: add node `evidence_desk` (non-blocking: on failure, empty brief + note).
- `api/orchestrator/session.py`: call `gather_attack_evidence` per round; collect sources into the summary.
- `plugins/export_html_report`: render Sources section from the summary (plugins read models only).
- Web: `web/src/panels/EvidencePanel.tsx` (new), entry in Red Team tab and Copilot result card; strings in `en.json`.
- `api/adapters/search.py`: make sure the per-session `SearchBudget` is created per session and per Copilot run.

**Tests**

- `T-N02-1` (unit, fake Tavily client) queries are built from venue features; at most 3 per round; cached on second call.
- `T-N02-2` (unit) an attack citing a URL not in hits or dataset is discarded (audit-logged).
- `T-N02-3` (unit) budget exhausted → no further live calls, cached hits still served, `tool_call` summary says so.
- `T-N02-4` (unit) no key / `OFFLINE=true` → session completes, sources only from dataset, banner flag in `/features`.
- `T-N02-5` (unit) web brief items all have `source_url` ∈ hits; invalid items dropped; empty brief renders the empty state.
- `T-N02-6` (integration) Copilot graph includes `evidence_desk` and still completes when Tavily raises.
- `T-N02-7` (exporter) report contains a Sources section with every cited URL exactly once.
- `T-N02-8` (live, marker `tavily`) one real search returns ≥ 1 hit with url and title.
- `T-N02-9` (e2e) Red Team tab shows the Evidence panel with "Live web" sources on a recorded session.

**Done when:** a live session on the T-alley sample shows at least one attack card whose source is a live Tavily
URL; the report's Sources section lists it; all tests green; README claim is now true.

---

### N03 — Local rules research with verified quotes (P1)

**Why:** organizers and permit offices need *their* local rules, not generic example values. Strong Tavily use;
uses the otherwise idle `long` role (gap G5); hard anti-hallucination guarantee.

**Behaviour**

1. Plan tab › Rules section › **Find local rules**. Inputs: venue location (country/city from the project
   location or OSM), event type (indoor/outdoor).
2. Backend runs 2–4 Tavily searches (e.g. `"<country> outdoor event permit crowd safety guidance"`,
   `"<country> fire code exit width per person assembly"`), then `extract` on the top 3 distinct URLs.
3. The `long` role reads extracted text and returns candidate rules, each:
   `{metric, comparator, value, unit, applies_to, source_url, quote}` where `metric` is from a fixed enum the
   checker understands: `exit_width_mm_per_person`, `max_travel_m`, `max_density_ppm2`, `min_exits_above_people`,
   `toilets_per_people`, `stewards_per_people`, `first_aiders_per_people`.
4. **Verification in code (no trust in the model):** `source_url` ∈ extracted URLs; `quote` must appear in the
   extracted text of that URL after whitespace/case normalisation; the number `value` must appear inside the
   quote; units are converted by code. Failing candidates are dropped and counted ("3 suggestions dropped:
   quote not found on the page").
5. UI lists candidates as **Unconfirmed** with the quote and a link; the user ticks to confirm. Confirmed rules
   are stored per project and checked like `rules_generic` (violations highlighted in 3D, listed in the report
   with the quote and link). The report marks them "found by AI, confirmed by <user> on <date>".

**Contracts and storage**

- `api/models/rules.py`: `RuleCandidate`, `ProjectRule{id, metric, comparator, value, unit, source_url, quote,
  status: "unconfirmed"|"confirmed"|"rejected", confirmed_at?}`.
- Migration `0002_*` adds table `project_rule` (see section 5 "Migration 0002").
- Routes (`api/app/routes_rules.py`, new): `POST /projects/{id}/rules/research` → `{candidates, dropped, queries,
  live}`; `GET /projects/{id}/rules`; `PATCH /projects/{id}/rules/{rule_id}` (`status`).
- Plugin `plugins/rules_researched/` (RulesPack) that receives confirmed rules **through the models it is given**
  (the orchestrator passes them in; the plugin must not import `api.db`; import-linter enforces this).

**Tests**

- `T-N03-1` quote verification: exact, whitespace-variant and case-variant quotes pass; paraphrase fails; a value
  not inside the quote fails.
- `T-N03-2` URL not among extracted pages → dropped.
- `T-N03-3` unit conversion (inches → mm, feet → m) correct; unknown unit → dropped.
- `T-N03-4` confirmed rule produces a violation on a venue that breaks it and none on one that satisfies it.
- `T-N03-5` rejected/unconfirmed rules never affect checks or the score.
- `T-N03-6` no Tavily key → endpoint returns `{live:false, candidates: []}` with hint copy, 200 not 500.
- `T-N03-7` (live, `tavily` + `nebius`) Dhaka, Wellington, London: each run returns ≥ 1 verified candidate or an
  honest empty result; zero unverified candidates ever shown (assert).

**Done when:** tests green; on the Ramna Park project at least one confirmed local rule appears in Checks and in
the report with its quote and link (or, if none is found live, the empty state explains it honestly).

---

### N04 — Nebius Sandboxes live, parallel branches (P0 attempt)

**Why:** "every attack and fix is a sandbox snapshot branch" is our strongest Nebius story. Code exists
(`api/adapters/nebius_sandbox.py`, contree-sdk 0.3.6) but has only run against a fake client.

**Steps**

1. When H3 access arrives: `scripts/probe_sandboxes.py` (new): create base image from `python:3.12-slim`, run
   `echo ok`, write a file, read it back, branch twice from one parent, time each step. Record results.
2. `make smoke-nebius` full path: base image build (cache id in `cache/nebius/base_image.json`), one Tier 2 run,
   artifacts read back, metrics equal (within 1 %) to the same run on Docker with the same seed (determinism).
3. Parallelism: `SANDBOX_MAX_PARALLEL=4`, measure a 4-attack round wall time vs local (record both in PROGRESS
   and FEEDBACK; this is a video moment: "4 branches in parallel").
4. Branch tree nodes carry the sandbox image id (show it in the node tooltip: "Nebius snapshot img_…").
5. Failure handling already exists (failed sandbox → estimates fallback). Add retry-once on transient errors.

**Tests**

- Existing: `test_nebius.py::test_nebius_runner_branches_and_reads_results`, `test_nebius_runner_failure_is_reported`.
- `T-N04-1` (unit, fake) transient error then success → one retry, result ok, one `log` warning event.
- `T-N04-2` (unit, fake) concurrency never exceeds `SANDBOX_MAX_PARALLEL` (instrumented fake).
- `T-N04-3` (live, `nebius`) `test_nebius_live_health` passes; one Tier 2 run on `school_wing` (300 people) returns
  status ok and the same p95 as Docker within 1 %.
- `T-N04-4` (live) a red-team round with 4 attacks runs 4 sandboxes concurrently (timestamps overlap).

**Fallback (if access never arrives by Oct 20):** keep `SANDBOX_PROVIDER=docker` on the Nebius AI Cloud VM (N06),
so simulations still run **on Nebius AI Cloud**. Say exactly that in README/Devpost/FEEDBACK
("Sandboxes runner built against contree-sdk 0.3.6, untested live: access pending").

---

### N05 — Ranges across seeds: multi-seed ensembles (P1)

**Why:** one simulation is one sample of a random process. Showing "evacuation time (95%) 206 s, range 199–221 s
over 10 seeds, 0 of 10 seeds break" is what a safety engineer expects, and it showcases parallel sandboxes.

**Behaviour**

- *Your plan* shows the range automatically when Thorough Autopilot ran it; Expert view › Simulate ›
  **Run with several seeds** (seeds 5/10/20, quick or full simulation). Runs `default_seed + i` for i in 0..N−1,
  in parallel up to `SANDBOX_MAX_PARALLEL`, each a normal run (cached, idempotent).
- Aggregate per metric: median, min, max, p10, p90; `break_fraction = breaks / N`.
- UI: metric chips get a range bar and "n seeds" label; verdict uses p90 of evacuation time and any-break rule
  ("2 of 10 seeds break → at risk"). Copy uses "range across N simulations", not "confidence interval" (no
  distribution assumption).
- Red Team final confirmation can optionally use an ensemble (`config.confirm_seeds`, default 1 locally, 5 on Nebius).

**Contracts / code**

- `api/models/ensemble.py`: `EnsembleRequest{tier, seeds, attack_id?, fix_id?}`, `EnsembleResult{run_ids, stats:
  {metric: {median, min, max, p10, p90}}, break_fraction, status}`.
- `api/orchestrator/ensemble.py`; routes `POST /projects/{id}/ensemble` (202) and `GET /ensembles/{id}`.
- Table `ensemble` in migration 0002 (id, project_id, venue_version, request JSON, result JSON, status, timestamps).
- Web: `web/src/panels/Metrics.tsx` range bar component; i18n strings.

**Tests**

- `T-N05-1` aggregator: hand-made metric lists give the exact median/p10/p90/min/max (define percentile method:
  linear interpolation, numpy default) and break fraction.
- `T-N05-2` fake runner with 10 seeds → 10 distinct run ids, idempotent on repeat (no new runs).
- `T-N05-3` concurrency bound respected (shared instrumented fake with N04).
- `T-N05-4` (sim, slow) school wing 5 seeds Tier 2: all ok; spread > 0 and < 15 % of median (sanity of seeding).
- `T-N05-5` (e2e) range bar visible after an ensemble on a sample.

---

### N06 — Public demo mode and hosted deployment on Nebius (P0)

**Why:** R5 requires a working demo URL; judges will click it. A public app with LLM calls and simulations
must not be abusable, must not leak keys, and must not let one visitor break the demo for others.

**Demo mode** (`DEMO_MODE=true`, new settings; all off by default so local use is unchanged):

| Setting | Default in demo | Behaviour |
| --- | --- | --- |
| `DEMO_MODE` | true | enables everything below |
| `DEMO_READ_ONLY_SETTINGS` | true | `PUT /settings` → 403 `{code:"demo_read_only", hint:"Settings are fixed on the public demo. Run it locally to change them."}` |
| `DEMO_MAX_PEOPLE` | 3000 | caps runs (clear message when capped) |
| `DEMO_RATE_LIMITS` | copilot 5/h, sessions 2/h, runs 20/h, edits 60/h, ask 30/h, rules 5/h per visitor | 429 with `Retry-After` and designed copy |
| `DEMO_MAX_CONCURRENT_SESSIONS` | 1 | others wait in a queue; UI shows "You're number 2 in line" |
| `DEMO_DAILY_USD_CAP` | 5.00 **[set with the human after N01 cost measurement]** | when reached, LLM calls run in `replay` only; banner "Today's live AI budget is used up; showing recorded runs" |
| `TRUST_PROXY` | true behind Caddy | client IP from `X-Forwarded-For` (only then) |
| `LLM_FALLBACK` | none | no local GPU model on the server |

- **Visitor isolation:** API sets an anonymous cookie `st_ws` (random 128-bit, HttpOnly, SameSite=Lax, Secure).
  New column `project.owner_ws` (migration 0002). In demo mode `GET /projects` returns samples + the visitor's
  own projects only; every project route checks ownership (404 if not owner; samples are readable by all).
- **Samples are read-only in demo mode:** an edit on a sample returns 409 `{code:"sample_read_only",
  hint:"Make your own copy to edit it."}`; the UI offers **Make my copy** (existing duplicate route).
- **Cleanup:** background task deletes visitor projects older than 48 h and their runs (reuse delete path from F01).
- **Rate limiter:** small in-memory token bucket in `api/app/ratelimit.py` (no new dependency), applied by route
  group via a FastAPI dependency.
- **Usage persistence:** daily token/cost totals in a `usage_day` table (migration 0002) so the cap survives restarts.
- **No Docker socket** in the public compose file when `SANDBOX_PROVIDER=nebius`; when the fallback Docker runner is
  used on the VM, the socket is mounted but the API never accepts user-controlled image names or commands
  (already true; add a test).

**Deployment files** (new, section 8 has the procedure): `deploy/docker-compose.public.yml`, `deploy/Caddyfile`,
`deploy/.env.public.example`, `deploy/README.md`, `scripts/smoke_public.py`, `scripts/load_public.py`.

**Tests**

- `T-N06-1` `PUT /settings` → 403 in demo mode, 200 otherwise.
- `T-N06-2` rate limit: the 6th copilot call within an hour from one visitor → 429 with `Retry-After`; another
  visitor is unaffected; `TRUST_PROXY=false` ignores spoofed `X-Forwarded-For`.
- `T-N06-3` visitor A cannot read, edit, export or delete visitor B's project (404 each).
- `T-N06-4` edit on a sample → 409 with hint; duplicate works and the copy is owned by the visitor.
- `T-N06-5` daily cap reached → agent calls served from replay; uncached request → designed "budget used" error,
  not 500; banner flag in `/features`.
- `T-N06-6` concurrency: two sessions started → second queued with position 1; it starts when the first ends.
- `T-N06-7` secret scan: crawl every GET route (test client) and assert no response contains the configured key
  values; also scan the built web bundle (`web/dist`) for key-like strings.
- `T-N06-8` cleanup deletes only visitor projects older than 48 h; samples untouched.
- `T-N06-9` run artifact routes reject traversal ids (`T-F11-2`).
- `T-N06-10` (deployed) `scripts/smoke_public.py <URL>`: HTTPS, health green, samples listed, one trajectory
  downloaded, one Tier 1 call, one copilot call (when budget allows), SSE stream opens through the proxy.
- `T-N06-11` (deployed) `scripts/load_public.py <URL>`: 20 concurrent virtual visitors browsing samples for 2 min →
  p95 < 800 ms for JSON routes, no 5xx; 3 concurrent copilot requests → 1 runs, 2 queue, all finish or get 429.

---

### N07 — Live Ops console: the day-of mode (P1)

**Why:** "Design" and "Impact": the product continues after planning, into the event night. Uses only computed
numbers (Tier 1, weather, countdown), so it is honest and fast.

**Behaviour** (opened from *Your plan* › **Go live**; implemented as a full-screen page `/p/:projectId/live`,
plus a `live` mode in Expert view where `Mode` in `web/src/state/ui.ts` gains `"live"`):

1. Big clock in the venue time zone, countdown chip enlarged: "Latest safe time to start evacuating 21:47"
   with the formula on click (existing countdown).
2. **Headcount now:** per zone, enter current people (or one total split by plan ratios). Recompute Tier 1 →
   "If you evacuate now: evacuation time (95%) 4 min 12 s (instant estimate)" and exit loads.
3. **Wind watch** (outdoor): refresh Open-Meteo every 10 min (cached per hour); amber at gust ≥ 80 % of stage
   limit, red at ≥ 100 %; shows the next crossing time.
4. **Exit status:** toggle an exit as blocked (same op as Break it yourself, but not saved as a version) →
   instant re-estimate and the countdown updates.
5. **Decision log:** every alert, headcount entry and exit toggle appended with timestamp and user note;
   export as CSV/HTML ("event log") for the post-event report.
6. Works offline after load (no LLM needed). Optional: a "Brief me" button where the `fast` model writes a
   2-sentence status that must pass the number check.

**Contracts / code**

- `api/models/live.py`: `LiveStatusRequest{counts: {zone_id: int}, blocked_exits: list[str]}`,
  `LiveStatus{tier1, countdown, alerts: [{level, text, at}], wind?: {...}}`, `LiveLogEntry{at, kind, text, data}`.
- `api/orchestrator/live_ops.py`; routes `POST /projects/{id}/live/status`, `GET/POST /projects/{id}/live/log`,
  `GET /projects/{id}/live/log.csv`.
- Table `live_log` (migration 0002).
- Web: `web/src/panels/LivePanel.tsx`, `ToolRail`/`TopBar` mode switcher entry, keyboard `L`.

**Tests**

- `T-N07-1` headcount scaling: counts equal to the plan reproduce the plan's Tier 1 result exactly; doubling counts
  never decreases evacuation time.
- `T-N07-2` blocked exit raises evacuation time and moves the countdown earlier (when a hazard exists).
- `T-N07-3` alert thresholds 80 %/100 % with a stored forecast snapshot; no hazard → no alert, explicit copy.
- `T-N07-4` log entries persist across restart; CSV export has a header and one row per entry.
- `T-N07-5` counts exceeding zone capacity are accepted but flagged ("over plan by 20 %").
- `T-N07-6` (e2e) open Wellington sample → Live → enter counts → see estimate and wind status.

---

### N08 — Steward briefing pack with translation (P1)

**Why:** the plan must reach the people at the gates. Bangla support makes the Bangladesh use case concrete
(Ramna Park, Suhrawardy Udyan samples) and shows Nemotron's multilingual ability with a hard number guarantee.

**Behaviour**

1. Report tab › **Steward pack** (language: English, Bangla; more later).
2. **Positions are computed, not generated:** one steward post per exit (more for exits with load above
   average from Tier 1), one per hotspot cluster from the latest run, remaining stewards spread over zones by
   people. Total = the "stewards" estimate (F04); if posts exceed it, show the shortfall.
3. Each card (one per post, printable A6/A5 per page): post name and map crop (SVG from `export_svg_map` geometry),
   "Direct people to: East door" (Tier 1 assignment), "If East door is blocked: send people to South gate 2"
   (from red-team fixes or next-best exit), radio call sign, 3 plain-language instructions written by the `fast`
   model from a fixed template and facts dict.
4. **Translation with locked numbers:** before translation, replace every number and every venue name with
   placeholders `⟦1⟧, ⟦2⟧ …`; the `main` model translates; code checks that every placeholder appears exactly
   once, then restores them. Failure → regenerate once → fall back to English for that card with a note.
5. Export via a new Exporter plugin `plugins/export_steward_pack/` (HTML, print CSS), route
   `GET /projects/{id}/stewards.html?lang=bn` (and session variant).

**Tests**

- `T-N08-1` positions are deterministic for a given run; every open exit has ≥ 1 post; total equals the estimate
  or the shortfall is reported.
- `T-N08-2` placeholder round-trip: all numbers and names restored byte-identical; a translation that drops or
  duplicates a placeholder is rejected.
- `T-N08-3` English card text passes the number check (only numbers from facts).
- `T-N08-4` exporter HTML has one card per post, the disclaimer, and `lang` attribute set (`bn` for Bangla).
- `T-N08-5` LLM unavailable → template English instructions, pack still exports.
- `T-N08-6` (live eval) 10 cards translated to Bangla on Nebius: 10/10 placeholder-valid after ≤ 1 retry.
- Human check (once): a Bangla speaker reads 3 cards for correctness; record the result in PROGRESS.

---

### N09 — Share link for permit offices (P2)

**Behaviour:** Report › **Share** creates a read-only link (`/share/<token>`) to the latest report, with expiry
(7 days default) and revoke; shows a QR code for printing. The page is the HTML report plus the 3D snapshot
images; no edit routes are reachable with the token.

- Token: 128-bit random, URL-safe; store only its SHA-256 (`share_link` table, migration 0002).
- QR: dependency `segno` **[VERIFY licence; add to `docs/LICENSES.md`]** or omit QR if not acceptable.
- Routes: `POST /projects/{id}/share`, `DELETE /shares/{id}`, `GET /share/{token}` (HTML).

**Tests:** `T-N09-1` valid token → 200 HTML with disclaimer; `T-N09-2` expired → 410, revoked → 404, unknown → 404;
`T-N09-3` token gives no access to `/api/v1/projects/*`; `T-N09-4` only the hash is stored.

---

### N10 — Validation lab: simulator vs real experiments (P1)

**Why:** "One clear validation chart does more for credibility than any claim" (project brief section 14). It
backs every number in the product.

**Behaviour**

1. `scripts/validate_bottleneck.py` (new): reproduce a published bottleneck series (Wuppertal 2018 bottleneck
   series, https://doi.org/10.34735/ped.2018.1, and/or Jülich archive bottleneck experiments
   **[VERIFY dataset URLs, file format and licence; record in `docs/LICENSES.md`; download in
   `scripts/get_data.sh`, never commit raw data]**). For each bottleneck width `b`, build the corridor geometry in
   JuPedSim with the experiment's dimensions and headcount, run 3 seeds, measure flow with PedPy at the same
   measurement line as the experiment, and compute measured flow from the trajectories with the same PedPy method.
2. Output `api/data/validation.json`: per width `{b_m, measured_flow_ps, simulated_flow_ps: {median, min, max},
   error_pct}` + metadata (dataset, method, engine version, agent radius, date).
3. Help page section "How good is the simulator?" and a report appendix: chart of flow vs width, measured vs
   simulated, and the honest error. **Do not tune parameters to fit silently**: if we change anything, record it
   in ASSUMPTIONS with before/after numbers.
4. Target: median error ≤ 15 % across widths (brief section 14). If missed, publish the real error and explain the
   known model limits (CFSM, no pushing forces).
5. Also add the Indiana check (brief section 14): friction-only ballast model fails in the 25–43 mph range;
   reported in the same JSON and chart notes.

**Tests:** `T-N10-1` `validation.json` validates against its Pydantic model and every width has ≥ 3 seeds;
`T-N10-2` Help page renders the chart from the JSON (vitest component test); `T-N10-3` (slow) the script runs one
width end-to-end on a small headcount in the sim image.

---

### N11 — Judge landing and 90-second guided tour (P0, small; part of the N14 Home screen)

**Why:** judges give each project a few minutes. The first screen must show value without reading.
This is the sample/tour row of the N14 *Describe* screen, not a separate page.

**Behaviour**

1. First visit to the public URL (no projects of their own): under the *Describe* box, three buttons:
   **Watch a 90-second tour** (guided tour across the T-alley sample: 3D → red team cards → branch tree → compare →
   countdown → report), **Plan an event with Nemotron** (Autopilot prefilled with the Ramna Park example),
   **Open a sample**.
2. Autopilot shows "Live on Nemotron (Nebius)" when budget allows; otherwise "Replay of a recorded run on
   `<date>`" (honest label) using a recorded Autopilot event stream stored with the samples.
3. Tour reuses `web/src/panels/Tour.tsx` (narration via browser speech synthesis, Esc to stop, mute).
4. Footer on every page: "Planning aid, not a safety certification" · GitHub link · "How it works" (Help).

**Tests:** `T-N11-1` (e2e) fresh browser context → hero visible → tour runs through all steps without errors
(console clean); `T-N11-2` budget-exhausted flag → Autopilot shows the replay label; `T-N11-3` axe scan of the
landing page has no serious/critical violations.

---

### N12 — Repo and submission compliance (P0)

1. Copy `nebius/LICENSE` (Apache-2.0) to `./LICENSE` at the repo root (keep both identical). Verify on GitHub that
   "Apache-2.0 license" appears in the repo sidebar/header after push (human, H10).
2. `.github/workflows/ci.yml` at the **repo root** (GitHub only reads workflows there), with
   `defaults.run.working-directory: nebius`. Jobs: (a) python: setup uv, `uv sync` in `api`, ruff check + format
   check, lint-imports, mypy (same targets as `make typecheck`), `pytest -m "not slow and not nebius and not tavily
   and not live"`; (b) web: Node 22, `npm ci`, eslint, `tsc -b --noEmit`, vitest, `vite build`; (c) sim (manual or
   on main): build sim image, `pytest ../sim/tests`. Add `pip-audit` and `npm audit --omit=dev` (non-blocking
   report). No secrets needed. Fix `CHANGELOG.md` line 69 so it is true.
3. Root `README.md`: keep it short but add (a) "How we use NVIDIA Nemotron and Nebius" table (copy from
   `nebius/README.md`, updated with live facts), (b) demo URL and video link at the top, (c) "Feedback" link,
   (d) "Built during the hackathon (started 2026-10-08)" line. Every claim must be true at submission time.
4. Fix stale path in `docs/TESTING_GUIDE.md` (G8).
5. `docs/FEEDBACK.md` rewritten into the official structure (section 9.2) with live observations.
6. Add pytest markers `tavily` and `live` to `api/pyproject.toml` (`nebius` and `slow` exist).

**Tests:** `T-N12-1` CI passes on a branch push (human pushes when asked); `T-N12-2` `scripts/check_claims.py`
(new): asserts README files mention only providers whose health was green in the last recorded live smoke
(reads `docs/evals/latest.json`), and that `./LICENSE` equals `nebius/LICENSE`.

---

### N13 — Autopilot: one click from a sentence to a stress-tested, fixed plan (P0, the story)

**Why:** today the organizer must run the Copilot, then a stress test, then Red Team Night, then apply fixes, then
export, across four modes. The story is "AI automates the tedious work". Autopilot makes that literal.

**Behaviour**

1. Input: one sentence (or an existing project) + depth:
   - **Quick** (default on the public demo): brief → venue → estimates → baseline quick simulation (Tier 2) →
     one red-team round with 3 attacks screened by instant estimate, the worst 2 simulated → up to 2 fixes each →
     apply kept fixes → full simulation (Tier 3) of before/after under the worst attack → plan + report.
   - **Thorough:** as quick, plus the six-scenario sweep, up to 3 rounds × 5 attacks, multi-seed ranges on the final
     plan (N05, 5 seeds on Nebius, 1 locally), steward pack (N08) and web brief (N02).
2. Every step emits events; the *AI at work* screen (N14) shows them as plain-language steps with time and cost.
3. Budget: `budget_usd` (default from settings; demo default from `DEMO_MAX_USD_PER_PLAN`, e.g. 0.25
   **[set after N16 measurement]**) and the existing session caps. When a budget runs out, Autopilot finishes with
   what it has and labels the plan "partial: <reason>".
4. Stop button: finishes gracefully (reuse session stop).
5. Result: a project with a new version "Plan by Autopilot" (fixes applied), the session summary, the report, and
   the cost record. The user lands on *Your plan*.

**Design: extend the existing LangGraph graph, do not build a second orchestrator.**

- `api/orchestrator/copilot_graph.py`: after the existing nodes (brief → site → layout → ratios → project →
  simulation → sweep → safety officer), add nodes `red_team` (runs the existing `session.py` loop with an Autopilot
  config), `apply_fixes` (existing `/sessions/{id}/apply` logic as a function), `confirm` (already part of the
  session), `deliver` (report + optional steward pack + cost record). Conditional edges skip `sweep` and the steward
  pack in quick depth. `GET /copilot/graph` then shows the full Autopilot graph automatically.
- `api/orchestrator/autopilot.py` (new, thin): presets for quick/thorough → graph config; persistence; SSE fan-out.
- Contracts `api/models/autopilot.py`: `AutopilotRequest{text?: str, project_id?: str, depth: "quick"|"thorough",
  budget_usd?: float}`, `AutopilotStep{key, label, status: "pending"|"running"|"done"|"skipped"|"failed", started_at?,
  finished_at?, cost_usd, detail?}`, `AutopilotRun{id, project_id?, session_id?, status, depth, steps, cost: CostRecord,
  partial_reason?, created_at, finished_at?}`.
- Routes `api/app/routes_autopilot.py`: `POST /autopilot` (202) → run; `GET /autopilot/{id}`;
  `GET /autopilot/{id}/events?after=` (SSE, same framing as session events, ends with `event: end`);
  `POST /autopilot/{id}/stop`; `GET /projects/{id}/autopilot` (latest run).
- SessionEvent `status.phase` gains Autopilot step keys (additive). Steps map to friendly labels in `en.json`:
  "Understanding your event", "Building the venue", "Checking capacity and staff", "Simulating the crowd",
  "Trying what could go wrong", "Fixing the weak spots", "Confirming the fixes", "Writing your plan".
- Table `autopilot_run` (migration 0002).

**Tests**

- `T-N13-1` (integration, fake LLM + fake runner) quick Autopilot from a sentence ends `finished` with: a project,
  ≥ 1 baseline run, a session summary, exactly one applied version, a report URL, a cost record whose total equals
  the sum of `agent_call` costs.
- `T-N13-2` thorough depth adds sweep runs and the steward pack; quick does not (steps marked `skipped`).
- `T-N13-3` LLM down → rule-based attacks/fixes; Autopilot still delivers a plan labelled with the outage.
- `T-N13-4` budget hit mid-red-team → `partial_reason="budget"`, plan still delivered with what exists.
- `T-N13-5` stop → `stopped`, partial plan, no orphan running sims (fake runner reports none active).
- `T-N13-6` SSE `?after=` replays later events only; `/copilot/graph` includes the new nodes and edges.
- `T-N13-7` existing project as input skips brief/site/layout and starts at simulation.
- `T-N13-8` (live eval) quick Autopilot on 3 sentences on Nebius finishes; record wall time and cost (feeds N16).

**Done when:** tests green; quick Autopilot on the Ramna Park sentence finishes on Nebius in a time and cost we
record and publish; the user lands on *Your plan* without touching any other screen.

---

### N14 — Simple UI: three screens and an Expert view (P0, design)

**Why:** gap G12. The judging "Design" criterion rewards a coherent product. An organizer should go from a sentence
to a plan they can hand over with **one** decision (pressing *Plan it*).

**Principles (apply to every screen in the simple flow)**

1. One primary action per screen, visually dominant.
2. At most **three numbers** on first view; everything else one click away ("Show details").
3. Plain language. No "Tier 1/2/3" (say "instant estimate", "quick simulation", "full simulation"), no machine ids,
   no jargon without a Help link. Keep the mandatory vocabulary (section 0 rule 8).
4. The 3D venue is the hero; panels never cover more than 40 % of the width on desktop.
5. Progressive disclosure: advanced controls live in Expert view, not hidden in menus on the simple screens.
6. Works on a phone (390 × 844) for *Describe* and *Your plan*; *AI at work* readable on a phone; Expert view
   desktop only (≥ 1280 px, as today).

**Screen A — Describe (Home, route `/`)**

- Big text box "Describe your event" with placeholder from the Ramna Park example, depth toggle (Quick / Thorough,
  default Quick), primary button **Plan it**.
- Three example chips (concert in a park, conference with a balcony, festival in wind).
- Row "See it work": **90-second tour** (N11) and the three sample cards.
- "Your plans" list below (cards with verdict colour and date); empty state copy from CLAUDE.md 4A.4.
- Small link "More ways to start" → today's New project dialog (Describe it / Real place / Template).
- Removed from Home: the templates grid (moved into "More ways to start").

**Screen B — AI at work (route `/autopilot/:id`)**

- Left (or top on phone): the eight Autopilot steps (N13) with status, elapsed time and cost; the current step
  expanded with one plain sentence ("Testing 3 things that could go wrong; 2 need a simulation").
- Right: the 3D venue appears as soon as it exists; the latest finished simulation replays automatically with the
  density heatmap; attack and fix cards slide in compactly.
- Footer: live cost "$0.03 so far · 14 scenarios screened instantly · 4 simulated · Nemotron on Nebius" (N16).
- Buttons: **Stop** (secondary). When done: auto-navigate to *Your plan* (with a 2 s "Done" state; respect
  reduced motion).
- Expert link "Show the agent graph" opens the existing `AgentGraph` in a side sheet.

**Screen C — Your plan (route `/p/:projectId`, default view of a project)**

- Verdict banner: *This plan holds* / *at risk* / *fails* + one sentence from the judge text (number-checked).
- Three numbers: **Safe capacity**, **Evacuation time (95%)** (with range if N05 ran), **Latest safe time to start
  evacuating** (or "No hazard in forecast window").
- "What the AI changed": kept fixes as rows "Added East door 3 m: evacuation time 311 s → 169 s" with
  **Show in 3D** (before/after toggle on the 3D view).
- "Top risks it found": up to 3 compact attack cards with their source link (incident or live web).
- "Cost of this plan" line (N16).
- Primary button **Download report**; secondary: **Steward cards** (N08), **Go live** (N07), **Share** (N09 if built).
- Bottom: "Ask or change anything" box (N15). Changing the plan offers **Re-run Autopilot** (quick) afterwards.
- Link **Expert view** → today's Workspace (`/p/:projectId/expert`), which keeps Plan / Simulate / Red Team / Report.
  The choice is remembered per browser (localStorage with try/catch).

**Expert view cleanup (small, do not redesign):** move Showtime lights, tour and layers into one "View" menu; move the
cost meter into a popover on the provider badge; group Estimates + What-if under "Plan for the day". Keep shortcuts.

**Code**

- `web/src/pages/Home.tsx` (new, replaces Projects as `/`; keep `Projects.tsx` logic for the list and reuse its query
  hooks), `web/src/pages/AutopilotRun.tsx` (new), `web/src/pages/PlanSummary.tsx` (new), route changes in
  `web/src/app/App.tsx` (old project URLs redirect to the new ones), `web/src/api/queries.ts` hooks for Autopilot,
  `web/src/api/useAutopilotStream.ts` (copy of `useSessionStream.ts` pattern), strings in `en.json`.
- Reuse existing components: `VenueModel`/`SceneRoot`, `ScoreGauge` (verdict colours), `RedTeamPanel` card parts,
  `ReportView`, `Tour`.

**Tests**

- `T-N14-1` (e2e) simple journey: Home → type sentence → Plan it → AI at work shows steps advancing → lands on Your plan
  with verdict, three numbers and Download report; **≤ 2 clicks** after typing (Plan it, Download report).
- `T-N14-2` (e2e) phone viewport 390 × 844: Home and Your plan have no horizontal scroll and all primary buttons are
  visible without zooming.
- `T-N14-3` (e2e) Expert view link opens the old workspace with the same project and version; back returns to Your plan.
- `T-N14-4` (e2e) old URLs still work (redirect).
- `T-N14-5` (a11y) axe: no serious/critical issues on the three screens; every button has an accessible name; focus
  order follows the visual order.
- `T-N14-6` (vitest) "three numbers" component renders "No hazard in forecast window" and range text correctly.
- `T-N14-7` (lint script) no string on the simple screens contains "Tier", "tier1", "run_id" or a raw id pattern
  (`/[a-z]+_[a-z0-9]+/` on visible text in the three page components).
- `T-N14-8` (manual, recorded in PROGRESS) a person who has never seen the app gets from Home to a downloaded report
  without help; note where they hesitated and fix it.

**Detailed screen specs, copy, states and UI tests:** section 5A (it is part of this feature).

**Done when:** all tests green; every item of the 5A.9 checklist ticked for the three screens; screenshots (light and
dark, phone and desktop) reviewed against the principles above and 5A; TESTING_GUIDE rewritten to start with the simple flow.

---

### N15 — "Ask or change anything": one box with an intent router (P1)

**Why:** today there are three separate inputs (command bar edits, Ask the venue, what-if sliders). One box is simpler
and shows Nemotron understanding the organizer.

**Behaviour**

- The `fast` role classifies the text into `{intent: "edit"|"question"|"what_if"|"navigate"|"other", ...}` with a JSON
  schema; `what_if` extracts `{crowd_scale?, weather?: "rain"|"smoke"|"none", closed_exits?: [names]}`.
- `edit` → existing Venue agent with `apply=false`, shows the preview in 3D, user confirms **Apply** (never applied
  silently on the simple screens); after applying, offer **Re-run Autopilot**.
- `question` → existing explainer (`/ask`), number-checked; uses the latest run.
- `what_if` → existing `/projects/{id}/whatif` with the extracted parameters; numbers come from code.
- `navigate` → UI action (open report, go live, open expert view).
- `other` → polite "I can change the plan, answer questions about the results or try what-ifs" with examples.
- LLM unavailable → keyword fallback (`add|remove|move|set` → edit; `what if|if it rains|close` → what_if; `why|how`
  → question).

**Code:** `api/agents/router.py` + `prompts/router.md`; `POST /projects/{id}/ask-anything` →
`{intent, result}` where result is the existing response shape of the target route; `web/src/panels/AskAnything.tsx`.

**Tests:** `T-N15-1` eval set of 20 utterances (5 per intent) routed correctly ≥ 18/20 on Nebius, ≥ 16/20 locally;
`T-N15-2` what-if parameter validation (scale clamp 0.25–3, unknown exit names rejected with the list of names);
`T-N15-3` edit is never applied without the confirm call; `T-N15-4` keyword fallback routes the 20 utterances
≥ 14/20 with the LLM down; `T-N15-5` (e2e) type "what if it rains?" on Your plan → evacuation time changes and says
"instant estimate".

---

### N16 — Cost efficiency: measured cost per plan, screening funnel, model escalation (P0, the story)

**Why:** "cost efficient" is half of the story and must be proven with numbers from our own runs, not claimed.

**What already saves cost (record it, show it):** role routing by model size; Tier 1 screening before simulation;
content-addressed run cache (same venue + seed + events → same run, `test_run_is_idempotent_and_cached`); LLM
record/replay cache; compact venue summaries in prompts; per-session token, run and wall-clock budgets.

**New**

1. **Cost record** per Autopilot run and per session: `CostRecord{usd_total, tokens_in, tokens_out, by_role: {role:
   {calls, tokens_in, tokens_out, usd}}, by_model, sim: {instant_estimates, quick_sims, full_sims, sim_seconds,
   cache_hits}, llm_cache_hits, wall_s}`. Built from existing `agent_call`, `run_started/finished` and `tool_call`
   events; persisted in the run row.
2. **Screening funnel** shown everywhere a session or Autopilot result appears: "18 scenarios screened instantly →
   5 quick simulations → 2 full simulations". Emitted as part of `score` events (additive fields).
3. **Model escalation policy:** a call on the `fast` role that fails validation after its repair call is retried once on
   `main` (logged as `escalated: true` in `agent_call`); `judge` is used only by the judge and safety officer. Setting
   `LLM_ESCALATE=true` (default true).
4. **Cost card** on *Your plan* and in the report ("How this plan was made"): total cost, models used, simulations by
   kind, compute time, time taken. No comparison with consultant prices unless a cited source is added to
   ASSUMPTIONS; otherwise say "compare with your current planning time and cost".
5. **Measurement** (`scripts/measure_cost.py`, part of `make eval`): quick and thorough Autopilot on the 3 samples
   and the Ramna Park sentence on Nebius; writes `docs/evals/cost-<date>.json` with median and max per depth. README,
   video and Devpost quote these numbers only.

**Tests:** `T-N16-1` cost record totals equal the sum of events (fake session); `T-N16-2` funnel counts equal the
numbers of Tier 1 screenings, Tier 2 and Tier 3 runs in the event stream; `T-N16-3` escalation: fake `fast` returns
invalid JSON twice → one `main` call, result valid, `escalated: true`; `T-N16-4` cache hits counted when a run is
reused; `T-N16-5` cost card renders local runs as "$0.00 (local model)" and Nebius runs with prices from settings;
`T-N16-6` claims check (N12) fails if README quotes a cost not present in `docs/evals/cost-*.json`.

---

### N17 — Open formats: export a scenario for the user's own simulation tools (P2)

**Why:** "we use existing simulation software" also means experts can check our work in theirs.

**Behaviour:** Expert view › Simulate › **Export scenario**: a zip with the venue geometry (WKT + GeoJSON), agent start
areas and counts, exits, events, seed and engine parameters, plus a standalone Python script that runs the same
scenario with JuPedSim (the same code path as `sim/jps_build.py`, vendored into the zip) and a README.

**Tests:** `T-N17-1` exported script runs inside the sim image and reproduces the original run's evacuation time (95%)
within 1 % (same seed); `T-N17-2` zip contains the licence notices for JuPedSim (LGPL) and our code.

---

### N18 — Event research: web-sourced, cited input suggestions (P1)

**Why:** organizers rarely know their own numbers (last year's attendance, venue capacity, which gates exist). A
guessed input makes every simulation wrong. Tavily finds the numbers; the organizer decides. Central Tavily use for
the prize and the first moment of the demo ("Last year's attendance ≈ 40,000 (source). Use this?").

**Behaviour**

1. Runs inside the N02 `evidence_desk` Copilot node, after the event brief: place, event name and date come from
   the brief.
2. Backend runs 2–4 Tavily searches (e.g. `"<event> <place> attendance"`, `"<venue> capacity"`, `"<venue> gates
   entrances"`, `"<venue> crowd crush OR stampede"`), then `extract` on the top 3 distinct URLs.
3. The `fast` role proposes suggestions, each
   `{field, value, unit, source_url, quote, published?}` where `field` is from a fixed enum the venue/event model
   understands: `expected_attendance`, `venue_capacity`, `gate_count`, `peak_arrival_window_min`.
4. **Verification in code (same as N03):** `source_url` ∈ extracted URLs; `quote` appears in the extracted text
   after whitespace/case normalisation; `value` appears inside the quote; units converted by code. Failures are
   dropped and counted ("2 suggestions dropped: quote not found on the page").
5. UI (Describe screen and Copilot result card): each suggestion is labelled "Found on the web, not verified" with
   the quote, link and date, and **Accept / Edit / Reject**. Accepted values enter the event/venue with provenance
   `web` (alongside imported, assumed, organizer-confirmed and measured), plus source URL and acceptance date.
   Edited values become organizer-confirmed and keep the link.
6. **Offline / no key / budget exhausted:** step skipped, empty state "Live search is off. Enter numbers
   yourself." The Copilot never fails because of this step.

**Contracts**

- `api/models/evidence.py`: `InputSuggestion{field, value, unit, source_url, quote, published?, status:
  "suggested"|"accepted"|"edited"|"rejected"}`; `WebBrief` gains `suggestions: list[InputSuggestion]` and
  `dropped: int`.
- Accepted suggestions are added to the session summary `sources` (N02) with `used_by` set to the field name.

**Code**

- `api/orchestrator/evidence.py`: `research_event(st, brief, budget) -> list[InputSuggestion]`; reuses `st.search`,
  the disk cache and the per-run `SearchBudget`.
- `api/agents/event_research.py` + `prompts/event_research.md` (new, role `fast`); quote verification shared with
  N03 (one helper, e.g. `api/core/quotes.py`).
- Web: suggestion list in the Describe screen / Copilot card; strings in `en.json`.

**Tests**

- `T-N18-1` (unit, fake Tavily) suggestion with a quote not on the page, or a value not in the quote, is dropped
  and counted.
- `T-N18-2` (unit) unknown `field` or unit → dropped.
- `T-N18-3` (unit) budget exhausted / no key / `OFFLINE=true` → empty suggestions, Copilot completes.
- `T-N18-4` (unit) accepted suggestion sets provenance `web` with URL and date; edited → organizer-confirmed.
- `T-N18-5` (e2e, recorded session) accept a suggestion; the value appears in the venue inputs and in the report
  Sources section.

**Done when:** on the Ramna Park sample at least one accepted web-sourced input reaches the simulation and is
listed in the report Sources (or the empty state explains honestly why none were found).

---

### N19 — Fix guidance: blue team fixes cite trusted safety guidance (P2)

**Why:** "add a second exit lane" is more credible with "recommended by (official guidance)" next to it.

**Behaviour:** for each blue-team fix type in a round (not each fix), one Tavily search with `include_domains`
limited to a configured list of trusted guidance sources (e.g. the UK Green Guide publisher, HSE, national fire
codes; list in settings, never chosen by the model). `extract` the top hit; attach `{source_url, quote}` to the fix
only when the quote verifies (shared N03 helper). The fix card shows "Guidance: (source)". Guidance never blocks or
ranks a fix; it is context only. Offline / no key → no guidance line.

**Tests:** `T-N19-1` unverified quote dropped; `T-N19-2` a hit outside the domain list is rejected; `T-N19-3` offline
→ fixes unchanged, no guidance line; `T-N19-4` at most one search per fix type per round (cached on repeat).

---

### Migration 0002 (one migration for all new tables, written in M12, extended only before M17)

To avoid migration churn, create `0002_hackathon_features.py` once with: `project.owner_ws` (nullable string,
index), `project_rule`, `ensemble`, `live_log`, `share_link`, `usage_day`, `autopilot_run`. Downgrade drops them. Test
`T-M2-1`: upgrade from a database created at 0001 with data keeps every project and version; downgrade then upgrade
is clean. If a later milestone needs a column change, add `0003_*` (never edit 0002 after it is committed).

---

## 5A. Ease-of-use specification (every screen)

This section is the contract for N14 and for every screen a new feature touches. The goal: **an event organizer
who has never seen Showtime, and has no simulation or software background, gets a plan they can hand over without
help, without reading docs, on a laptop or a phone.** It builds on the design system in CLAUDE.md 4A (palette
tokens in `web/src/styles.css`, Public Sans, 4 px grid, Radix controls, lucide icons, `sonner` toasts) and changes
nothing in it; it adds rules for simplicity.

### 5A.1 Measurable usability goals

| Goal | Target | How it is measured |
| --- | --- | --- |
| First plan without help | ≥ 90 % of first-time testers reach a downloaded report | Usability test (5A.7), task 1 |
| Effort | ≤ 2 clicks after typing the sentence (Plan it, Download report) | `T-N14-1` |
| Time on task (excluding AI wait) | ≤ 90 s from landing to pressing Plan it; ≤ 60 s from Your plan to downloaded report | Usability test timings |
| Understanding | ≥ 4 of 5 testers can say in their own words what the AI changed and why, from Your plan only | Usability test, task 2 |
| Satisfaction | System Usability Scale (SUS) ≥ 80 (average of testers) | SUS questionnaire after the test |
| Errors | Every error state has a one-click way forward; no dead ends | `T-UX-3`, error catalogue (5A.6) |
| Phone | Describe, AI at work, Your plan, Go live and Steward cards usable at 390 × 844 | `T-N14-2`, `T-UX-5` |
| Accessibility | WCAG 2.2 AA; zero serious/critical axe violations | `make a11y` |
| Speed | Home interactive < 2.5 s (LCP) on the deployed demo over broadband; every click answers within 100 ms (spinner, skeleton or result) | Lighthouse run on the deployed URL, recorded in PROGRESS |

### 5A.2 Global rules (apply everywhere)

**Layout and controls**

1. **One primary button per screen**, filled `signal` colour, bottom-right of its card or the main column; everything
   else is secondary (outline) or a text link. Never two filled buttons side by side.
2. **Same place, same thing:** header (logo → Home, "Your plans", "Help", provider/cost badge, theme toggle) is
   identical on every simple screen; back arrow top-left on every screen that is not Home.
3. **Touch targets ≥ 44 × 44 px** on the simple screens (CLAUDE.md allows denser controls only in Expert view).
4. **Body text ≥ 16 px** on the simple screens, line length ≤ 75 characters, numbers in tabular figures.
5. **No hover-only information.** Anything in a tooltip must also be reachable by tap/focus (Radix Tooltip + a
   visible "?" button for phone).
6. **No modal for routine work.** Dialogs only for: deleting a plan, leaving with an Autopilot running, sharing.
   Everything else is inline.
7. **Autosave everywhere**, no Save buttons on the simple screens (versions exist; say "Saved" quietly).
8. **Undo instead of confirm:** destructive-but-reversible actions (apply a change, remove an exit) happen at once
   with a toast "Removed East door · Undo" (sonner action, 8 s). Only deleting a whole plan asks first.
9. **Progressive disclosure:** "Show details" expanders, never more than one level deep on simple screens; deeper
   material goes to Expert view or Help.

**Words**

10. **Plain language:** sentences ≤ 15 words on simple screens; reading level about grade 8 (check with a readability
    script on `en.json` simple-flow keys, `T-UX-6`). Buttons are verbs ("Plan it", "Download report", "Go live").
11. **Forbidden on simple screens** (lint, `T-N14-7`): "Tier", "RSET", "CFSM", "p95", "seed", "run_id", "venue_hash",
    raw ids like `door_e1`, "JSON", "SSE", "LLM". Use: "instant estimate", "quick simulation", "full simulation",
    "evacuation time (95%)", exit names shown in 3D, "AI".
12. **Every number has a unit and a source tag:** "Evacuation time (95%) **4 min 12 s** · confirmed by simulation"
    or "· instant estimate". Tapping the number opens "Where this number comes from" (existing traceability).
13. **Glossary terms** (people per m², evacuation time (95%), latest safe time to start evacuating, red team) have a
    dotted underline and open a one-sentence definition (existing glossary route `/api/v1/glossary`).
14. **Sentence case, no exclamation marks, no apologies**, errors say what happened and what to do (CLAUDE.md 4A.4).

**Feedback and states**

15. **Never a blank screen:** every async view has a skeleton within 100 ms, then content; anything > 3 s says what is
    happening and roughly how long ("Simulating 6,000 people · about 2 minutes").
16. **Five designed states** for every view: loading, empty, error, partial, offline (CLAUDE.md 4A.4). Listed per
    screen in 5A.4.
17. **The disclaimer** "Planning aid, not a safety certification" in the footer of every simple screen and on every
    exported document.
18. **Colour is never the only signal:** verdict uses colour + icon + word (Holds ✓ / At risk ! / Fails ✕ via lucide
    icons); danger in 3D has an outline and a label.
19. **Motion** only to explain change (step completes, card arrives); `prefers-reduced-motion` turns it off.
20. **Keyboard:** everything reachable; visible focus ring; `/` focuses the main box on every simple screen; `Esc`
    closes sheets; shortcuts listed in Help.

### 5A.3 Navigation map

```
/                          Describe (Home)  ── "More ways to start" sheet
/autopilot/:runId          AI at work       ── auto-advances to Your plan
/p/:projectId              Your plan        ── default view of any plan
/p/:projectId/live         Go live (day-of console)
/p/:projectId/stewards     Steward cards (print view)
/p/:projectId/report       Report (print view, Download PDF)
/p/:projectId/expert       Expert view (today's Workspace: Plan / Simulate / Red Team / Report)
/settings                  Settings (simple first, "Advanced" collapsed)
/help                      Help (tasks first, then glossary, then "how numbers are computed")
/share/:token              Shared report (read-only, N09)
```

Old routes (today's project and workspace URLs) redirect to the new ones (`T-N14-4`). The header never shows the
Expert view entry on phones (desktop only, ≥ 1280 px); on a phone, Expert links say "Open on a computer for the
expert view".

### 5A.4 Screen specifications

Each screen lists: purpose · wireframe · elements and copy · states · interactions · tests. Copy below is the
English source text; keys go into `web/src/i18n/en.json` under new groups `home`, `autopilot`, `plan`, `ask`,
`live`, `stewards`.

#### A. Describe (Home, `/`)

**Purpose:** get one sentence and start Autopilot.

```
Desktop                                                      Phone
┌──────────────────────────────────────────────────────┐    ┌──────────────────────┐
│ [logo] Showtime            Your plans  Help  ● NEBIUS │    │ [logo]        ≡      │
│                                                      │    │ Plan a safe event    │
│   Plan a safe event in minutes                       │    │ in minutes           │
│   Describe it. AI builds, simulates and fixes it.    │    │ ┌──────────────────┐ │
│  ┌────────────────────────────────────────────────┐  │    │ │ Describe your    │ │
│  │ Describe your event…                           │  │    │ │ event…           │ │
│  │                                                │  │    │ └──────────────────┘ │
│  └────────────────────────────────────────────────┘  │    │ [chips, scroll →]    │
│  📍 Ramna Park  📅 16 Dec 18:00  👥 6,000  ⏱ 5 h      │    │ (•) Quick ( ) Thorough│
│  ( ) Quick · about 3 min   ( ) Thorough · about 10 min│    │ [   Plan it        ] │
│                                       [ Plan it  ▸ ] │    │ See it work          │
│  Try: Concert in a park · Conference with a balcony · │    │ [▶ 90-second tour  ] │
│       Festival on a windy day                        │    │ [sample] [sample] →  │
│ ──────────────────────────────────────────────────── │    │ Your plans           │
│  See it work   [▶ 90-second tour]  [sample][sample][sample]│ …                   │
│  Your plans    [card] [card] [card]      More ways to start │                   │
│  Planning aid, not a safety certification            │    │ Planning aid, not a… │
└──────────────────────────────────────────────────────┘    └──────────────────────┘
```

(Icons in the chip row are lucide icons, shown here as emoji only for the sketch.)

**Elements and copy**

- Title "Plan a safe event in minutes"; subtitle "Describe it. AI builds, simulates and fixes it."
- Text area (3 lines, grows to 6), label "Describe your event", placeholder "Victory Day concert at Ramna Park, Dhaka,
  16 December 6 pm, 6,000 people, 5 hours, with a bar".
- **"What I understood" chips** under the box, updated as the user types by a small client-side parser
  (`web/src/lib/briefHints.ts`, no AI call, no cost): place (text after "at"/"in"), date, time, people, duration,
  alcohol yes/no, indoor/outdoor words. Chips are hints only; the real brief comes from the event brief agent.
  Missing essentials show as amber chips: "How many people?" / "Where?". Tapping a chip focuses the text at that spot.
- Depth: radio "Quick · about 3 min" (default) / "Thorough · about 10 min" (times measured in N16, update the copy
  from `docs/evals/cost-*.json`).
- Primary **Plan it**. Disabled with reason "Add where and how many people" only if neither place nor people can be
  found by the hint parser **and** the text is under 20 characters; otherwise always enabled (the agent asks).
- Example chips fill the box (do not auto-start).
- "See it work": **90-second tour** + three sample cards (title, place, verdict badge, image thumbnail via existing
  `VenueThumb`).
- "Your plans": up to 6 cards, newest first, "Show all" link; each card: name, date, verdict badge, "Open".
- Link "More ways to start" opens a side sheet with three big choices: **Pick a real place on the map**,
  **Describe the venue in detail**, **Start from a template**, each opening today's corresponding tab.

**After Plan it:** if the event brief agent needs an answer (no place and no people), show one inline question card
under the box ("How many people do you expect?" with a number field and **Continue**), never a dialog. Otherwise go
straight to AI at work.

**States**

| State | What the user sees |
| --- | --- |
| Loading | Skeleton for samples and plan cards; the box is usable immediately |
| Empty (no own plans) | "No plans yet. Describe your event above, or watch the 90-second tour." |
| Error (server unreachable) | Banner "We can't reach the Showtime server. Retrying…" with **Try again**; on the public demo never mention `make up` (fix the current `errors.network` copy per environment) |
| Partial (AI budget used up on the demo) | Notice above the box: "Today's live AI budget is used up. You can still open the samples or watch a recorded plan." Plan it becomes "Watch a recorded plan" |
| Offline (browser offline) | Banner "You're offline. Samples you opened before still work." |
| Rate limited | Inline under the button: "You've planned 5 events this hour. Try again at 14:20, or open a sample." |

**Tests:** `T-UX-A1` hint parser unit tests (12 sentences incl. Bangla place names written in Latin script, "6k
people", "from 6 pm to 11 pm"); `T-UX-A2` e2e example chip fills the box and does not start; `T-UX-A3` question card
appears for "a concert" and Continue starts Autopilot; state screenshots for every row of the table.

#### B. AI at work (`/autopilot/:runId`)

**Purpose:** show progress honestly and make the wait interesting; never leave the user guessing.

```
Desktop                                                                Phone
┌───────────────────────────────────────────────────────────────┐    ┌──────────────────────┐
│ ← Ramna Park concert                       ● NEBIUS  $0.03     │    │ ← Ramna Park concert │
│ ┌──────────────────────┐ ┌──────────────────────────────────┐ │    │ Step 5 of 8          │
│ │ ✓ Understanding your │ │                                  │ │    │ Trying what could go │
│ │   event        4 s   │ │        3D venue (live)           │ │    │ wrong                │
│ │ ✓ Building the venue │ │   crowd replay of latest run     │ │    │ ▓▓▓▓▓▓▓▓░░░░ 2:10    │
│ │ ✓ Checking capacity  │ │                                  │ │    │ ┌──────────────────┐ │
│ │ ✓ Simulating crowd   │ │                                  │ │    │ │   3D (smaller)   │ │
│ │ ● Trying what could  │ │                                  │ │    │ └──────────────────┘ │
│ │   go wrong     2:10  │ └──────────────────────────────────┘ │    │ [attack card]        │
│ │   Testing 3 things;  │ ┌ What the AI is trying ──────────┐  │    │ Steps ▾              │
│ │   2 need simulation  │ │ [attack card] [attack card]      │  │    │ $0.03 · 14 screened  │
│ │ ○ Fixing weak spots  │ └──────────────────────────────────┘  │    │ [ Stop ]             │
│ │ ○ Confirming fixes   │                                       │    └──────────────────────┘
│ │ ○ Writing your plan  │  $0.03 so far · 14 scenarios screened │
│ │            [ Stop ]  │  instantly · 4 simulated · Nemotron   │
│ └──────────────────────┘                                       │
└───────────────────────────────────────────────────────────────┘
```

**Elements and copy**

- Eight steps from N13 with lucide icons: done ✓, running (spinner), pending ○, skipped (grey, "Skipped in Quick"),
  failed (! with one-line reason). Each shows elapsed time; the running step shows one plain sentence from the
  event stream.
- Overall progress bar with an honest estimate ("about 2 min left", computed from measured step durations in N16;
  if unknown, say "a few minutes").
- 3D view appears as soon as the venue exists; the latest finished simulation replays on loop with the heatmap;
  camera auto-orbits slowly (off with reduced motion). No controls other than drag/zoom.
- "What the AI is trying": compact attack cards (title, one-line why, source link) and fix cards (title, "kept" /
  "not kept" with the before → after number) as they arrive; max 4 visible, "Show all" for the rest.
- Footer: cost so far, funnel counts, model badge(s) "Nemotron Nano · Super · Ultra on Nebius" (or "local model").
- **Stop** (secondary): confirm dialog "Stop now? You'll get a partial plan with what's done so far." → Stop / Keep
  going.
- Leaving the page while running: the run continues on the server; Home shows it under "Your plans" as "Planning…"
  with a progress ring; returning resumes the stream (`?after=`).
- Done: step list all ✓, "Your plan is ready" for 2 s, then navigate to Your plan (button "Open your plan" also
  shown for reduced motion and screen readers; focus moves to it).

**States**

| State | What the user sees |
| --- | --- |
| Queued (demo concurrency) | "You're number 2 in line. Your plan starts in about 3 min." + **Watch a recorded plan meanwhile** |
| Step failed but recoverable | Step shows "!" + "Used a simpler method" (e.g. rule-based attacks); run continues |
| Run failed | "We couldn't finish this plan: <reason>." **Try again** (same text) and **Open what we have** if a project exists |
| Partial (budget/stop) | Lands on Your plan with a "Partial plan" banner naming what was skipped |
| Connection lost | "Reconnecting…" pill; the stream resumes from the last event; never resets the step list |
| Replay (recorded) | Pill "Recorded on 24 Oct · not live" at the top; cost shows the recorded value |

**Tests:** `T-UX-B1` (e2e, mocked stream) steps advance in order and the page navigates to Your plan on `end`;
`T-UX-B2` drop the SSE connection mid-run → reconnects with `?after=` and no duplicate cards; `T-UX-B3` queued state
renders with position; `T-UX-B4` failed step shows the fallback text and the run continues; `T-UX-B5` screen reader:
step changes are announced via an `aria-live="polite"` region (assert the region text updates).

#### C. Your plan (`/p/:projectId`)

**Purpose:** answer three questions at a glance: *Is it safe? What did the AI change? What do I do next?*

```
Desktop                                                                  Phone
┌─────────────────────────────────────────────────────────────────┐    ┌──────────────────────┐
│ ← Your plans   Ramna Park concert · v4 (Plan by Autopilot) Saved │    │ ← Ramna Park concert │
│ ┌───────────────────────────────────────────────────────────────┐│    │ ✓ This plan holds    │
│ │ ✓ This plan holds   with the 2 changes below. Start evacuating ││    │ ┌──────────────────┐ │
│ │   by 21:47 if the forecast gusts arrive.          [Download report]│ │ Safe capacity    │ │
│ └───────────────────────────────────────────────────────────────┘│    │ │ 6,400 people     │ │
│ ┌ Safe capacity ─┐ ┌ Evacuation time (95%) ┐ ┌ Start evacuating by ┐│    │ ├──────────────────┤ │
│ │ 6,400 people   │ │ 9 min 40 s (9:20–10:05)│ │ 21:47               ││    │ │ Evacuation time  │ │
│ │ instant estim. │ │ confirmed, 5 sims      │ │ wind 18 m/s at 22:30││    │ │ 9 min 40 s       │ │
│ └────────────────┘ └────────────────────────┘ └─────────────────────┘│    │ ├──────────────────┤ │
│ ┌──────────────── 3D  [Before | After] ───────┐ ┌ What the AI changed ┐│ │ │ Start evacuating │ │
│ │                                             │ │ + East gate 4 m      ││ │ │ by 21:47         │ │
│ │                                             │ │   12:10 → 9:40  [Show]││ │ └──────────────────┘ │
│ │                                             │ │ + 2 stewards at bar  ││ │ [Download report]    │
│ └─────────────────────────────────────────────┘ │ Top risks it found   ││ │ What the AI changed ▾│
│ Cost of this plan: $0.06 · 3 min · 18 screened │ │ [risk] [risk] [risk] ││ │ Top risks ▾          │
│ [Steward cards] [Go live] [Share]   Expert view │ └──────────────────────┘│ │ 3D ▾                 │
│ ┌ Ask or change anything ───────────────────────────────────────┐│    │ [Steward cards][Live]│
│ │ e.g. "What if it rains?" · "Make the east gate wider"        ▸ ││    │ Ask or change…   ▸   │
│ └───────────────────────────────────────────────────────────────┘│    │ Planning aid, not…   │
│ Planning aid, not a safety certification                          │    └──────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

**Elements and copy**

- Header: plan name (click to rename inline), version label, "Saved".
- **Verdict banner** (colour + icon + word): "This plan holds" / "This plan is at risk" / "This plan fails", then one
  sentence (judge text, number-checked) and the primary **Download report**.
- **Three number cards:** Safe capacity · Evacuation time (95%) (range if N05 ran) · Start evacuating by (or "No
  hazard in the forecast window"). Each card has its source tag and opens "Where this number comes from".
- **3D** with a **Before | After** segmented toggle (Before = the plan before the AI's fixes under the worst attack,
  After = the fixed plan); the replay plays once automatically, then a play button.
- **What the AI changed:** one row per kept fix: icon, plain title with the exit/area name, before → after for the
  main number, **Show** (flies the camera, toggles After). If nothing changed: "The AI found no change worth making.
  Here's what it tested." Not-kept fixes are hidden behind "Also tried (not kept, 3)".
- **Top risks it found:** up to 3 compact attack cards: title, "Inspired by Itaewon 2022" (link to the source),
  result word (Breaks / Holds after fixes). "Show all" opens Expert view's Red Team tab.
- **Cost of this plan** line (N16), tap → breakdown sheet by model and by simulation kind.
- Secondary actions: **Steward cards**, **Go live**, **Share** (if N09); text link **Expert view** (desktop only).
- **Ask or change anything** box (D below).
- If the plan was edited after Autopilot: banner "You changed the plan. Results are from before the change."
  **Re-run Autopilot (Quick)**.

**States**

| State | What the user sees |
| --- | --- |
| Loading | Skeleton banner + three skeleton cards; 3D placeholder with the venue outline from the thumbnail |
| No results yet (project without a run) | "This plan hasn't been tested yet." primary **Test it with Autopilot** |
| Partial | Amber banner "Partial plan: stopped after 'Trying what could go wrong' (budget). Re-run to finish." |
| Results out of date | Banner above + Re-run button (see above) |
| Error | Card-level errors ("Couldn't load the risks. Try again"), never the whole page |
| Offline | Plan stays readable from cache; actions needing the server are disabled with "You're offline" |

**Tests:** `T-UX-C1` banner variants (holds/at risk/fails/partial/out of date) rendered from fixtures (vitest +
screenshot); `T-UX-C2` Before/After toggle switches the replayed run ids; `T-UX-C3` "What the AI changed" rows use
exit names, never ids (lint + fixture); `T-UX-C4` number card opens its source sheet; `T-UX-C5` phone layout order is
verdict → numbers → Download → changes → risks → 3D.

#### D. "Ask or change anything" box (component on Your plan and AI-at-work-finished; N15)

- One line input that grows; placeholder rotates between three examples every 6 s (static with reduced motion).
- After send, the answer appears **under the box** (not in a chat sidebar):
  - edit → "Here's the change: Added a 4 m gate on the east side." 3D shows a ghost preview; **Apply** (primary)
    and **Cancel**; after Apply → toast "Applied · Undo" and the out-of-date banner with **Re-run Autopilot**.
  - question → answer text with numbers tagged and a **Show me** that flies the camera.
  - what-if → "If it rains: evacuation time 11 min 05 s (instant estimate, +1 min 25 s)". **Keep as a scenario**
    (adds it to the plan's tested scenarios; Expert view).
  - other → "I can change the plan, answer questions about the results or try what-ifs. Try: …" with 3 chips.
- History: the last 5 exchanges in a collapsible "Earlier" list.
- **Tests:** `T-UX-D1` edit never applies without Apply; `T-UX-D2` Undo after Apply restores the previous version;
  `T-UX-D3` what-if answers always carry the "instant estimate" tag.

#### E. Go live (`/p/:projectId/live`, N07)

- Full-screen, high contrast, big type (clock ≥ 48 px), works in sunlight and on a phone; screen kept awake via the
  Wake Lock API when available (feature-detect, no error if missing).
- Top: venue local time · **Start evacuating by 21:47** (or "No hazard in the forecast window") · wind status pill.
- Middle: "People inside now" with one number field per zone (or one total with "split by plan"), big +/− steppers
  (±50, ±500); **Update** recomputes "If you evacuate now: about 6 min 30 s (instant estimate)".
- Exit list with big toggles "Open / Blocked"; blocking updates the estimate instantly.
- Alerts appear as full-width bars with a sound off by default (toggle).
- Log button: "Add note" (free text) and the automatic log; **Export log**.
- **Tests:** `T-UX-E1` steppers and fields work with keyboard and touch; `T-UX-E2` no layout shift when alerts appear
  (CLS check in Playwright); `T-UX-E3` wake-lock absent → no error.

#### F. Steward cards (`/p/:projectId/stewards`, N08)

- Language selector (English / বাংলা), **Print** (primary), **Download PDF via print**.
- Preview grid of cards; each card: post name, mini map with "You are here" and arrows, 3 instructions, "If <exit>
  is blocked, send people to <exit>", radio call sign. Print CSS: one card per A6, crop marks optional.
- **Tests:** `T-UX-F1` print stylesheet puts each card on its own page (Playwright PDF page count = cards);
  `T-UX-F2` Bangla font renders (no tofu boxes: check the font loads; self-host a Bangla-capable open font such as
  Noto Sans Bengali **[VERIFY licence: SIL OFL]**).

#### G. Report (`/p/:projectId/report`)

- Same report as today, opened in a clean print view with **Download PDF** (browser print) as primary,
  **Evacuation map (SVG)**, **Data (JSON)**, **Project file (.showtime.zip)** as secondary links.
- First page summary mirrors Your plan (verdict, three numbers, what changed, top risks, cost line, disclaimer).

#### H. Expert view (`/p/:projectId/expert`)

- Today's Workspace, unchanged in function. Small cleanups only (N14): "View" menu (Showtime lights, tour, layers),
  cost meter inside the provider badge popover, Estimates + What-if grouped under "Plan for the day".
- A persistent link "Back to your plan" top-left.

#### I. Settings (`/settings`)

- **Simple section first:** language, units (metric/imperial), theme, "Show expert view by default" switch.
- **Advanced** (collapsed, labelled "For technical users"): providers, model routing (N01), budgets, simulation
  defaults, plugins. On the public demo the advanced section is read-only with the demo hint.

#### J. Help (`/help`)

- **Task-first:** "How do I… plan an event · read my plan · change the plan · prepare for the day · share with the
  permit office", each 3–5 steps with a small screenshot.
- Then glossary, then "How the numbers are computed" (existing), then "How good is the simulator?" (N10), then
  keyboard shortcuts.

#### K. First-time guidance

- No forced onboarding wizard. The 90-second tour is offered, never auto-started on Home.
- At most **three coach marks** in the whole app, each shown once (stored in localStorage with try/catch): on Your
  plan → the verdict ("Start here"), the three numbers ("Tap any number to see where it comes from"), the Ask box
  ("Ask or change anything"). Dismiss with one tap; never block interaction.
- Existing `Onboarding.tsx` first-run checklist (model, Docker, keys) moves under Settings › Advanced for local
  installs; the public demo never shows it.

### 5A.5 Components to build or reuse

| Component | New/reuse | File |
| --- | --- | --- |
| `VerdictBanner` | new (reuses ScoreGauge colours) | `web/src/components/VerdictBanner.tsx` |
| `NumberCard` (value, unit, source tag, range, "where from") | new | `web/src/components/NumberCard.tsx` |
| `StepList` (Autopilot steps, aria-live) | new | `web/src/components/StepList.tsx` |
| `ChangeRow`, `RiskCard` (compact) | new, logic from RedTeamPanel | `web/src/components/ChangeRow.tsx`, `RiskCard.tsx` |
| `CostLine` + breakdown sheet | new | `web/src/components/CostLine.tsx` |
| `AskAnything` | new (N15) | `web/src/panels/AskAnything.tsx` |
| `BriefHints` chips + `briefHints.ts` parser | new | `web/src/components/BriefHints.tsx`, `web/src/lib/briefHints.ts` |
| `StateView` (loading/empty/error/partial/offline) | extend existing `components/ui/states.tsx` | same file |
| `BeforeAfterToggle` | new, wraps `SceneRoot` run switching | `web/src/scene/BeforeAfterToggle.tsx` |
| Coach marks | new, tiny (Radix Popover) | `web/src/components/CoachMark.tsx` |
| 3D, replay, report, tour | reuse | `web/src/scene/*`, `web/src/replay/*`, `panels/ReportView.tsx`, `panels/Tour.tsx` |

Rules: Radix primitives for anything interactive; no new UI library; strings only via `t()`; every component has a
vitest test for its states.

### 5A.6 Error message catalogue

Backend errors already arrive as `{code, message, hint, details}` (`api/app/errors.py`). The UI shows `message` as
the title and `hint` as the next step, plus one button. Add or review these codes (new ones marked *):

| Code | When | Message (title) | Hint and button |
| --- | --- | --- | --- |
| `network` (client) | server unreachable | "We can't reach the Showtime server." | Local: "Start it with `make up`." Demo: "Try again in a minute." · **Try again** |
| `rate_limited`* | N06 limits | "You've reached this hour's limit." | "Try again at 14:20, or open a sample." · **Open a sample** |
| `demo_read_only`* | settings on demo | "Settings are fixed on the public demo." | "Run Showtime on your computer to change them." · **How to install** |
| `sample_read_only`* | edit a sample on demo | "Samples can't be changed." | "Make your own copy to edit it." · **Make my copy** |
| `budget_used`* | daily AI cap | "Today's live AI budget is used up." | "Watch a recorded plan, or come back tomorrow." · **Watch a recorded plan** |
| `place_not_found`* | brief place unknown to OSM | "We couldn't find 'Ramna Prak' on the map." | "Check the spelling, or describe the venue instead." · **Describe the venue** |
| `area_too_large` | OSM area over limit (exists) | keep current message | **Draw a smaller area** |
| `geometry_invalid` | patch breaks the venue (exists) | keep current message | **Undo** |
| `model_unavailable`* | AI provider down and no fallback | "The AI is unavailable right now." | "Your plan uses simpler built-in rules until it's back." · **Continue** |
| `sim_failed` | sandbox failure (exists in fallbacks) | "One simulation didn't finish." | "We used an instant estimate for it." · **Show details** |

**Tests:** `T-UX-3` for every code above, a Playwright test intercepts the API to return it and asserts the title,
the hint and that the button works (no dead end). `T-UX-4` client `network` copy differs between demo and local
builds (`DEMO_MODE` exposed in `/features`).

### 5A.7 Usability test protocol (run twice: M13 end on localhost, M18 on the deployed demo)

- **Participants:** 5 people who have not seen the app (classmates outside the project; ideally one person who has
  organised an event or works in campus facilities). 5 testers find most usability problems; do not wait for more.
- **Setup:** laptop + one phone; screen and voice recorded with consent; think-aloud; the facilitator does not help
  except to unblock after 60 s of being stuck (count it as a failure).
- **Tasks:**
  1. "You're organising a concert for 6,000 people at Ramna Park on 16 December at 6 pm. Get a safety plan and
     download it."
  2. "What did the AI change in your plan, and why?"
  3. "What happens if it rains?"
  4. "Make the east gate wider and check the plan again."
  5. "It's the event night. 4,500 people are inside and the north gate is blocked. When should you start evacuating?"
     (Go live)
- **Measure:** success yes/no, time, number of clicks, hesitation points (> 5 s without action), wrong turns, quotes.
  After the tasks: SUS questionnaire (10 standard questions) and "What was the most confusing thing?".
- **Record:** `docs/usability/<date>.md` with a table per task and the top 5 problems ranked by severity
  (blocker / major / minor) and the fix for each. Fix all blockers and majors before the next milestone gate.
- **Pass:** the targets in 5A.1.

### 5A.8 Automated UI test suite (added to `web/e2e/`)

| File | What it covers |
| --- | --- |
| `simple-flow.spec.ts` | `T-N14-1`, `T-UX-A*`, `T-UX-B*`, `T-UX-C*`, `T-UX-D*` with the API mocked by Playwright route interception for determinism, plus one unmocked run against the real app with fake providers |
| `states.spec.ts` | every row of every state table in 5A.4 via route interception (loading delayed, empty lists, 500s, offline via `context.setOffline(true)`) |
| `errors.spec.ts` | `T-UX-3`, `T-UX-4` |
| `phone.spec.ts` | 390 × 844 project: no horizontal scroll (`document.scrollingElement.scrollWidth <= innerWidth`), primary buttons in viewport, touch targets ≥ 44 px (`T-UX-5`: bounding boxes of every button/link on simple screens) |
| `a11y.spec.ts` | axe on every route in 5A.3 in light and dark |
| `copy.spec.ts` + `scripts/lint_copy.mjs` | forbidden words (`T-N14-7`), sentence length and readability score on simple-flow keys (`T-UX-6`), every `t()` key exists (`T-F24-3`) |
| `visual.spec.ts` | screenshots of every screen and state (light, dark, phone) compared with `toHaveScreenshot` baselines committed under `web/e2e/__screenshots__/` (update only intentionally) |
| console guard | a shared fixture fails any test that logs a console error or an unhandled rejection |

`make e2e` runs all of them; `make a11y` runs only `a11y.spec.ts`.

### 5A.9 UI definition of done (every screen, every PR)

- [ ] One primary action; matches the wireframe and copy in 5A.4 (or the change is recorded here).
- [ ] Loading, empty, error, partial and offline states designed and tested.
- [ ] No forbidden words; every number has unit + source tag; glossary terms linked.
- [ ] Keyboard path works; focus visible; screen-reader names; `aria-live` where content updates.
- [ ] Phone 390 × 844 checked (for simple screens); dark mode checked.
- [ ] Strings in `en.json`; no hard-coded text.
- [ ] axe clean; console clean; visual baseline updated on purpose.
- [ ] Disclaimer present where results are shown.

---

## 6. The test system

### 6.1 Layers

| Layer | Tool | Where | Runs in CI | Command |
| --- | --- | --- | --- | --- |
| Unit + integration (fake LLM, fake sandbox, fake Tavily) | pytest | `api/tests/` | yes | `make check` (fast), `make test` (all) |
| Plugin conformance | pytest suites | `api/tests/conformance/` | yes | part of `make test` |
| Simulation | pytest in sim image | `sim/tests/` | optional job | `make test-sim` |
| Frontend unit/component | vitest | `web/src/**/*.test.ts(x)` | yes | `make test-web` |
| End-to-end journeys | Playwright | `web/e2e/journeys.spec.ts` (+ new files) | no (needs app) | `make e2e` |
| Accessibility | `@axe-core/playwright` **(new dev dep)** | `web/e2e/a11y.spec.ts` | no | `make a11y` (new) |
| Agent evals (quality, live or replay) | Python scripts | `scripts/eval_agents.py` (new, wraps `eval_venue_agent.py`) | replay only | `make eval` (new) |
| Live provider tests | pytest markers `nebius`, `tavily`, `live` | `api/tests/test_live_*.py` | no | `make test-live` (new) |
| Smoke | Python | `scripts/smoke.py`, `smoke_nebius.py`, `smoke_public.py` (new) | no | `make smoke`, `make smoke-nebius`, `make smoke-public URL=…` |
| Load | Python (httpx + asyncio) | `scripts/load_public.py` (new) | no | `make load URL=…` |
| Security | pytest + scripts | `api/tests/test_demo_mode.py` (new), secret scan | yes (unit part) | in `make test` |
| Visual review | Playwright screenshots + `toHaveScreenshot` baselines | `web/e2e/screens.mjs`, `web/e2e/visual.spec.ts` | no | `make screenshots`, `make e2e` |
| UI states, errors, phone, copy | Playwright with route interception | `web/e2e/{simple-flow,states,errors,phone,copy}.spec.ts` (5A.8) | no | `make e2e` |
| Usability (humans) | 5 testers, 5 tasks, SUS | `docs/usability/<date>.md` (5A.7) | no | manual, M13 and M18 |
| Claims check | Python | `scripts/check_claims.py` (new) | yes | in `make lint` |

### 6.2 Test infrastructure to build

#### 6.2.1 Fakes and fixtures

- **Fake Tavily client** (`api/tests/fakes/tavily.py`): deterministic hits per query, counts calls, can raise.
- **Instrumented fake runner** that records start/end timestamps to assert concurrency bounds (N04, N05).
- **Frozen weather snapshot** (exists in the Wellington pack) reused for Live Ops tests.
- **DXF fixture** generated by a tiny `ezdxf` script at test time (no binary in git).
- LLM fixtures: replay cache under `api/tests/fixtures/llm_cache/` (exists); add Nebius-recorded fixtures in M12.

#### 6.2.2 New Make targets (add to `Makefile` with `## help` comments)

```
eval        ## Agent quality evals on the configured provider; writes docs/evals/<date>-<provider>.{json,md}
test-live   ## Live tests (Nebius, Tavily); skip cleanly without keys
a11y        ## Axe accessibility scan of every screen (app must be running)
smoke-public## Smoke test against a deployed URL: make smoke-public URL=https://…
load        ## Load test against a deployed URL: make load URL=https://…
```

#### 6.2.3 Live test files

- `api/tests/test_live_nebius.py` (`@pytest.mark.nebius`): T-N01-4, T-N04-3, T-N04-4.
- `api/tests/test_live_tavily.py` (`@pytest.mark.tavily`): T-N02-8, T-N03-7.
- Each skips with a clear reason when its key is missing. Never run in CI.

#### 6.2.4 Agent eval suite (`make eval`) and thresholds

| Agent | Eval set | Pass threshold (Nebius) | Local 9B threshold |
| --- | --- | --- | --- |
| Venue (edits) | 12 scripted requests (existing) | ≥ 11/12 valid patches | ≥ 11/12 |
| Event brief | 10 sentences with expected fields | ≥ 9/10 all fields correct | ≥ 8/10 |
| Venue designer | 5 descriptions | 5/5 valid venues after ≤ 1 repair | ≥ 4/5 |
| Red team | 3 sample venues × 1 round | 100 % cards cited (enforced); ≥ 80 % attacks valid without rule fallback; ≥ 1 live Tavily citation per venue when key set | ≥ 60 % valid |
| Blue team | worst attack on each sample | ≥ 1 accepted fix per venue | ≥ 2/3 venues |
| Judge / safety officer / explainer | 5 cases each | number check passes first try ≥ 80 %; final 100 % (after regen or template) | same final 100 % |
| Web brief (N02) | 3 events | 100 % items cite a hit (enforced); ≥ 3 items per event when live | n/a |
| Rules research (N03) | Dhaka, Wellington, London | 0 unverified shown (enforced); ≥ 1 verified per city or honest empty | n/a |
| Steward translation (N08) | 10 cards → Bangla | 10/10 placeholder-valid after ≤ 1 retry | n/a |
| Intent router (N15) | 20 utterances | ≥ 18/20 | ≥ 16/20 |
| Autopilot quick (N13) | Ramna Park + 3 samples | 4/4 finish; cost and wall time recorded (N16) | 4/4 finish |
| Latency | Copilot end-to-end (no sim wait) | ≤ 60 s p50 over 3 runs | ≤ 90 s |

Output: `docs/evals/<YYYY-MM-DD>-<provider>.json` and `.md` (table), plus `docs/evals/latest.json` (used by the
claims check). README numbers ("12/12 edits") must be copied from these files, not typed by hand.

### 6.3 Gates

| Gate | When | Must pass |
| --- | --- | --- |
| **G-change** | after every code change | `make check` |
| **G-feature** | after each feature | that feature's T-ids + `make test` + `make test-web` |
| **G-milestone** | end of each milestone | G-feature + `make smoke` + `make e2e` + PROGRESS entry + commit |
| **G-live** | end of M12, M13, M14, M17 | `make test-live`, `make smoke-nebius`, `make eval` thresholds |
| **G-deploy** | end of M17 and after every redeploy | `make smoke-public`, `make load`, T-N06-* green, manual phone check |
| **G-release** | M20 | everything above + fresh-clone verification + section 11 checklist |

### 6.4 Manual "judge simulation" (run in M18 and again in M20, by the agent with Playwright and by the human)

1. Logged-out, fresh incognito window, desktop 1280 px and a phone: open the public URL. Within 10 s the landing shows.
2. Start the 90-second tour; it reaches the report without errors.
3. Autopilot (Quick) with the Ramna Park example: AI at work → Your plan (live or labelled replay); the cost card shows a number.
4. Open the T-alley sample: red team cards cite sources; branch tree clickable; compare works.
5. Make my copy → in "Ask or change anything" type "add a 3 m exit on the east wall" → Apply → Re-run Autopilot → evacuation time changes.
6. Report → PDF print preview shows disclaimer, sources, steward pack link.
7. GitHub repo page (logged out): licence visible at top, README shows demo + video links.
8. YouTube video plays logged out, ≤ 3:00.

### 6.5 Test-writing rules

- Every bug found gets a regression test before the fix (name it after the behaviour, not the bug id).
- No test calls the network unless marked `live`, `nebius` or `tavily`.
- Tests must be deterministic: fixed seeds, frozen time (`freezegun` is not installed; pass `now` explicitly to
  functions that need it instead of adding a dependency).
- Keep `/tmp` free (it is RAM here): pytest basetemp is already `../cache/pytest`.

---

## 7. Milestones and schedule (Oct 9 – Oct 30)

Feature freeze: **end of Oct 24**. After that only fixes, polish, docs, video. Milestones overlap by a day on
purpose: start the next one's backend while the previous one's UI is being finished, but never mark a milestone
done before its gate is green.

### M11 — Baseline and compliance (Fri Oct 9 – Sat Oct 10)

- Ask the human for H1–H4 (section 3) today.
- Re-run all gates on the current code to confirm the recorded state (`make check`, `make test`, `make test-web`,
  `make e2e`, `make smoke`); record actual numbers.
- N12 steps 1, 2, 4, 6 (root LICENSE, CI workflow, TESTING_GUIDE path, markers).
- Backend tests to add from section 4: T-F01-1..3, T-F03-1..4, T-F04-1..2, T-F06-1..3, T-F11-1..2, T-F13-1..3,
  T-F14-1..3, T-F17-1..2, T-F18-1..3, T-F19-1..3, T-F21-1..2, T-F23-1..3, T-F24-1..2, T-F25-1.
- Fakes from 6.2.1; new Make targets as stubs that print "not yet" where the feature does not exist.
- **Done when:** all new tests green; CI file present; LICENSE at root; PROGRESS entry.

### M12 — Nemotron live + cost metering (Sat Oct 10 – Mon Oct 12)

- N01 complete (probe, routing, per-role extra body, fallback none, model routing panel, Nebius fixtures).
- N16 backend: cost record, funnel fields, escalation policy, `scripts/measure_cost.py` skeleton.
- Migration 0002 (all tables, section 5) with T-M2-1.
- `scripts/eval_agents.py` + `make eval`; run on local and Nebius. Start `docs/feedback-log.md`.
- **Done when:** G-live (LLM part) green; one full Red Team Night on Nebius recorded with a cost record.

### M13 — Autopilot and the simple UI: the story (Mon Oct 12 – Fri Oct 16)

- N13 Autopilot (graph nodes, presets, routes, SSE, persistence).
- N14 three screens + Expert view cleanup, built to section 5A (wireframes, copy, states, error catalogue,
  components); N11 tour row on Home; N16 cost card and funnel in the UI.
- First usability test (5A.7) on localhost with 5 testers at the end of the milestone; fix blockers and majors.
- Rewrite `docs/TESTING_GUIDE.md` and `docs/USER_GUIDE.md` to start with the simple flow.
- **Done when:** T-N13-*, T-N14-*, T-N16-*, T-UX-* green; usability report in `docs/usability/`; quick Autopilot on Ramna Park works end to end on Nebius and the
  user lands on *Your plan*; first cost measurement recorded in `docs/evals/`.

### M14 — Tavily evidence, local rules, one box (Thu Oct 15 – Sun Oct 18)

- N02 Evidence Desk (also wired into Autopilot thorough depth and the attack cards on *Your plan*).
- N03 rules research; N15 "Ask or change anything".
- **Done when:** G-live (Tavily) green; a live Autopilot run shows a live Tavily citation on *Your plan*; router eval
  ≥ 18/20 on Nebius.

### M15 — Sandboxes, seed ranges, early deploy (Sat Oct 17 – Tue Oct 20)

- N04 (if access) or documented fallback; N05 ranges (used by thorough Autopilot).
- **Early deploy (D0):** current app on the Nebius VM (section 8) behind basic auth to find hosting problems early
  (SSE through the proxy, file sizes, Docker on the VM, memory).
- **Done when:** ranges work locally and on the VM; Sandboxes live result or fallback documented; D0 reachable.

### M16 — Operate and hand over, validation (Mon Oct 19 – Thu Oct 22)

- N07 Live Ops (Go live from *Your plan*); N08 steward pack (English + Bangla); N10 validation chart.
- N09 share link only if the three above are done by Oct 21.
- **Done when:** their tests green; Bangla cards checked by a speaker (or marked unchecked); validation error published.

### M17 — Public demo hardening and deployment (Wed Oct 21 – Sat Oct 24) · feature freeze at the end

- N06 complete (demo mode, isolation, limits, per-plan and daily caps, cleanup, deployment files).
- Re-record the three sample packs and the recorded Autopilot replay on Nebius models (F20, N11).
- Deploy with `DEMO_MODE=true`, HTTPS, no basic auth.
- **Done when:** G-deploy green; demo URL works from a phone on mobile data.

### M18 — Polish and judge experience (Sat Oct 24 – Mon Oct 26)

- Frontend tests T-F07-1..3, T-F15-1..2, T-F24-3; `make a11y` clean; performance budgets on the deployed URL
  (first load < 3 s on desktop broadband).
- `make screenshots`, self-review against the N14 principles and CLAUDE.md 1A/4A, fix findings, update README
  screenshots. Second usability test (5A.7) on the deployed demo; 5A.1 targets met (SUS ≥ 80, ≥ 90 % task 1
  success). Go live, Steward cards, Settings and Help screens checked against 5A.4 E–J. N17 only if everything else
  is green.
- Manual judge simulation (6.4).
- **Done when:** all of the above green; PROGRESS review entry.

### M19 — Story: video, Devpost, feedback (Mon Oct 26 – Wed Oct 28)

- Video (section 9.3) recorded from the **deployed** app, voice-over (H7), ≤ 3:00, uploaded (public).
- Devpost text (section 9.4), track Best Apps and Agents, city (H9).
- FEEDBACK.md final (section 9.2); README final; HANDOFF and CHANGELOG updated; tag `v0.2.0`.
- **Done when:** video link and demo link in both READMEs; claims check green.

### M20 — Release verification and submit (Wed Oct 28 – Thu Oct 29)

- Fresh-clone verification (CLAUDE.md M10 procedure) of the public repo: `make setup && make check && make test`.
- G-release; section 11 checklist ticked; human submits on Devpost by Oct 29 18:00 GMT+6 (H8, H10).
- Oct 30: reserve for emergencies only; do not change the deployed app after submission unless it is broken.

### Calendar view

| Week | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Oct 5–11 | | | | | 9 M11 | 10 M11/M12 | 11 M12 |
| Oct 12–18 | 12 M12/M13 | 13 M13 | 14 M13 | 15 M13/M14 | 16 M13/M14 | 17 M14/M15 | 18 M14/M15 |
| Oct 19–25 | 19 M15/M16 | 20 M15/M16 | 21 M16/M17 | 22 M16/M17 | 23 M17 | 24 M17 freeze/M18 | 25 M18 |
| Oct 26–31 | 26 M18/M19 | 27 M19 | 28 M19/M20 | 29 **submit** | 30 reserve (deadline 23:00 GMT+6) | | |

---

## 8. Deployment on Nebius (public demo)

**Target architecture**

```
Browser ──HTTPS──> Caddy (TLS, gzip, SSE pass-through) on a Nebius AI Cloud CPU VM
                    ├── web (nginx static build, existing web/Dockerfile)
                    └── api (existing api/Dockerfile, DEMO_MODE=true)
                          ├── LLM: Nebius Token Factory (Nemotron Nano/Super/Ultra)
                          ├── Sandboxes: Nebius Sandboxes (contree-sdk)  ── or fallback: Docker on the VM
                          ├── Tavily, Open-Meteo, OSM (cached)
                          └── SQLite on a persistent disk (state/, runs/, cache/)
```

**Procedure (write it into `deploy/README.md` as you do it):**

1. Create a VM (Ubuntu LTS, 8 vCPU / 32 GB, 100 GB disk) in Nebius AI Cloud **[VERIFY console steps; record them
   for FEEDBACK]**; open ports 80/443 only; SSH by key.
2. Install Docker Engine + compose plugin. Clone the repo. Build the sim image if the Docker fallback is used.
3. `deploy/.env.public` from `deploy/.env.public.example` (keys entered on the server only, `chmod 600`).
4. `docker compose -f deploy/docker-compose.public.yml up -d --build`. Compose differences from the local file:
   Caddy service; API `mem_limit` raised (e.g. 4 GB); `API_HOST=0.0.0.0` inside the network only; `WEB_ORIGIN` =
   the public origin; no host port for the API; Docker socket only in the `docker-sandbox` profile.
5. Caddy: automatic HTTPS for the domain (H6); `flush_interval -1` (or equivalent) for the SSE route so events stream.
6. Seed samples (they install on first start). Run `make smoke-public URL=…` and `make load URL=…` from the laptop.
7. Backups: nightly copy of `state/showtime.sqlite` (use SQLite `.backup`, not a file copy, because of WAL).
8. Monitoring: `/api/v1/health` checked every 5 min by a cron on the VM writing to a log; daily cost report from
   `usage_day`.

**Nebius Serverless Endpoints / Jobs** (encouraged, not required): only consider after M17 is green. Candidate use:
run ensemble seeds (N05) as Serverless Jobs **[VERIFY API, image requirements, pricing]**. Do not start this if it
risks the freeze.

---

## 9. Submission package: README, feedback, video, Devpost text

### 9.1 README (both root and `nebius/README.md`)

Order: the problem in two sentences (planning and simulation are slow, expensive, specialist) → our answer (AI
automates it with existing simulators, cost-efficiently) → demo URL + video link → screenshot of the three screens →
how it works (Autopilot steps) → **cost of a plan** (measured, from `docs/evals/cost-*.json`) → **How we use NVIDIA and
Nebius** (role routing table, Token Factory, Sandboxes or AI Cloud VM, Tavily, live-verified status) → the existing
simulation software we build on → quickstart (local and "try the demo") → validation chart → limits ("planning aid")
→ docs → licence.

### 9.2 FEEDBACK.md (required; prize for the most valuable)

For **each** of: Nebius Token Factory, Nebius AI Cloud (VM), Nebius Sandboxes, NVIDIA Nemotron (Nano 9B v2 local,
Nemotron 3 Nano/Super/Ultra hosted), Tavily — answer these headings exactly (from the Devpost update "How to build a
winning project"):

1. What we used it for (one paragraph, concrete).
2. What worked well (specific, with numbers: latency, accuracy on our evals, time saved).
3. What needs work (specific: tool, page or endpoint, the exact error text, what we expected, what happened, the
   workaround).
4. Onboarding: zero to hello world (minutes, steps, where we got stuck).
5. Would we build with it again, and why.
Keep a running log in `docs/feedback-log.md` during M12–M17 (timestamped), and condense it at M19.

### 9.3 Video script (≤ 3:00; record from the deployed app; name Nebius and NVIDIA out loud)

| Time | Shot | Voice-over (essence) |
| --- | --- | --- |
| 0:00–0:15 | Itaewon alley dimensions and Indiana stage photo (cite) | "159 people died in a 3.2 m alley. A stage fell in a 59 mph gust. Neither event was stress-tested, because crowd simulation takes experts, weeks and money." |
| 0:15–0:30 | Home: one box; type the Ramna Park sentence; press Plan it | "Showtime lets AI do that work. One sentence." |
| 0:30–1:15 | AI at work: steps tick by; 3D park appears; crowd replay; attack cards with sources (dataset and live Tavily); fixes; footer "Nemotron on Nebius · 18 scenarios screened instantly · 5 simulated" | "Nemotron on Nebius Token Factory builds the real park, then drives proven simulation software, JuPedSim from Jülich, to test what could go wrong. Nano drafts, Super fixes, Ultra judges. Instant estimates screen every scenario so only the dangerous ones get a full simulation, each in its own Nebius sandbox." |
| 1:15–1:45 | Your plan: verdict, three numbers, "What the AI changed" with before/after in 3D | "Every fix is re-simulated; only measured improvements are kept." |
| 1:45–2:00 | Cost card with the measured number; validation chart | "This plan cost <measured> in AI and <measured> minutes. And the simulator is checked against real experiments." |
| 2:00–2:20 | "What if it rains?" in the one box; Go live console with the countdown; Bangla steward cards | "Ask anything. On the night: the latest safe time to start evacuating, live headcounts, steward cards in Bangla." |
| 2:20–2:45 | Report download; architecture slide (Nemotron roles, Token Factory, Sandboxes/AI Cloud, Tavily, JuPedSim/PedPy/Pynite) | "Built on NVIDIA Nemotron, Nebius Token Factory and Nebius AI Cloud, with Tavily for live evidence." |
| 2:45–3:00 | Tagline + "Planning aid, not a safety certification." | "Run the disaster before the gates open." |

### 9.4 Devpost text outline

Inspiration (the two disasters; planning and simulation are slow, expensive and specialist, so most events skip it) ·
What it does (Autopilot: describe → AI builds, simulates, breaks, fixes → your plan; Live Ops; steward pack) · How we
built it (Nemotron role routing on Token Factory, LangGraph Autopilot, existing simulators as tools: JuPedSim, PedPy,
Pynite, Open-Meteo, OSM; Sandboxes; Tavily; honesty rules; cost tactics) · Cost (measured per plan) · Challenges (from
PROGRESS: doorway artefacts, 9B schema ordering 6/10 → 10/10, memory, WAL across Docker Desktop, simplifying the UI) ·
Accomplishments (validation result, evals, cost) · What we learned · What's next · Built with (tags) · "Built during
the submission period, started 2026-10-08" · Links: demo, video, repo, feedback.

---

## 10. Risks, fallbacks and the cut order

### 10.1 Top risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Sandboxes access not granted | medium | medium | Docker runner on the Nebius AI Cloud VM (still "runs on Nebius AI Cloud"); honest wording |
| Token Factory model lacks `json_schema` | medium | low | prompted JSON + repair path; evals decide |
| Nemotron 3 reasoning eats the reply budget | medium | medium | per-role extra body to disable reasoning; total deadline exists |
| Public demo abused / cost spike | medium | high | N06 limits, daily cap, replay fallback |
| Free-tier Tavily credits run out | medium | medium | disk cache, per-session cap, record demo searches into the sample packs |
| OSM/Nominatim rate limits on the public demo | high | medium | cache, 1 req/s, prefer samples and cached places on the landing |
| SSE broken behind the proxy | medium | high | D0 early deploy in M14 tests it |
| Validation misses the 15 % target | medium | low | publish the real error with explanation; never tune silently |
| Simple UI rewrite takes longer than planned | medium | high | build the three screens on existing components and queries; Expert view is today's workspace unchanged; no new design system |
| Autopilot too slow for a judge's patience on the public demo | medium | high | Quick depth by default; live progress with 3D from the first minute; recorded replay when the queue is long |
| Running out of time | medium | high | cut order below; feature freeze Oct 24 |

### 10.2 Fallbacks (extend CLAUDE.md section 18)

| Problem | Fallback |
| --- | --- |
| No Token Factory key by Oct 13 | Keep building with OpenRouter Nemotron 3 (`LLM_PROVIDER=openai`) for development only; escalate to the human daily; the submission must run on Nebius |
| Tavily `research`/`crawl` behaves differently than expected | use only `search` + `extract` (enough for N02/N03) |
| Bangla translation quality poor | ship English pack; Bangla marked "beta" or removed from the video |
| Deployment VM unavailable | deploy on any VM for testing, but the submitted URL must be on Nebius AI Cloud; escalate |
| Load test fails | lower `DEMO_MAX_CONCURRENT_SESSIONS`, cache more aggressively, serve samples only for heavy routes |

### 10.3 Cut order (cut from the top when a milestone slips more than one day)

1. N17 Open formats
2. N09 Share link
3. Nebius Serverless Jobs experiment
4. Expert view cleanup (keep today's workspace as is)
5. N05 in Autopilot thorough (keep the Expert view button)
6. N07 "Brief me" LLM button (keep the rest of Live Ops)
7. N08 Bangla (keep the English steward pack)
8. N10 Indiana note (keep the bottleneck chart)
9. N15 (keep the existing command bar and Ask the venue in Expert view)
10. N03 (keep N02)

Never cut: N01, N02, N06, N11, N12, **N13, N14 (with 5A.2 global rules and screens A–C), N16**, the usability test,
the video, FEEDBACK.

---

## 11. Final pre-submission checklist

**Compliance**

- [ ] Demo URL works logged out on desktop and phone; HTTPS; samples load; Autopilot (Quick) runs live or with a labelled replay and ends on *Your plan* with a cost card.
- [ ] App uses Nemotron on Nebius Token Factory at runtime (provider badge `NEBIUS`; activity feed shows Nano/Super/Ultra).
- [ ] Public GitHub repo; Apache-2.0 visible at the top; README with setup, demo URL, video link, Nebius/NVIDIA usage, feedback link.
- [ ] Video ≤ 3:00, public on YouTube, names Nebius Token Factory and NVIDIA Nemotron out loud, shows the app working.
- [ ] FEEDBACK.md covers Token Factory, AI Cloud, Sandboxes, Nemotron (local + hosted), Tavily with the five headings.
- [ ] Devpost: track = Best Apps and Agents; description; "built during the submission period" statement; city if any.

**Quality**

- [ ] G-release green: `make check`, `make test`, `make test-web`, `make e2e`, `make a11y`, `make smoke`, `make smoke-nebius`, `make test-live`, `make eval`, `make smoke-public`, `make load`.
- [ ] Fresh clone of the public repo builds and passes `make check && make test`.
- [ ] Claims check green: every statement in READMEs and Devpost matches `docs/evals/latest.json`, NEBIUS_SWITCH status and HANDOFF.
- [ ] No secrets in git history (`git log -p | grep -E "sk-|tvly-|NEBIUS_API_KEY=."` returns nothing) and none in the web bundle.
- [ ] Ease of use: 5A.1 targets met in the last usability test (report in `docs/usability/`); 5A.9 ticked for every screen.
- [ ] "Planning aid, not a safety certification" on results screens, report, steward pack, share page, landing footer.
- [ ] HANDOFF, PROGRESS, CHANGELOG, ASSUMPTIONS, LICENSES, NEBIUS_SWITCH updated; tag `v0.2.0`.

---

## 12. Double-check log (what was verified while writing this plan)

Checked on 2026-10-09 in this repository:

| Claim in this plan | How it was checked |
| --- | --- |
| Repo root has only `README.md`, `requirements.txt`, `nebius/` (plus this plan); no root LICENSE | `ls -la` at the root; `git ls-files` |
| No CI workflow; CHANGELOG line 69 claims one | `git ls-files` (no `.github/`); `grep -n workflow CHANGELOG.md` |
| Tavily adapter only used for health | `grep -rn "st.search" api` → `routes_core.py` lines 30, 103 only; `TavilySearch` built in `api/app/state.py` |
| tavily-python 0.8.5 has `search`, `extract`, `crawl`, `map`, `research` | `grep "def " api/.venv/.../tavily/tavily.py` |
| contree-sdk 0.3.6, langgraph 1.2.12, openai 3.26.0 installed | `ls api/.venv/lib/python3.12/site-packages` |
| Agent roles: fast (red team), main (brief, designer, venue, blue, explainer), judge (judge, safety officer); `long` unused | `grep role= api/agents` |
| `LLM_FALLBACK` defaults to `local` | `api/core/settings.py:72` |
| One Alembic migration (`0001_initial_schema.py`) | `git ls-files api/db/migrations` |
| UI modes are `plan | simulate | redteam | report` | `web/src/state/ui.ts:6` |
| Import-linter contracts (core never imports plugins; plugins only use `api.core.extensions` and `api.models`; layers app → orchestrator → agents → core) | `.importlinter` |
| Existing tests: 96 test functions in `api/tests`, 9 in `sim/tests`, 10 vitest cases, 3 Playwright journeys; 65 API routes; 22 panel files | `grep -c "def test_"`, `grep "it(\|test("`, `grep -c @router.`, `ls web/src/panels` |
| Pytest markers `slow` and `nebius` exist; `tavily`/`live` do not | `api/pyproject.toml` |
| Stale path in TESTING_GUIDE | `docs/TESTING_GUIDE.md` line 8 |
| UI complexity (G12): 4 workspace modes, 22 panel files, ~4,000 lines in pages/panels/app; Home shows Copilot, samples, templates, projects | `wc -l web/src/pages/*.tsx web/src/panels/*.tsx web/src/app/*.tsx`, `web/src/state/ui.ts`, TESTING_GUIDE |
| Copilot is a LangGraph graph whose structure is served at `/copilot/graph` (so Autopilot can extend it) | `api/app/routes_places.py` lines 129, 148; `api/orchestrator/copilot_graph.py` |
| Current client error copy says "Start it with: make up", wrong for a public demo | `web/src/i18n/en.json` → `errors.network` |
| Existing UI stack: Radix primitives, lucide-react, sonner toasts, react-router 7, design tokens in `styles.css` | `web/package.json`, `web/src/styles.css` |
| API errors are `{code, message, hint, details}` via `ApiException` | `api/app/errors.py` |
| Content-addressed run cache exists | `api/tests/test_persistence.py::test_run_is_idempotent_and_cached` |
| Deadline 2026-10-30 23:00 GMT+6; requirements, prizes, criteria | Devpost text pasted by the human on 2026-10-09 |
| 2026-10-09 is a Friday; 2026-10-29 a Thursday | computed from 2026-01-01 = Thursday |

**Not verified (marked [VERIFY] in the text):** Token Factory model ids, prices, `json_schema` support and reasoning
switch for Nemotron 3; Sandboxes behaviour against the live service; Tavily parameter names for news/recency;
Nebius AI Cloud VM console steps and Serverless APIs; validation dataset URLs, formats and licences; `segno` licence.
