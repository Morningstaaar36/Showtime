# Showtime — Handoff

## Start it
1. `cp .env.example .env` (keys optional locally; the file already exists on this machine).
2. `make setup` — first time only: Python env, web deps, sim image, llama.cpp binary, Nemotron
   GGUF and the incident data, all inside this folder (`.tools/`, `models/`, `data/`).
3. `make llm-up` — Nemotron Nano 9B v2 on the GPU (≈ 20 s; logs in `logs/llm.log`).
4. `make up` → open http://localhost:5173 (Docker Compose: API + static web).
   Lighter alternative: `make dev` (API + Vite natively; stop with `make dev-down`).
5. Stop: `make down`, `make llm-down`.

`make probe` checks GPU, Docker, sim image, LLM chat and JSON, Tier 1, stage check,
Open-Meteo, Tavily and the incident data in one go.

## Try these (5 minutes)
A full organizer walkthrough is in [TESTING_GUIDE.md](TESTING_GUIDE.md).
- Open the sample "Halloween night · T-shaped alley" → **Red Team** tab → read attack cards
  (with incident links), click **Show in 3D**, open **Branch tree**, **Compare before and after**.
- Open "Waterfront Spring Festival · Wellington" → wind chart, stage limit, countdown chip.
- New project from *Conference hall, 2 floors* → type "add a 3 m exit on the east wall" →
  **Simulate** → **Run stress test** → click a hotspot → **Ask the venue**.
- Simulate → `X` tool → click a door ("Break it yourself") → **Confirm with simulation**.
- **Report** → Export PDF / Evacuation map.

## Use another hosted model for testing (optional)
`LLM_PROVIDER=openai` with `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_LABEL`
and `MODEL_*` works with any OpenAI-compatible API, e.g. OpenRouter's free Nemotron models
(`nvidia/nemotron-3-super-120b-a12b:free`) with `LLM_EXTRA_BODY={"reasoning":{"enabled":false}}`
and `LLM_SUPPORTS_JSON_SCHEMA=false`. Free OpenRouter keys allow about 50 requests a day.
The hackathon submission must still run on Nebius.

## Switch to Nebius
- In `.env`: `LLM_PROVIDER=nebius`, `SANDBOX_PROVIDER=nebius`, `NEBIUS_API_KEY=…`, and the
  `MODEL_FAST/LONG/MAIN/JUDGE` ids from the Token Factory console (plus prices for the cost meter).
- `make smoke-nebius` (skips cleanly without a key). Details: [NEBIUS_SWITCH.md](NEBIUS_SWITCH.md).

## Status
| Feature | Status | Notes |
|---|---|---|
| Templates (4), projects, versions, undo/redo, import/export | Done | SQLite + Alembic; survives restarts |
| Event Copilot (one sentence → site, layout, estimates, project, simulation) | Done | Live-tested with Nemotron 3 Super on Ramna Park (6,000 people); scripted test offline |
| Plan for the day estimates (capacity, exits, staff, toilets, fencing, budget) | Done | Ratios cited in `api/data/planning_ratios.json`; check local rules |
| New venue from a description (designer agent + solver + checks) | Done | Tested live with Nemotron 3 Super (OpenRouter) and offline with a scripted model |
| New venue from a real place (OpenStreetMap search, buildings, areas, drawn box) | Done | Tested on BUET buildings, a BUET area and Ramna Park; needs internet |
| 3D plan, drag edit, draw barrier/zone/exit, measure | Done | R3F; snaps to 0.5 m |
| Text edits (Venue agent) | Done | 10/10 on scripted edits with local Nemotron |
| Geometry checks + example rules pack | Done | Rules labelled "example values (IBC 2021)" |
| Instant estimate (Tier 1) + Break it yourself | Done | 3–20 ms |
| Tier 2 / Tier 3 JuPedSim simulation, heatmap replay | Done | Docker sandbox, `--network=none` |
| Two-floor venues | Done | Stair queue chaining (approximation, see ASSUMPTIONS) |
| Red Team Night (red/blue/judge, rounds, confirmation) | Done | Rule-based fallbacks when the LLM is down |
| Branch tree, scoreboard, activity feed, cost meter | Done | |
| Time travel, split compare, marshal bubbles | Done | |
| Wind hazard (Open-Meteo + Pynite) and countdown | Done | Screening estimate |
| Ask the venue | Done | Number-checked |
| Report (HTML/PDF), SVG evacuation map, JSON bundle | Done | |
| Sample projects with finished sessions | Done | Installed on first start from `cache/demos/` |
| DXF / JSON import | Done | DXF uses JuPedSim `jps-*` layer names |
| Nebius Token Factory adapter | Built, unit-tested | Untested live: no key |
| Nebius Sandboxes runner | Built against contree-sdk 0.3.6 source, fake-client tests | Untested live: no access |
| Tavily search | Built, cached, capped | Untested live: no key; dataset fallback works |
| Validation vs Jülich experiments, IFC import, narrated walkthrough | Not done | P2, see BACKLOG |

## Test results
| Check | Result |
| --- | --- |
| `make check` | green (lint, format, import boundaries, mypy --strict, tsc, fast tests) |
| `make test` | 96 passed, 1 skipped (Nebius live test needs a key) |
| `make test-web` | 10 passed |
| `make e2e` | 3 journeys passed |
| `make smoke` | OK (40–80 s), lowest free RAM 4.28 GB |
| Venue agent eval (local Nemotron) | 12/12 |
| Memory | llama-server ≈ 0.9–2.2 GB RSS, 6.4 GB VRAM; sims capped at 2 GB |

Details and the screenshot self-review: [PROGRESS.md](PROGRESS.md).

## Known issues and approximations
- Crowd model (CFSM) simulates walking and queuing, not pushing forces. Head-on counterflow in
  narrow streets can gridlock (used deliberately by the counterflow attack, but it is a model
  property). Engine artefact fixes (doorway capture, squeeze, sidestep) are documented in PROGRESS.
- Stairs are a capacity-limited queue between floors, not a walkable ramp.
- Tier 1 is optimistic for open-air crowds queuing across a wide front (calibration ratio
  0.62–0.63 vs 1.10–1.11 indoors); the ratio is printed in every report.
- Wind reanalysis smooths out thunderstorm downbursts; enter a manual gust when storms are likely.
- Docker Desktop's VM has 3.3 GB here, so sims are capped at 2 GB (`SIM_MEM_LIMIT`).
- The API container mounts the Docker socket to launch sims (local development only; see SECURITY.md).

## Unverified items (need human check)
- Nebius model ids and prices (copy from the console into `.env`).
- Nebius Sandboxes calls with a real key (`make smoke-nebius`).
- Tavily with a real key.
- Feliciani dataset licence: Zenodo record lists CC BY 4.0 — confirm before redistributing
  derived data (we download at setup, never commit it).
- Template dimensions are illustrative (the T-alley follows published Itaewon measurements; see ASSUMPTIONS).
