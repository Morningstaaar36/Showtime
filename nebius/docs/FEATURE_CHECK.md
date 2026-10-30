# Feature check

What was verified before this release, how, and with what result. Every command runs from
`nebius/` with the app up (`make up`). Live runs used NVIDIA Nemotron on OpenRouter (free
models) with `LLM_CACHE_MODE=record`, so nothing was replayed, and Docker sandboxes with
`SANDBOX_MAX_PARALLEL=3`.

Last run: 2026-10-30.

## Automated tests

| Check | Command | Result |
| --- | --- | --- |
| Lint (ruff, eslint, import boundaries) | `make lint` | clean; 3 import contracts kept |
| Types (mypy --strict on core, adapters, orchestrator; `tsc -b`) | `make typecheck`, `cd web && npx tsc -b` | no issues |
| Python tests, with simulations in real sandboxes | `make test` | 982 passed (one autopilot test hit a disk I/O blip under load and passed on its own rerun) |
| Web unit tests | `make test-web` | 276 passed in 55 files |
| End-to-end smoke against the running app (edit by text, instant estimate, full simulation, red team, blue team, judge, report and map) | `make smoke` | SMOKE OK in 89 s |
| Browser checks, headless, no model calls | `npx playwright test e2e/break-it.spec.ts e2e/real-cases.spec.ts e2e/scripts.spec.ts e2e/surroundings.spec.ts e2e/header-on-top.spec.ts e2e/operational-plan.spec.ts e2e/zone-profile.spec.ts e2e/building-tools.spec.ts` | 8 passed |

Tests never touch the app's own database or run folder (each test session gets its own), so the
suite can run while the app is serving.

## A real case, end to end with the AI

`make live-case CASE=docs/examples/bailey-road-case.json` writes the case through the API, opens
it, and presses "Let the AI fix it". Nothing in the code knows the case. Three runs were made
while finishing this release; the last record is in
[examples/bailey-road-case.run.json](examples/bailey-road-case.run.json).

| Step | What it checks | Seen |
| --- | --- | --- |
| Real case form → designer | A description becomes a seven-storey building with a dining fit-out on every floor | 22 × 14 m, 7 storeys, one 1.2 m stair, one street door, 290 people; kitchens, toilets, lifts, tables, enclosed stairwell |
| Map lookup | The real building's outline, or a stated fallback | "OpenStreetMap has no building outline at this point; the described size was used." |
| Design rounds and plan critic | Rounds recorded; the critic's points alone earn one revision | 2 rounds, round 1 kept; critic notes shown |
| Plan checker | Ways out, walking distance, crowding and the instant estimate per round | nothing to send back (0 fixes in each round); instant estimate 115 s |
| Red team in parallel sandboxes | Attacks grounded in real incidents, one written as code | 3 of 3 attacks broke the plan; worst left 152 of 290 inside |
| Blue team and the simulator | A structural fix is proposed and proven | "Add a second stairwell at the south-west corner" kept |
| Let the AI fix it | Proven fixes become a version; the plan is tested again | Run 2: v1 3/3 → stairwell → v2 2/3 → both stairs 2.0 m → v3 0/3, holds. Run 3: v1 3/3 → stairwell → v2 1/3 (38 inside, down from 152), no further fix held, and the loop said so |

## Screens

The README's screenshots (`docs/screenshots/readme/`) were taken headless from the running app by
`node e2e/readme-shots.mjs ../docs/screenshots/readme "<case title>"` (and `… live` while a test
runs). The Bailey Road set is in `docs/screenshots/bailey/`.

## Earlier, broader checks

A visible, feature-by-feature pass in Chrome (`e2e/feature-check.mjs`, `e2e/qa-visible.mjs`) ran
on 2026-10-29 over every screen: projects and imports, Check your venue, the AI at work, Your plan,
Expert view (Plan, Simulate, Red Team, Report, Analysis), scripts, the narrated tour, hand over
and help. Every failure it found was a script selector, fixed in those scripts; the app changes it
led to are in the CHANGELOG. Its checklist by area is [FEATURE_CHECKLIST.md](FEATURE_CHECKLIST.md).
