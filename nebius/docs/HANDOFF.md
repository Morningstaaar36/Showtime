# Showtime — Handoff

## Start it
1. `cp .env.example .env`, then set three lines: `LLM_PROVIDER=openai`,
   `OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1` and `OPENAI_COMPAT_API_KEY=...`.
   The OpenRouter Nemotron model ids fill in on their own. With no key, use **Offline** tests.
2. `make setup`: first time only. It installs the Python env, web deps, the sim image and the
   incident data, all inside this folder (`.tools/`, `data/`). It fetches llama.cpp and the
   Nemotron Nano GGUF only when `LLM_PROVIDER=local`.
3. `make up` → open http://localhost:5173 (Docker Compose: API + static web).
   Lighter alternative: `make dev` (API + Vite natively; stop with `make dev-down`).
4. Stop: `make down` (and `make llm-down` if you started the local model).

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

## The local model (optional)
`LLM_PROVIDER=local` runs Nemotron Nano 9B v2 on your GPU (`make llm-up`, about 6.4 GB VRAM). It
is also the automatic fallback when the hosted model is paused, for example by a used-up daily
quota. The badge then shows OPENROUTER → LOCAL. Free OpenRouter keys allow about 50 requests a
day.

## Switch to Nebius
Only `.env` changes:
- **Token Factory:** `LLM_PROVIDER=nebius` and `NEBIUS_API_KEY=…`. Model ids left from another
  provider switch to the Nebius preset on their own.
- **Sandboxes:** `SANDBOX_PROVIDER=nebius` and `NEBIUS_PROJECT_ID=…`.
- **Check:** `make verify-nebius-llm`, `make verify-nebius-sandbox`, then `make up`.

Details: [WHEN_YOU_GET_THE_KEYS.md](WHEN_YOU_GET_THE_KEYS.md) and [NEBIUS_SWITCH.md](NEBIUS_SWITCH.md).

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
- Nebius Token Factory with a real key (`make verify-nebius-llm`). The preset ids were checked
  against Nebius's public model info on 2026-10-26.
- Nebius Sandboxes with a real key and project ID (`make verify-nebius-sandbox`, which also proves
  that the network is off).
- Tavily with a real key (`make verify-tavily`).
- Feliciani dataset licence: Zenodo record lists CC BY 4.0 — confirm before redistributing
  derived data (we download at setup, never commit it).
- Template dimensions are illustrative (the T-alley follows published Itaewon measurements; see ASSUMPTIONS).
