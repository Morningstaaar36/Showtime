# QA log: problems found by testing the app in Chrome, and their fixes

Every problem below was found by driving the real app in Google Chrome. The scripts live in
`web/e2e/`: `qa-visible.mjs` (every feature, in a visible window with captions), `qa-crawl.mjs`
(every screen, every safe click), `qa-flows.mjs` (feature flows) and the `explore-*.mjs` scripts. Each fix has a test that failed first, unless the row says otherwise.
Screenshots are in `docs/screenshots/step7/` unless the row says otherwise.

| # | Found | Problem | Fix | Guard |
| --- | --- | --- | --- | --- |
| 1 | Bad model key (a second API with an invalid key) | Rules wrote the attacks and the summary, but the plan looked like an AI test, and a rule script was logged as "AI-written" | The summary records `stood_in`; the plan and the report say "The AI didn't answer, so built-in rules wrote …" (cf4cc4d) | `api/tests/test_stood_in.py`, `stoodIn.test.ts` |
| 2 | Bad key | The "model isn't answering" hint said `make llm-up` on a hosted provider; Home's error toast dropped the API's hint and vanished in 4 s; the banner ended in ".." | The hint names the rejected key or the pause; toasts carry the hint for 12 s (7fddbc7, eec6e6d) | `test_llm_unavailable.py`, `client.test.ts` |
| 3 | `docker kill` on a running simulation | The run restarted silently and the error claimed "out of memory" | The feed says the first sandbox stopped and the run restarted; exit 137 names both causes (b8632e6, c50b3a8) | `test_sandbox_feed.py`, `test_crash_hint.py` |
| 4 | Live Quick test | An AI script that crashed was labelled "Stopped by a limit" | "Failed: error in its code"; red-team prompt v6 warns about empty lists (42ecfa9, 785e5ad) | `test_sandbox_feed.py`, `SandboxFeed.test.ts` |
| 5 | Scrolling Your plan and AI at work | The 3D view's floor switch drew over the sticky header | The 3D views isolate their layers (85d1543) | `header-on-top.spec.ts` |
| 6 | Sandboxes tab at 1600 px | The Rewind table's last column was cut off | Rewind and Stress test stack full width (202e95c) | `rewind.spec.ts` (column fits) |
| 7 | Phone width 320 px | AI at work scrolled sideways (419 px) | `minmax(0,1fr)` grid column (8f7c291) | `release-quality.spec.ts` |
| 8 | axe, light theme | Sandbox feed state words below AA contrast | Darker text shades (37d551a) | `release-quality.spec.ts` |
| 9 | Fresh install, real case | While the first test ran, the case's sources were hidden | The case card shows at once (3bbf8ca) | Checked in Chrome on a fresh install (`clean-clone-real-case.png`) |
| 10 | Code review against the Nebius docs | Sandboxes need `NEBIUS_PROJECT_ID`; the network is on by default; leftover model ids broke the `.env` switch | The project ID is sent; the network is off per run; presets fill leftovers (ae14871) | `test_env_only_switch.py` |
| 11 | Scan of the components | 229 UI strings were written in components instead of the locale file | All are in `en.json`; whole sentences with variables (4e54b3d) | `src/i18n/literals.test.ts` (TypeScript parser) |
| 12 | Demo tour in a visible window | The tour typed into the middle of the example script | The tour clears the box first (`demo-tour.mjs`) | A headless run of the whole tour |
| 13 | Palette drag in `qa-visible.mjs` | A door dropped a little inside the venue was refused ("drop it near a wall") | It goes on the nearest outer wall (f979a2b) | `dragDrop.test.ts` (`onNearestWall`) |
| 14 | Simulate panel, keyboard only | Exits could be blocked only by clicking them in 3D | Exit toggles in the panel (636c0ac) | `break-it.spec.ts` |
| 15 | `qa-crawl.mjs`, Welcome | A request to a removed endpoint (`/agents`) answered 404 on every visit | The page reads the AI team from `/health` (3677aef) | The crawl: 106 screens, no failed requests |
| 16 | Response headers in Chrome DevTools | No `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` or `Permissions-Policy` | Set on the API and in nginx (3677aef) | `test_security_headers.py` |
| 17 | Map tab review | The map services, the start position and the largest area were constants naming one city | All are settings, sent with `/health` (b1516a2) | `test_osm_settings.py`, `mapConfig.test.ts` |
| 18 | Report preview | Credits listed every provider, used or not | Each part cites itself; the report credits what the run used (5983bc4) | `test_stood_in.py::test_the_report_credits_what_was_used_as_each_part_cites_itself` |
| 19 | Replay of an older run | The replay asked for a people mix the run never recorded (404 in the console) | It asks only when the run's artifacts list one (910b84f) | `agentKinds.test.ts` |
| 20 | Projects, import | The accepted file types were written by hand in the page and in the error | Both come from the importer plugins, `GET /importers` (e745abd) | `test_importers.py`, `importTypes.test.ts` |
| 21 | Import check in `qa-visible.mjs` | The check could not write its DXF (wrong working folder) | Fixed in the script; JSON and DXF imports pass in Chrome (1050681) | `qa-visible.mjs` |
| 22 | Kind of event in `qa-visible.mjs` | "Use the usual people mix" was not tested: the check picked a kind with no usual mix | The check picks a kind that has one and confirms the saved mix (f2dc629) | `qa-visible.mjs` |
| 23 | Red Team tab in Chrome | Tab names, the empty state and the start toast were English written in the component; the guard missed props, joined strings, lists and `.ts` modules | The guard checks all of them; 60 strings moved to `en.json` (661ed9b) | `literals.test.ts` |
| 24 | Review of the verdict code | The page judged runs with its own numbers (5 s above danger, 5 people left, 30 s at risk, danger 5 in the what-if lab); the danger-time setting was ignored | The rules are settings, sent to the browser; the page, the server and the score read the same values (32e0cca, 661ed9b) | `test_redteam.py::test_break_rules_come_from_the_settings`, `verdict.test.ts` |
| 25 | Red-team summary | "Still at risk" when one person of thousands was left inside, unlike the server's tolerance | Uses the same tolerance as the server (661ed9b) | `verdict.test.ts` |
| 26 | Map search box | The placeholder named particular places | A generic example (661ed9b) | `literals.test.ts` |
| 27 | Palette hints | "2 m door" and "200 people" were written in the text, apart from the values used | The hints read the values the drop uses (661ed9b) | `dragDrop.test.ts` |
| 28 | Upload over the limit | The error said the size but not what to do | It names the fix and the setting (a5e3a62) | `test_importers.py` |
| 29 | Real cases in Chrome: Shanghai Bund 2014 typed into the new form | The geocoder did not know the square and the form saved the case at 0, 0 | The form asks for a location before saving (1a307d7) | `realCases.test.ts` (`missingField`) |
| 30 | Real cases in Chrome: Kanjuruhan 2022 | The designer had no way to draw a locked gate, so it dropped all three | Exits take `"closed": true` and are built blocked; designer prompt v12 (b29cf28) | `test_venue_designer.py::test_a_locked_exit_is_drawn_but_closed` |
| 31 | Real cases in Chrome | A layout that needed fixing opened in the editor without saying why; a second click skipped the server, so it was never designed again | The editor opens with the designer's problems; tiles always ask the server (1a307d7) | `real-cases.spec.ts`, `test_saved_cases.py` |
| 32 | Review against the Nebius Sandboxes docs | Every spawn ran without a network, the setup pip install too, so no Nebius run could finish | Only the setup run keeps the network; the base image and pins come from `sim/Dockerfile` (fa8f5c5) | `test_env_only_switch.py` |
| 33 | Token Factory deprecation notice | Nemotron 3 Nano and Super leave Serverless on 2026-11-09 | Presets are data (`api/data/llm_presets.json`) with Lightning and 3.5 Super VL; documented `reasoning_effort` (c2f1d59) | `test_env_only_switch.py` |
| 34 | Code scan | The HTML report judged runs with its own 5 s, 5 people and 3.5 per m² | One break rule in the plugin SDK, built from the settings (2beea83) | `test_report_evidence.py::test_the_report_judges_with_the_servers_rules` |
| 35 | Code scan | The simulator fell back to a 1.0 s time gap (setting 0.25) and a hardcoded counterflow inflow | One table of sim defaults, kept equal to the settings (71e41b7) | `test_sim_defaults.py` |
| 36 | Code scan | A rule-written power cut slowed people to 60% where ASSUMPTIONS.md says 70%; "Ask anything" used smoke 0.6 against 0.5 | Both use the scenario library's cited speeds (fcff918, 7954e09) | `test_session_modes.py` |
| 37 | Code scan | Help's glossary stated 3.5, 5, 60 s and 1.5 as text | Filled from the settings (881229d) | `test_glossary.py` |
| 38 | Code scan | Two densities for a new crowd (palette 2 per m², drawn area 1.5); page copies of targets, seed, speeds, item sizes and test depths | All from the server (`settings.editor`, `speed_presets`, `/test_modes`) (96c442c) | `editorDefaults.test.ts`, `speedPresets.test.ts`, `testModes.test.ts` |
| 39 | Code scan | 60+ UI strings bypassed en.json in patterns the guard missed; examples named real places | The guard covers them; strings moved; examples are generic (661ed9b, 78c82ef) | `literals.test.ts` |
| 40 | Sim tests at the production time gap | The 0.05 s step is ~21% slower than 0.01 s on a small room (documented: 8%, measured at the old gap) | Documented and tested at the calibrated gap (71e41b7) | `sim/tests/test_sim.py::test_time_step_calibration` |
