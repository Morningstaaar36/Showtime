# Feature and quality checklist

Every feature and every quality check, ticked only after it was verified, with the evidence next
to it. Unticked items are not verified yet.

Evidence:
- **Chrome** means driven in Google Chrome by a script in `web/e2e/` (the spec or script is named).
- **Test** names an automated test.

Problems found are logged in [QA_LOG.md](QA_LOG.md). The last full visible run (2026-10-26): 19 of 19
checks passed in one take.

## 1. Start a venue

- [x] Home loads, and its three ways to start are shown (Chrome: `qa-crawl.mjs`)
- [x] Describe a venue in one sentence: metro, mosque, market (Chrome: `explore-describe.mjs`, `describe-*.png`)
- [x] Describe with a bad key shows the reason and what to do (Chrome: `explore-badkey.mjs`)
- [x] Pick a place on the map: search a place and build the venue (needs internet: OSM) (Chrome: `qa-visible.mjs`)
- [x] Draw an area on the map (Chrome: `qa-visible.mjs`)
- [x] Start from a template: create a project (Chrome: `journeys.spec.ts`)
- [x] Real cases: a double click opens one project, and the card shows its sources (Chrome: `real-cases.spec.ts`, `explore-real-case.mjs`)
- [x] Autopilot "Plan it for me": a sentence to a venue, a test and a plan (Chrome: `qa-visible.mjs`, on the hosted model)
- [x] Import a `.showtime.zip`, a venue `.json` and a `.dxf` (Chrome: `qa-visible.mjs`; Test: `test_importers.py`)

## 2. Check your venue

- [x] An exit's width can be edited, and it saves a version (Chrome: `test-plan-click.spec.ts`, `journeys.spec.ts`)
- [x] Lock an item: its controls become read-only (Chrome: `journeys.spec.ts`)
- [x] Headcount per zone: + / − and typed values save (Chrome: `qa-visible.mjs`)
- [x] Drag a door from the palette onto the venue (Chrome: `qa-visible.mjs`); fence, crowd and stall placement (Test: `dragDrop.test.ts`)
- [x] Kind of event and people mix: the usual mix is saved in every area (Chrome: `qa-visible.mjs`)
- [x] Floors: switch, spread apart (Chrome: `qa-visible.mjs`)
- [x] Test modes: Quick, Standard, Deep and Offline are remembered and sent (Chrome: `test-mode.spec.ts`; Test: `testModes.test.ts`)
- [x] Ask or change anything: a what-if and a question (Chrome: `qa-visible.mjs`)

## 3. AI at work

- [x] Live steps, the sandbox feed and tool calls (Chrome: `sandbox.spec.ts`, `explore-journey.mjs`)
- [x] Stop a running test (Chrome: `qa-flows.mjs`)
- [x] A killed sandbox restarts and says so (Chrome: `explore-killed.mjs`)
- [x] No sideways scroll on a phone (Chrome: `release-quality.spec.ts`)

## 4. Your plan

- [x] Overview: the verdict, the key numbers, the case card (Chrome: `journeys.spec.ts`)
- [x] Rules standing in for the AI are stated (Chrome: `explore-badkey.mjs`; Test: `test_stood_in.py`)
- [x] Replay: play and pause (Chrome: `qa-visible.mjs`)
- [x] Scenarios: cards, the Evidence panel, the failure map (Chrome: `evidence.spec.ts`, `explore-claims.mjs`)
- [x] Deeper checks: more seeds and the range (Chrome: `seed-check.spec.ts`)
- [x] Sandboxes: AI-written code, Rewind, Stress test at scale (Chrome: `rewind.spec.ts`, `explore-plan.mjs`)
- [x] Fixes: choose fixes and accept them as a new version (Chrome: `qa-visible.mjs`)
- [x] Floors tab (Chrome: `qa-visible.mjs`)
- [x] Hand over: the checklist and the report carry the disclaimer (Chrome: `explore-plan.mjs`)

## 5. Expert view

- [x] Edit by text, and undo with Ctrl+Z (Chrome: `journeys.spec.ts`)
- [x] Run a stress test (Chrome: `journeys.spec.ts`)
- [x] Break it yourself: block an exit, then confirm with a simulation (Chrome: `qa-visible.mjs`)
- [x] Red Team tab: cards, failure map, branch tree, activity, before/after compare (Chrome: `qa-visible.mjs`)
- [x] Report: preview and every export: SVG map, JSON bundle, glb, zip (Chrome: `qa-visible.mjs`)
- [x] Building tools: add a floor, stairs and a room (Chrome: `building-tools.spec.ts`)
- [x] Scripts: an unsafe script is refused with its reason (Chrome: `scripts.spec.ts`)
- [x] Scripts: an analysis script runs in the sandbox and shows its table or chart (Chrome: `qa-visible.mjs`)
- [x] Version history: restore an earlier version (Chrome: `qa-visible.mjs`)

## 6. Projects

- [x] Search, copy, download, import, delete (Chrome: `qa-visible.mjs`, `qa-flows.mjs`)
- [x] An empty project list shows its empty state (Chrome: `qa-visible.mjs`, with the list answered empty)

## 7. Other screens

- [x] Help: sections, the sandbox proof, the simulator validation (Chrome: `sandbox.spec.ts`, `explore-claims.mjs`)
- [x] AI team page (Chrome: `sandbox.spec.ts`)
- [x] Settings: units persist after a reload (Chrome: `qa-visible.mjs`)
- [x] Welcome checklist: every row ready (Chrome: `qa-visible.mjs`)
- [x] Unknown pages explain themselves (404) (Chrome: `journeys.spec.ts`)

## 8. Quality: accessibility, responsiveness, i18n

- [x] WCAG 2.2 AA (axe) on the simple screens, light and dark (Chrome: `release-quality.spec.ts`)
- [x] Keyboard reaches the primary action of each simple screen (Chrome: `release-quality.spec.ts`)
- [x] Phone widths 320, 375 and 414 px without sideways scroll (Chrome: `release-quality.spec.ts`)
- [x] No console errors on any page (Chrome: `release-quality.spec.ts`)
- [x] Every UI string comes from `en.json`: components, props, toasts, lists and `.ts` modules (Test: `literals.test.ts`, `keys.test.ts`)
- [ ] Every screen and every safe click crawled with no errors (Chrome: `qa-crawl.mjs`)

## 9. Quality: generic, configurable, nothing hardcoded

- [x] Providers are plug-ins; switching is `.env` only (Test: `test_env_only_switch.py`, `test_provider_registry.py`)
- [x] Venue knowledge comes from data files (Test: `test_generic_venues.py`)
- [x] The designer handles any venue: the prompt has no case text (Test: the guard in `test_venue_designer.py`)
- [x] No venue-specific names (doors, gates, stairs, places) in app code (scan of `api/` and `web/src`, 2026-10-26; new items are named from `en.json`)
- [x] Every limit and threshold is a setting, and the page judges runs by the server's values (Test: `test_env_example.py`, `test_break_rules_come_from_the_settings`, `test_osm_settings.py`, `verdict.test.ts`)

## 10. Quality: security, dependencies, code health

- [x] AI-written code runs only in the sandbox: 14 attacks stopped (Test: `make sandbox-proof`)
- [x] No secrets in the repository or its history (git scan, 2026-10-26)
- [ ] Dependency audit: `pip-audit` and `npm audit` (not run: waiting for your go-ahead)
- [x] API input limits: upload size and type, request validation (Test: `test_importers.py`; checked with a 6 MB file and an `.exe`)
- [x] CORS limited to the web origin; keys never sent to the browser (checked with a foreign `Origin`, and `/settings` and `/health` hold no keys)
- [x] Lint, types and import contracts clean (Test: `make check`)
- [x] Dead code: vulture (two intended hits) and a scan of web exports; unused code removed (e5b5d96, ad48cff)

## 11. Release

- [x] `make test` passes (917), and so does CI on GitHub
- [x] A clean clone works from the README
- [x] The live walkthrough (`docs/DEMO.md`), start to finish (Chrome: `explore-demo.mjs`)
- [ ] Stray shells, servers and background jobs cleaned up
