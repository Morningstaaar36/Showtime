# Showtime — Handoff

Updated 2026-10-30. To try it, start at [JUDGE_GUIDE.md](JUDGE_GUIDE.md).

## Start it

1. `cp .env.example .env`, then set `OPENAI_COMPAT_API_KEY=` to a free OpenRouter key. The
   OpenRouter Nemotron model ids fill in on their own. With no key, use **Offline** tests.
2. `make up` → open http://localhost:5173. Needs only Docker and make: it builds the sandbox
   image, the API and the web app, and fetches the incident dataset inside the API image.
3. Stop: `make down`.

Developer setup (host Python and Node for `make check`, `make dev`, or the local model):
`make setup`, then `make dev` (API + Vite natively; stop with `make dev-down`). Hosting on a
server: [HOSTING.md](HOSTING.md).

## Try these (5 minutes)

[JUDGE_GUIDE.md](JUDGE_GUIDE.md) has the short path; [TESTING_GUIDE.md](TESTING_GUIDE.md) is the
full organizer walkthrough.
- **Projects** › open the sample "Halloween night · T-shaped alley" › **Your plan**: the
  **Scenarios** tab (failure map, attacks with incident links, **Evidence**), **Fixes**,
  **Replay**.
- Open "Waterfront Spring Festival · Wellington": wind chart, stage limit, countdown.
- **Projects › New project › Conference hall, 2 floors › Create project**, then **Expert view**:
  type "add a 3 m exit on the east wall", **Simulate › Run stress test**, click a hotspot ›
  **Ask the venue**.
- **Expert view › Simulate › Break it yourself**: click an exit to block it, then **Confirm with
  simulation**.
- **Your plan › Download report** and **Download checklist**.

## The local model (optional)

`LLM_PROVIDER=local` runs Nemotron Nano 9B v2 on your GPU (`make setup` fetches it, `make llm-up`
starts it, about 6.4 GB VRAM). Free OpenRouter keys allow about 50 requests a day; when the
hosted model is paused, the badge says so.

## Switch providers

Only `.env` changes (`make use-openrouter`, `make use-local`, `make use-list`); where each key
goes, and how to check it, in [PROVIDERS.md](PROVIDERS.md).

## Status

| Feature | Status | Notes |
|---|---|---|
| Templates (4), projects, versions, undo/redo, import/export | Done | SQLite + Alembic; survives restarts |
| Event Copilot (one sentence → site, layout, estimates, project, simulation) | Done | Live-tested on OpenRouter Nemotron (Ramna Park, 6,000 people); scripted test offline |
| Plan for the day estimates (capacity, exits, staff, toilets, fencing, budget) | Done | Ratios cited in `api/data/planning_ratios.json`; check local rules |
| New venue from a description (designer agent + solver + checks) | Done | Live on OpenRouter Nemotron; offline with a scripted model |
| New venue from a real place (OpenStreetMap) | Done | Needs internet |
| 3D plan, drag edit, draw barrier/zone/exit, measure | Done | R3F; snaps to 0.5 m |
| Text edits (Venue agent) | Done | 12/12 scripted edits with local Nemotron Nano |
| Geometry checks + example rules pack | Done | Rules labelled "example values (IBC 2021)" |
| Instant estimate (Tier 1) + Break it yourself | Done | milliseconds |
| Tier 2 / Tier 3 JuPedSim simulation, heatmap replay | Done | Docker sandbox, `--network=none` |
| Multi-storey venues | Done | Stair queue chaining (approximation, see ASSUMPTIONS) |
| Red Team Night (red/blue/judge, rounds, confirmation) | Done | Menu attacks plus at most one AI-written scenario script per round; rule-based fallbacks when the model is down |
| Real cases (examples + your own via **Add a real case**) | Done | Illustrations from hand-written descriptions ([REAL_CASES.md](REAL_CASES.md)) |
| Rewind the worst moment, stress test at scale | Done | |
| Wind hazard (Open-Meteo + Pynite) and countdown | Done | Screening estimate |
| Ask the venue / analyst | Done | Every number in the answer checked against the computed results |
| Report (HTML/PDF), SVG evacuation map, checklist, JSON bundle | Done | |
| Sample projects with finished sessions (4) | Done | Installed on first start from `cache/demos/` |
| DXF / JSON import | Done | DXF uses JuPedSim `jps-*` layer names |
| Validation vs the Jülich 2006 bottleneck experiment | Done | [VALIDATION.md](VALIDATION.md): calibrated and checked on the same experiment |
| Hosting on a server (`make cloud-up`: Caddy, HTTPS, password) | Built | Checked locally (`docker compose config`, `caddy validate`) ([HOSTING.md](HOSTING.md)) |
| Tavily search | Built, cached, capped, fake-client tests | **Not run live**: no key; dataset fallback works |
| IFC import | Not done | |

## Tests

`make check` (lint, format, import boundaries, mypy --strict, `tsc -b`, fast API tests),
`make test` (all Python tests, including the simulator tests; needs Docker), `make test-web`
(vitest), `make e2e` (Playwright journeys; needs the app running), `make smoke`. CI runs the same
checks: `.github/workflows/ci.yml`. Run them for current counts rather than trusting a number
in a document.

## Known issues and approximations

- The crowd model (collision-free speed model) simulates walking and queuing, not pushing forces.
  The squeeze rule shrinks bodies at a clogged door so the model does not deadlock, which lets
  density there exceed what the normal bodies can pack (about 6 per m²): read such peaks as a
  severe jam, not a crush density ([ASSUMPTIONS.md](ASSUMPTIONS.md)). The crowd-pressure layer
  is indicative.
- Head-on counterflow in narrow streets can gridlock (a model property).
- Stairs are a capacity-limited queue between floors, not a walkable ramp.
- Tier 1 is optimistic for open-air crowds queuing across a wide front; the calibration ratio is
  printed in every report.
- Wind reanalysis smooths out thunderstorm downbursts; enter a manual gust when storms are likely.
- The API container mounts the Docker socket to launch sims (see SECURITY.md; `make dev` runs
  the API natively instead).
- Model replies are cached by default (`LLM_CACHE_MODE=record_replay`): an identical call is
  replayed from `cache/llm/`. Your plan › *How this plan was made* counts them.

## Unverified items (need human check)

- Tavily with a real key (`make verify-tavily`).
- Feliciani dataset licence: the Zenodo record lists CC BY 4.0. Confirm before redistributing
  derived data (we download at setup, never commit it).
- Template dimensions are illustrative (the T-alley follows published Itaewon measurements; see
  ASSUMPTIONS).

History: [archive/PROGRESS.md](archive/PROGRESS.md), [archive/REVIEW.md](archive/REVIEW.md) and
the rest of [archive/](archive/).
