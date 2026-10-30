# Showtime, reviewed as a Nebius x NVIDIA judge would

Four AI reviewers read the repository the way a judge's agents would (read only, nothing run),
on 2026-10-29: criteria fit and claims, code and security, UI design, and setup and hosting.
This file is the merged list of what they found and what to fix, most costly first. Each item is
ticked when it is fixed, with the commit.

## The judging frame

Devpost blocks automated reading, so the criteria come from public copies of the rules
([startupgrantsindia](https://www.startupgrantsindia.com/competitions/nebius-x-nvidia-global-ai-hackathon),
[a participant's checklist](https://github.com/isayahc/Real-Time-Video-Agents-Hack-NYC/issues/34)):

- Four criteria, equal weight: **Technological implementation** (build quality, effective use of
  Nebius Token Factory / AI Cloud and NVIDIA open models), **Design** (a complete, coherent
  product, not a proof of concept), **Potential impact**, **Quality of the idea**.
- **Stage 1 gate** before scoring: the project fits a track and genuinely uses the required
  APIs/SDKs. It must run on Nebius Token Factory or Nebius AI Cloud and use at least one NVIDIA
  open model.
- Deliverables: a working demo URL, a public YouTube video under 3 minutes, a public repository
  with an open-source licence and a README, feedback on the Nebius/NVIDIA tools; claims must match
  what is demonstrated. Extra prize: Best Use of Tavily.
- Deadline: 2026-10-30, 17:00 UTC (1 pm New York).

## Scores a judge would give today

Conditional on passing the gate, which today it would not:

| Criterion | Score | Why |
| --- | --- | --- |
| Technological implementation | 5/10 | Excellent engineering (sandbox with a recorded attack suite, typed plugins, real validation), but the sponsor tech never ran live; Nemotron runs only through OpenRouter |
| Design | 7/10 | Complete and coherent, but too much: seven plan tabs, six places to type, two app shells |
| Potential impact | 6/10 | A real problem and underserved users; thin validation and liability limit trust |
| Quality of the idea | 7/10 | An LLM red team judged by a physics simulator it cannot flatter is new and feasible; overclaims undercut it |

## 1. Blockers (the gate and the deliverables)

- [ ] **Nothing has run live on Nebius.** `docs/LIVE_STATUS.md`: Token Factory, Sandboxes and
  Tavily are SKIPPED; only OpenRouter and Docker pass. A literal judge rejects the entry before
  scoring. Fix: ask the organizers for credits or a written exception for a blocked country
  (keep the reply); try a teammate in an eligible country for a key; with a key, run
  `make verify-live`, commit the PASS rows, record the video with the NEBIUS badge and host with
  `make deploy-nebius`. Without one, the submission opens with the eligibility situation and the
  evidence (adapters, presets, the 401 probe), not the tagline. *(Owner action; the code is
  ready for an `.env`-only switch.)*
- [ ] **No demo URL, no recorded video, and local `main` is ahead of GitHub.** Fix: host (VM or a
  tunnel), record from `docs/VIDEO_SCRIPT.md`, push, and put both links at the top of the README.
  *(Owner action for the video and the push.)*
- [ ] **`make deploy-nebius` could never copy the code**: a comment after `|` in
  `deploy/nebius_vm.sh` broke the pipe (`bash -n` passes, the run fails).

## 2. Claims that do not match the code (trust)

- [ ] "Every attack is code the AI wrote" (README, PITCH, DEMO): the red team writes at most one
  script attack per round (`MAX_SCRIPT_ATTACKS = 1`); the rest are menu attacks. Say "the red team
  can write attacks as code; that code only ever runs in a sealed sandbox".
- [ ] `docs/HOSTING.md` says Showtime *already uses* Token Factory and Sandboxes: it is built to,
  once keys exist.
- [ ] Which Nemotron did what: docs credit Nemotron 3 Super for live results while also saying
  the free Super endpoint returned 404; FEEDBACK praises Ultra's red team, but the red team runs
  on the fast role (Lightning); README says "JSON is schema-constrained" while both presets set
  `LLM_SUPPORTS_JSON_SCHEMA=false`. One sentence everywhere, from `llm_presets.json` and the
  agents' roles.
- [ ] Stale and contradicting numbers: tests (857, 875, 917, "96 passed"), HANDOFF's
  "Validation: not done" next to VALIDATION.md; VALIDATION.md's interpretation still describes
  the old 1.0 s time gap.
- [ ] "Nothing about a venue is hand-made": the templates and the real-case descriptions are
  hand-written (with crowd splits and headings). Drop the sentence; present real cases as
  illustrations, not evidence.
- [ ] Crush densities: "out of reach" in PITCH, yet Hillsborough reaches 9.9 per m² through the
  squeeze rule; explain the rule and label the pressure layer indicative.
- [ ] "Twelve agents" counts one agent twice and a mostly-regex router; "every number traceable"
  is stronger than the number check (a number must appear in the tool output, not the right
  one); cached replies replay by default. Say so plainly.
- [ ] Tavily use is shallow (basic depth, 5 results, no extract) and never ran live: don't pitch
  for the Tavily prize without a live run.

## 3. Setup and hosting (it must be easy)

- [ ] The password hash from `make cloud-password` is corrupted by Compose (`$2a$14$…` is
  expanded): print it quoted.
- [ ] `SIM_USER=1000:1000` in `docker-compose.yml` breaks simulations on hosts whose user is not
  uid 1000: remove it (the adapter already picks the right user).
- [ ] Docker-only and hosted installs never get the incident dataset (`get_data.sh` needs `uv` on
  the host): fetch it inside the api image.
- [ ] `make setup` needs host Node and uv although `make up` builds in Docker, and the default
  `LLM_PROVIDER=local` downloads a 6 GB model: default to a hosted provider (or offline), and a
  Docker-only path that needs only Docker and make.
- [ ] Hosted over plain HTTP by default: set `SITE_ADDRESS=<ip>.sslip.io` on deploy for HTTPS
  without a domain; drop the `WEB_ORIGIN` step (same origin behind Caddy).
- [ ] `.env.example` has 229 lines and 124 variables; a user changes 3. Cut it to the required,
  optional and hosting blocks; the rest keep their code defaults (documented in ASSUMPTIONS and
  settings).
- [ ] The LLM fallback defaults to a local server judges won't have: no fallback unless the
  provider is local.
- [ ] Caddy's `encode gzip` may buffer the live progress stream: remove it (nginx compresses).
- [ ] On a public VM with `SANDBOX_PROVIDER=nebius`, drop the Docker socket mount.
- [ ] A zero-cost way to show a live demo: `make share` (a tunnel), and the password in the
  Devpost testing notes.
- [ ] Docs contradict each other (where to edit presets, dates, sample names, old UI names) and
  sprawl (42 docs, planning files at the repo root): one judge guide, archive the history.

## 4. Design: make it simple (the UI review)

- [ ] Your plan has seven tabs: keep Overview (with the replay), Fixes and Hand over; Scenarios,
  Sandboxes, Floors and the deeper checks move to Expert view.
- [ ] The Overview verdict contradicts itself ("at risk" next to an all-green fix card): one
  sentence and one button ("At risk today. 1 tested fix makes it safe → Accept fix"); hide the
  countdown card when there is no hazard; no run ids.
- [ ] Six places to type a sentence and two autopilots: keep "Plan it" on Home and "Ask or change
  anything"; remove the Copilot box from Projects; one "AI tests it" screen.
- [ ] Home repeats itself (samples and "Events like yours"; a 3-step strip that repeats the
  header stepper): keep the gallery, tested cards first.
- [ ] One vocabulary: evacuation time (95%), peak density (people per m²), exit, red team, fix,
  instant estimate vs confirmed by simulation.
- [ ] Check your venue: test depth under "More options" (Standard by default); one floor
  switcher; floor totals for tall buildings.
- [ ] Organizer header without provider and sandbox badges (Settings and Expert view keep them);
  one app shell.
- [ ] "AI tests it": no AI-cost line for organizers; one signal colour for progress.
- [ ] Safety colours only for meaning (no orange fences, green neutral icons, red borders on every
  scenario card, gradients); no arrows in button text.
- [ ] Scenarios: "Holds" next to a red row of the same plan; "–" for evacuation time reads "not
  everyone got out".
- [ ] Phone: hero numbers wrap, floor pills overflow, 3D labels overlap.
- [ ] Contrast of small muted captions on tinted cards; a send button that looks disabled;
  reduced motion for the card animations.

## 5. Code and security

No blockers. The sandbox hardening (no network, read-only, dropped capabilities, limits,
non-root), zip-slip and path guards, escaped exports and the designed error shape hold up.

- [x] **A malformed `.showtime.zip` breaks the project list**: `import_zip` trusts
  `current_version` and version numbers; one bad import makes `GET /projects` fail for everyone.
  Validate the versions and parse inside the try (422), and let the list skip a broken row.
- [x] **Zip bomb**: entries are read without checking their uncompressed size (the 5 MB limit is on
  the compressed file). Cap the total uncompressed size before reading.
- [x] **The red-team stream can lose its last events** when a reload replays history while the
  session finishes. Drain the live events after the replay, as Autopilot does.
- [x] **The run cache ignores the simulator version**, and imported runs keep their ids: a sim fix
  never reaches cached runs, and an import can plant a result. Key runs by a simulator version;
  re-key imported runs; require artifacts for a cache hit.
- [x] **Sim containers survive an API crash**: remove leftover `showtime-sim-*` and
  `showtime-code-*` containers at startup.
- [x] **Anyone who can reach the API can lift the token budget** (`PUT /settings` has no upper
  bounds) and nothing caps total spend: bound the fields, add a daily spend cap and a limit on
  concurrent sessions.
- [x] **Cross-site requests** to the unauthenticated local API (simple POSTs skip the CORS
  preflight; DNS rebinding): trusted hosts, and a custom header on every write.
- [x] **Finished sessions are never freed** from memory: drop them when they end.
- [x] Blocking work in async routes (`GET /real_cases` reads every venue; DXF import parses on the
  event loop): run it in a thread.
- [x] Low: an unreferenced background task; SECURITY.md says agents never execute code (AI-written
  scripts do run, in the sandbox); unused share-link and observation tables; deleting a project
  does not stop its session or remove its run files; timing-based tests; no tests for the
  three bugs above. (All fixed except the unused tables: removing them needs a migration.)

## 6. Tests found failing

- [ ] `real-cases.spec.ts`: a double click sends two open requests (the button disables a moment
  too late); the server builds once, but the page should send one.
- [ ] `multi-storey.spec.ts`: the map-built hospital never shows "is ready." within 120 s (to be
  diagnosed in Chrome).
