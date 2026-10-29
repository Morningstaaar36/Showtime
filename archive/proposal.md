# Showtime: Red Team Night — Consolidated Project Proposal

**Prepared:** 9 October 2026

**Project:** Showtime, for the Nebius x NVIDIA Global AI Hackathon

**Repository:** <https://github.com/Morningstaaar36/Showtime>

**Application directory:** `nebius/`
**Recommended track:** Best Apps and Agents

This proposal consolidates the project description, feature inventory, competition assessment, critiques, corrections, and product decisions discussed in our conversation. It incorporates the latest direction: organizers and AI jointly create and correct a venue through conversation and a focused 3D editor.

The current development preference is **OpenRouter for model calls and local Docker for simulations**. Nebius Token Factory, Nebius Sandboxes, and Tavily integration work are deferred for now. The final submission must still satisfy the competition's platform requirements.

Implementation status below comes from repository documentation and selected code inspection. The application, model calls, and simulation results were not independently run or reproduced during these discussions. Planned features and recommended changes must not be represented as completed capabilities.

## 1. Project proposition

**Showtime helps event organizers create a venue model, identify crowd-flow weaknesses, compare feasible improvements, and hand over the exact plan that was tested.**

An organizer describes an event. AI extracts the requirements, retrieves available site information or drafts a layout, and asks targeted questions. The organizer inspects and corrects the venue in 3D. The system then runs crowd simulations, proposes disruptive scenarios, suggests permitted changes, and compares the resulting plans.

**Tagline:** “Run the disaster before the gates open.”

**Product pitch:** “Describe your event, correct the venue with AI, test what could go wrong, and choose a practical plan backed by inspectable simulation results.”

Claims such as “in minutes” or “for cents” should be added only after representative measurements. Calculated results can depend on assumptions; the phrase “no number is a guess” would overstate certainty when inputs and model parameters are estimated.

The product is a planning aid. It supports conclusions about tested scenarios under stated assumptions. It does not establish comprehensive event safety or replace every aspect of professional engineering judgment.

## 2. Problem, audience, and intended value

Event planning involves geometry, audience locations, gate availability, crowd routing, temporary equipment, staffing, and operational timing. Showtime aims to reduce the effort needed to turn those inputs into a plan that can be examined and stress-tested.

The strongest initial audience is a specific group that can participate in evaluation:

- University event committees.
- Community festival organizers.
- Operators of smaller venues.

Venue managers and permit reviewers are possible later audiences. Early evaluation should concentrate on one audience and a small number of accurately represented sites.

Potential value includes faster preparation, discovery of overlooked weaknesses, clearer comparison of alternatives, and a more usable handover. These are hypotheses to measure. The conversation did not establish market size, adoption, willingness to pay, or proven reductions in injuries.

## 3. Competitive assessment and corrections

The project has a credible competitive proposition. Its distinguishing workflow is an agent proposing a failure scenario, a simulator evaluating it, another agent proposing a repair, and simulation checking the result. A clear before/after replay can make that workflow understandable in a short demo.

The idea has not been established as unique through a comprehensive competitor study. No defensible probability of winning can be assigned from the available information. Completing every roadmap item would not guarantee a prize.

| Area | Consolidated assessment |
| --- | --- |
| Idea quality | Promising and coherent; the incident-informed attack-and-repair loop gives it an identifiable purpose. |
| Potential value | Credible, with actual organizer usefulness still to demonstrate. |
| Feature quantity | Already substantial. A shortage of features is not the main competitive concern. |
| AI involvement | Substantial across intake, design, edits, scenarios, fixes, and explanations. Calling the project low in AI usage would be inaccurate. |
| Technical credibility | Depends on accurate result provenance, appropriate model scope, reproducibility, and validation. |
| Practical usefulness | Depends on whether recommended changes are feasible and change an organizer's decision. |
| Design | Depends on whether an unfamiliar organizer can complete the central task without mastering all expert panels. |
| Submission readiness | Requires eventual live platform verification, an accessible demo, accurate documentation, and the submission materials. |

Several earlier recommendations needed correction:

1. Proposing many additions made feature quantity sound like the problem. The main priority is reliable execution of the central workflow.
2. Autopilot, simpler screens, repeated simulations, cost reporting, validation, and steward packs already appear in the roadmap. They should be extended rather than duplicated.
3. Organizer confirmation is not independent verification or certification. Information provenance needs precise labels.
4. The current agent workflow mixes model-generated and standard rule-based fixes. Evaluation must preserve that attribution.
5. A user study is evaluation work; a new survey dashboard is not necessary to conduct it.
6. A benchmark against standard fixes is useful for claims of superior optimization. It is not a prerequisite for recognizing the value of conversational venue creation and tool orchestration.
7. Existing disclosures already acknowledge modeling limits. The issue is consistency across screens, reports, and demonstrations, not a claim that the whole project universally promises safety certification.

## 4. Roles of the organizer, AI, and computation

| Participant | Responsibility |
| --- | --- |
| Organizer | Supplies requirements, corrects the reconstruction, records measurements or confirmations, declares constraints, and selects a plan. |
| AI agents | Interpret requests, identify missing information, draft layouts, propose scenarios and actions, orchestrate tools, and explain results. |
| Geometry and constraint code | Validates edits, enforces restrictions, checks references and resource availability, and maintains consistent versions. |
| Simulation and calculation tools | Produce modeled crowd movement, metrics, planning estimates, and other computed outputs. |
| Evidence and reporting layer | Preserves what was tested, how it was tested, the source of inputs, remaining uncertainty, and the selected actions. |

“AI acts like an engineer” describes the intended interaction pattern: asking questions, proposing a design, checking it, and revising it. It does not itself demonstrate equivalent professional judgment. That must be supported through competent proposals, constraints, tests, and accurate descriptions of the system's limits.

The existing architecture uses a React/React Three Fiber interface, FastAPI, LangGraph, SQLite, provider adapters, and a plugin system. JuPedSim provides crowd simulation; the project uses PedPy-related crowd analysis, Pynite for structural screening, and map and weather services for context. Local and hosted model providers share an adapter interface.

## 5. Existing feature inventory

The following summarizes the 25 existing feature areas documented in `plan.md`. “Existing” means code or repository documentation supports the capability; it is not a claim of independent runtime verification in this review.

| ID | Capability | What it provides |
| --- | --- | --- |
| F01 | Projects and versions | Save, restore, undo/redo, duplicate, and import/export projects and history. |
| F02 | Venue templates | Conference hall with two floors, school wing, festival field, and T-shaped alley. |
| F03 | Event Copilot | Sentence to brief, venue, layout, estimates, project, simulation, sweep, and prioritized review; workflow visualization. |
| F04 | Planning estimates and what-if lab | Capacity, exits, staff, first aid, toilets, fencing, budget, explained planning score, and interactive parameter changes. |
| F05 | Venue from a description | AI-generated specifications built and checked by a layout solver. |
| F06 | Venue from a real place | Map search and selection using available buildings, areas, paths, water, and entrances. |
| F07 | 3D editor and presentation | Dragging, drawing barriers/zones/exits, measurement, venue display, lighting, and camera tour. |
| F08 | Text edits | Natural-language commands converted into validated venue patches. |
| F09 | Geometry and rule checks | Layout validation and an example rules pack; applicability must be understood. |
| F10 | Instant estimate | Fast crowd-flow estimates and interactive exit blocking. |
| F11 | Simulation and replay | Quick/full JuPedSim runs, trajectories, density, hotspots, evacuation metrics, and exit flows. |
| F12 | Multiple floors | Simplified stair-queue connections between floors. |
| F13 | Scenario sweep | Six what-if branches and a Safety Officer review of the results. |
| F14 | Red Team Night | Incident-informed attacks, proposed repairs, simulation branches, iterative rounds, and final comparison. |
| F15 | Session visibility | Branch tree, scoreboard, activity feed, token usage, and configured inference-cost accounting. |
| F16 | Comparison and intervention timing | Time-based intervention experiments, split comparison, and marshal annotations. |
| F17 | Wind and stage screening | Forecast integration, simplified structural checks, and evacuation-start estimates under assumptions. |
| F18 | Ask the venue | Questions about results or hotspots with numerical consistency checks. |
| F19 | Reports and exports | Printable HTML/PDF reports, SVG evacuation maps, and JSON bundles. |
| F20 | Sample projects | Bundled demonstrations with saved sessions. |
| F21 | Importers | Structured DXF and JSON intake. |
| F22 | Providers and caching | Local/hosted model adapters, configured fallback, recording/replay, and local Docker simulation. |
| F23 | Extensibility | Plugins and feature flags for hazards, rules, operations, engines, agents, import/export, and other extension points. |
| F24 | Supporting interface | Settings, help, onboarding, themes, and translation infrastructure. |
| F25 | Diagnostics | Health checks and probes. |

The project already has a 3D editing foundation. The proposed collaborative experience primarily connects and strengthens existing capabilities, with additional object provenance, locks, constraints, and result invalidation.

## 6. Existing roadmap and deferred integrations

| ID | Planned work | Position in this proposal |
| --- | --- | --- |
| N01 | Live Nemotron on Nebius Token Factory | Deferred during current development; verify before submission claims. |
| N02 | Tavily Evidence Desk and pre-event brief | Deferred. Current incident records support development. |
| N03 | Local-rule research with checked quotations | Deferred. Source authenticity alone does not establish applicability. |
| N04 | Live Nebius sandbox branches | Deferred; local Docker remains the development execution path. |
| N05 | Multiple random seeds | Retained as bounded robustness evaluation. |
| N06 | Public demo deployment and controls | Retained for release preparation, including isolation, queues, limits, and cleanup. |
| N07 | Live Ops console | Later priority; proposed headcounts are manually entered, not automatic sensing. |
| N08 | Steward packs and Bangla translation | Begin with accurate English handover; expand after preservation checks work. |
| N09 | Share links and QR codes | Later priority following reliable report generation. |
| N10 | Validation against experiments | Retained with a narrow, reproducible study. |
| N11 | Judge landing and guided tour | Retained as part of onboarding and demonstration polish. |
| N12 | Repository and submission completion | Retained: license placement, CI, documentation, feedback, and submission materials. |
| N13 | Autopilot | Central workflow; extend the existing graph. |
| N14 | Three-screen interface and Expert view | Central design priority. |
| N15 | Unified “Ask or change anything” input | Connect conversation, edits, questions, what-if analysis, and navigation. |
| N16 | Usage records and model escalation | Retained, with precise cost boundaries and measured results. |
| N17 | Independent simulation export | Later priority for expert reproduction outside the application. |

These are roadmap items, not all mandatory competition requirements. Features should be prioritized by their contribution to a complete, credible demonstration.

## 7. Collaborative venue creation: conversation plus a focused 3D editor

### 7.1 Interaction model

The organizer and AI jointly build the venue:

1. The organizer describes the event and site.
2. AI extracts requirements and generates a visible draft.
3. Assumptions and missing information are highlighted on that draft.
4. The organizer corrects the model using text, dragging, object controls, and exact numeric inputs.
5. The system checks geometry, references, and constraints after each change.
6. The organizer locks confirmed features or marks changes as proposals.
7. The system evaluates the agreed model and permitted alternatives.
8. Further edits mark affected evidence stale and offer a rerun.

Example input: “A rectangular hall with the stage at the north end and two doors on the south wall.” The AI drafts that layout, labels assumed dimensions, and asks whether the two doors are available as exits during the event. The organizer adjusts their positions and enters measured widths.

The objective is a focused event-layout editor inspired by direct manipulation in modeling tools. General-purpose mesh modeling is unnecessary for the core task.

### 7.2 Proposed editing controls

| Control | Intended behavior |
| --- | --- |
| Drag an exit along a boundary | Correct the location while retaining a valid connection to walkable geometry. |
| Add/remove a door or gate | Correct an existing-site representation or create an explicitly proposed opening. |
| Edit width numerically | Record the supplied dimension and its provenance. |
| Move barriers and equipment | Explore permitted arrangements. |
| Draw audience zones | Define the modeled starting areas and attendance. |
| Lock an object | Prevent subsequent agent proposals from altering it without an explicit user change. |
| Mark fixed/movable | Distinguish structural features from temporary equipment. |
| Undo and compare versions | Preserve a reviewable history of user and AI edits. |
| Preview an AI edit | Show its consequences before the user applies it. |

Every visual edit must update the same geometry and properties consumed by the simulator. A decorative change to a 3D mesh is insufficient.

### 7.3 Existing versus proposed features

Adding a door to represent an overlooked existing opening is different from proposing construction of a new opening. Record that distinction explicitly. A proposed structural change cannot silently become an available exit in the current operational plan.

For new venue design, AI can explore layouts within represented constraints. For reconstruction of an existing venue, multiple plausible layouts may fit the description. A plausible model must not be presented as a measured reconstruction.

### 7.4 Asking useful questions

Repeated conversation can clarify requirements and contradictions, but cannot establish physical facts unknown to both parties. Ask the next consequential question rather than continuing indefinitely.

Use bounded sensitivity checks to identify which uncertainty can change the recommendation. For example: “The preferred option depends on the east gate being available; confirm access before choosing it.” Preserve unresolved information when the organizer cannot answer.

Use precise provenance labels: assumed, imported, organizer-confirmed, and measured with a supplied source/date. Even measured inputs retain their measurement limits.

## 8. Meaning of the six original concerns

| Concern | What it means | Effect of the proposed features | What would justify closing the gap |
| --- | --- | --- | --- |
| Scientific credibility | The model's results are limited by its physics, inputs, and assumptions. | Better editing improves input quality; it does not add missing physics. | Scoped validation and conclusions consistent with the tested model. |
| Feasibility of fixes | A simulated change may be physically or operationally unavailable. | Collaborative editing, existing/proposed labels, locks, and constraints directly help. | Both rules and AI obey constraints; selected actions are reviewed and implementable under stated conditions. |
| Source and explanation quality | A real number or quotation can still be used in the wrong context. | Structured metric references and provenance improve traceability. | Correct scenario, unit, version, comparison, and applicability checks for the claims made. |
| Agent contribution | Benefits attributed to AI need supporting evidence. | Conversational intake, modeling, edits, and orchestration already provide a credible AI role. | Demonstrated usefulness; fair baselines when claiming superior discovery or optimization. |
| Product complexity | Users may struggle to complete the central task through many modes and panels. | Guided conversation, focused editing, and a simple result screen can help. | Observed first-time users complete the task successfully. |
| Impact and cost claims | Specific statements about speed, spending, and usefulness require measurements. | New features create something worth measuring. | Recorded runs, explicit cost boundaries, and observed organizer use. |

Proposing a feature responds to a concern. Implementing and testing the feature can resolve it. Once resolved, it should no longer be described as missing. Permanent modeling limitations should remain documented as scope boundaries rather than treated as an endless feature checklist.

## 9. What “astonishingly better” should mean

A dramatic demonstration is desirable, but improvement must be defined before selection. Otherwise the system can appear to succeed by inventing capacity, assuming perfect compliance, selecting favorable scenarios, or moving crowd demand outside the modeled area.

A useful improvement has:

- Comparable before/after conditions and attendance demand.
- Changes permitted by the venue and resource constraints.
- Better results on declared metrics without an unacceptable regression elsewhere.
- A clear explanation of remaining failures and uncertainties.
- An actionable handover that preserves the selected plan.

Some venues will have little room for improvement. Others will have no acceptable option under the supplied constraints. The system must be able to report these outcomes. “Improved under completed tests” does not mean “safe under every possible condition.”

## 10. Static implementation findings and required foundation

These findings were identified by reading selected source paths. They are not a complete code audit or a claim of reproduced runtime failures.

| Finding | Source | Required response |
| --- | --- | --- |
| Model and standard fixes are mixed in a session. | `nebius/api/orchestrator/session.py::_fixes` | Preserve proposal origin and selected-action attribution. |
| Baseline protection uses instant estimates. | `session.py::_hurts_baseline` | Treat this as screening; require appropriate completed evidence for final acceptance. |
| Final confirmation focuses on a selected attack. | `session.py::_finish` | Evaluate combined fixes against a bounded predefined regression suite. |
| Failed/timed-out simulations can become estimate fallbacks. | `session.py::_sim` | Preserve both records and prevent fallback estimates from satisfying full-simulation confirmation. |
| Some report/countdown wording implies confirmation unconditionally. | `session.py::_countdown`; `nebius/plugins/export_html_report/__init__.py` | Derive labels from successful completion and evidence provenance. |
| Conflicting edits may be skipped after fixes were accepted. | `session.py::_apply_ops` | Validate/apply a coherent bundle and make conflicts explicit. |
| Applying a final plan saves venue geometry; measures remain separately in the session summary. | `session.py::apply_final` | Explicitly persist the complete active plan and verify save/reload/rerun behavior. |
| Numerical checking uses allowed-value membership and exempts small integers. | `nebius/api/agents/numbers.py` | Add typed references to metrics, units, scenarios, and versions for measured claims. |
| One-way control can hold incoming people outside the modeled area. | `nebius/sim/plugins/events.py::one_way` | Account for external demand; model the receiving area or identify it as unassessed. |
| Saved calibration compares estimates with simulations. | `nebius/api/data/calibration.json` | Do not present it as independent comparison with real observations. |

Foundation requirements:

1. Separate execution status from evaluation status. A session can finish while its result remains inconclusive.
2. Distinguish estimates, partial simulations, completed simulations, failures, and unknown outcomes throughout the UI and exports.
3. Store geometry, operational measures, constraints, inputs, engine/settings version, and seeds with the evaluated plan.
4. Include all behavior-affecting inputs in cache identity.
5. Invalidate relevant evidence after a material edit.
6. Preserve remaining people and incomplete clearance alongside time for 95% to exit. Do not describe that percentile as everyone evacuated.
7. Never treat a failed, skipped, or timed-out run as a pass or zero risk.

## 11. Six connected development capabilities

### A. Feasible planning constraints

Declare fixed structures, allowed openings, movable equipment, staff inventory, work restrictions, and relevant approvals. Enforce them in shared code used by AI and standard proposals. Include explicit actions for opening an available existing gate rather than relying on creation of a new exit.

Actions should declare resource requirements, active time intervals, dependencies, response assumptions, and supplied cost/setup information. Prevent simultaneous assignments that exceed staff or equipment availability. Unknown quantities remain marked as unknown.

Distinguish planned dispersal from emergency evacuation. Do not transfer measures such as delayed release into a hazard scenario without an appropriate reviewed policy.

**Acceptance:** neither proposal source alters locked structures; unavailable gates cannot be treated as ready; staff cannot be double-counted; unresolved dependencies remain visible.

### B. Tested plan alternatives

Offer a small number of distinct feasible alternatives with a clear comparison against the original. Use compatible scenario definitions, demand, settings, and paired seeds. Check the combined action bundle, not only individual actions.

Use explicit thresholds per important metric. A weighted ranking score must not hide a trapped group or another unacceptable regression. Include baseline conditions and a bounded regression suite beyond the motivating attack.

**Acceptance:** a fixture that improves one scenario but introduces a disallowed regression is rejected. Unknown runs remain unknown. External crowd demand is accounted for or clearly unassessed.

### C. Consequential assumptions and clarification

Attach provenance to gate dimensions, access, staffing, attendance, intervention timing, and assumed compliance. Run a limited sensitivity screen to prioritize questions. Confirm consequential findings with the appropriate simulation before describing them as measured effects.

**Acceptance:** changing a relevant assumption can change the preferred option, and the interface identifies that dependency without inventing statistical confidence.

### D. A simple collaborative journey

Extend the existing Copilot graph and planned Autopilot. Combine conversational intake, the focused editor, a short input review, progress, and final selection. Preserve expert tools through progressive disclosure.

**Acceptance:** an unfamiliar organizer completes a template-based task, corrects an AI assumption, selects a tested option, and exports the plan without needing expert panels.

### E. Exact handover with inspectable evidence

Export the chosen geometry and operations with gate actions, staff posts, timing, map, dependencies, and assumptions. Numerical claims reference compatible run data and calculations. Separate computed observations from AI interpretations of causes.

Begin with accurate English instructions using the existing report infrastructure. Add Bangla steward cards after numbers, names, actions, and geometry survive translation/export checks. User approval selects a plan; it does not certify safety.

**Acceptance:** save/reload/export/rerun preserve operational measures; every measured comparison has traceable evidence; outdated and incomplete results retain their labels.

### F. Reproducible evaluation and usage records

Keep most evaluation tooling outside the organizer's main flow. Produce narrowly scoped physical validation, robustness results, appropriate agent comparisons, observed user exercises, and measured usage.

**Acceptance:** results are reproducible from recorded inputs; unsuccessful outcomes are included; claims match what was actually measured.

## 12. Validation, agent contribution, and organizer evaluation

### 12.1 Physical validation versus robustness

| Evaluation | Question answered |
| --- | --- |
| Published experimental comparison | How closely does this simulator configuration reproduce selected observed pedestrian behavior? |
| Repeated random seeds | How much do results vary under the modeled randomness? |
| Sensitivity to assumptions | How do different attendance, access, response, or movement assumptions change the outcome? |
| Withheld scenario evaluation | Do chosen fixes retain value on cases not used during selection? |

Reproduce a narrow bottleneck experiment using compatible geometry, population, measurement methods, and the actual modified simulator used by Showtime. Separate calibration cases from evaluation cases. Publish error and scope even when results miss an initial target.

A fraction such as “18 of 20 tested scenarios passed” is not a probability that an event will be safe. Report the scenario definitions, completed/failed/skipped counts, and remaining failures.

Two plans over three scenarios and three seeds already require eighteen full runs per venue. Measure runtime before expanding. Limit the initial study transparently rather than replacing incomplete runs with favorable assumptions.

### 12.2 AI value

There is no feature-count or model-call quota that establishes meaningful AI use. The project already uses AI substantially. Demonstrate competence in interpreting messy requirements, building a correctable model, generating useful proposals, and reducing manual effort.

If claiming better failure discovery or optimization, compare rules-only, model-only, and hybrid proposal generation under equal simulation budgets and constraints. Track origin, retries, model usage, feasible proposals, distinct weaknesses found, regressions, and final results. Freeze withheld evaluation cases before running comparisons and keep them out of selection.

If standard rules perform as well, report it. Conversational intake and understandable orchestration may still provide valuable assistance.

### 12.3 Organizer exercises

Observe a few organizers performing concrete planning tasks on real or carefully reconstructed venues. Record assumptions corrected, suggestions accepted/rejected, task completion, time, confusion, and whether the output changed a planning decision.

These exercises can demonstrate usability and usefulness. They do not establish injury prevention or comprehensive real-world safety. A separate survey product is unnecessary.

### 12.4 Cost and performance

Record elapsed time, model requests, tokens, retries, screened/simulated scenario counts, cache hits, and measured simulation usage. Separate fresh and cached runs.

Show API inference charges, search charges where applicable, and the boundary of the displayed total. Local compute time is not automatically a monetary cost measurement. A free model endpoint can support “$0 API inference charge,” not “the whole system costs nothing.”

## 13. Interface and implementation order

The default product uses three screens:

1. **Describe:** event brief, targeted conversation, draft inspection, and critical corrections.
2. **AI at work:** understandable progress, current simulations, proposals, usage, cancellation, and partial-result states.
3. **Your plan:** main finding, tested alternatives, before/after replay, unresolved conditions, selection, and report.

Detailed agent graphs, advanced geometry tools, exhaustive metrics, and technical evaluation data remain accessible in Expert view or detail panels. Loading, error, empty, partial, and offline states need coherent behavior. Keyboard access and useful mobile views are part of completion.

| Stage | Work | Completion gate |
| --- | --- | --- |
| 1 | Result provenance, complete plan persistence, constraints | Failures cannot become confirmed passes; geometry and operations survive save/reload. |
| 2 | One collaborative template journey through Autopilot | User corrects an assumption, obtains a feasible alternative, reviews a completed comparison, and exports the exact plan. |
| 3 | Combined-fix regression checks and bounded sensitivity | Important regressions and consequential assumptions are exposed. |
| 4 | Validation, appropriate baselines, user exercises, usage | Inspectable evidence supports the claims made. |
| 5 | Broader intake, interface polish, release preparation | Public experience and submission materials match demonstrated functionality. |

These are dependency gates, not promises about implementation dates. Keep time for eventual live Nebius verification and release reliability.

Later priorities include the full Live Ops console, share links, independent simulation export, broader translation, and live evidence research. New physics engines, automatic sensors, and broad administrative portals were not established as necessary for the core submission.

Use fake-provider fixtures for ordinary development checks where appropriate. Final model-behavior claims require live runs on the provider named in the claim.

## 14. Development now: OpenRouter and local Docker

OpenRouter support already exists through the generic OpenAI-compatible adapter, named `openai` in configuration. The default `.env.example` selects a local model; OpenRouter is not enabled automatically.

The machine inspected during the discussion was an Apple Silicon Mac with Docker installed and its daemon stopped. This is a recorded observation, not a claim about its current state. The API Dockerfile downloads an x86 Docker executable, and the simulation build target uses `linux/amd64`, so the discussed Compose route uses emulation. Startup was not executed during the review.

### 14.1 Configure

Start Docker Desktop and wait for `docker info` to succeed. Then:

```bash
cd /Users/ridhwanasif/Downloads/Nebius/Showtime/nebius
cp -n .env.example .env
```

Edit the existing keys in `.env`, adding missing keys:

```dotenv
LLM_PROVIDER=openai
OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPAT_API_KEY=YOUR_OPENROUTER_API_KEY
OPENAI_COMPAT_LABEL=OPENROUTER

MODEL_FAST=nvidia/nemotron-3-super-120b-a12b:free
MODEL_LONG=nvidia/nemotron-3-super-120b-a12b:free
MODEL_MAIN=nvidia/nemotron-3-super-120b-a12b:free
MODEL_JUDGE=nvidia/nemotron-3-super-120b-a12b:free

LLM_SUPPORTS_JSON_SCHEMA=false
LLM_EXTRA_BODY='{"reasoning":{"enabled":false}}'
LLM_FALLBACK=none
LLM_CACHE_MODE=record_replay

SANDBOX_PROVIDER=docker
SANDBOX_MAX_PARALLEL=1
TAVILY_API_KEY=
NEBIUS_API_KEY=
OFFLINE=false
```

The model identifier was documented in the repository's OpenRouter testing and checked against OpenRouter during the discussion. Availability and free quotas can change; check the linked provider pages when configuring. Keep credentials in the ignored local `.env`.

`LLM_FALLBACK=none` avoids attempts to contact a local GPU model. `OFFLINE=false` retains map/weather access. Without Tavily, incident-backed scenarios can use the bundled curated records; the complete incident dataset is optional for initial startup.

### 14.2 Build and run

```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
mkdir -p runs cache state data
make build-sim
docker compose up -d --build
```

Open <http://localhost:5173>. API documentation is at <http://localhost:8000/api/docs>.

This route installs application dependencies inside Docker. `make setup` also downloads a local model and Linux CUDA server; those steps are unnecessary for this OpenRouter configuration. Native development scripts also contain Linux assumptions and should be adapted before relying on them on macOS.

Diagnostics:

```bash
docker compose ps
docker compose logs --tail=100 api web
```

After `.env` changes:

```bash
docker compose up -d --force-recreate api
```

Stop:

```bash
docker compose down
```

Start with a saved sample, then a small template and a short session: one round, two attacks, one fix per attack. A session includes multiple model requests and possible repairs. The discussion found a published free allowance of 50 requests/day for a free account; treat that as a dated observation and verify the account's current limits. Caching reduces repeated work but does not turn cached calls into fresh live evidence.

## 15. Competition fit and submission preparation

Best Apps and Agents is the recommended track because the main product is a practical agent workflow for organizers. A crowd simulation alone is not a reason to force a Physical AI positioning.

| Judging dimension supplied in the hackathon brief | Showtime's evidence |
| --- | --- |
| Technological implementation | Working orchestration, constrained edits, reproducible simulation, reliable comparisons, and eventual live Nebius model use. |
| Design | A coherent collaborative journey from description to a selected plan. |
| Potential impact | Specific organizer tasks and observed usefulness. |
| Quality of idea | Incident-informed stress tests and feasible repairs, with demonstrated understanding of the problem. |

The official judging update emphasizes autonomous tool workflows and equally weighted criteria. Increasing technical breadth at the expense of usability or evidence would weaken that balance.

Submission preparation discussed includes the working project, chosen track, description, demo URL, public short YouTube demonstration, public licensed repository, setup instructions, accurate technology description, tool feedback, and an explanation of changes if the project predates the submission period. Record event attendance only if applicable to the city award.

At the reviewed checkout, the license was inside `nebius/`; the repository root needed detectable license placement. Nebius live use, final hosted demo, and final video were not established. These are outstanding items, not completed claims.

The rules reviewed permit a runtime Token Factory inference call to satisfy the Nebius execution requirement; the whole application need not be hosted on Nebius. Tavily bonus eligibility requires functional runtime use. The published schedule reviewed had an October 30, 2026 submission deadline and December judging; plan project access through the required judging period. Recheck the official rules before release.

Development on OpenRouter is consistent with the present preference. It does not by itself complete the final competition platform requirement.

## 16. Demonstration and evidence story

Use a measured single-level venue as the principal case, with fixed infrastructure, existing gates, movable equipment, and a stated staffing limit. This reduces reliance on the current simplified stair and wind models for the central accuracy claim.

Example narrative:

> “The event is tonight. Construction is unavailable, the stage must stay, and we have six stewards. We describe the venue, correct the AI's draft, lock the existing structures, test a blocked-gate scenario, and compare feasible responses. Here is the measured result, one unresolved dependency, and the exact plan we selected.”

Suggested sequence for a video under three minutes:

1. State the organizer's task and constraints.
2. Show the AI-generated venue and one meaningful user correction.
3. Show a simulated weakness.
4. Show a feasible proposed change and completed comparison.
5. Open the evidence for one result or consequential assumption.
6. Export the selected actions and show measured usage and actual provider involvement.

The saved red-team screenshot previously discussed displays 95% evacuation changing from 5 min 11 s to 2 min 50 s and time above its configured danger threshold changing from 39 s to zero. Those are recorded demonstration values, not independently reproduced results. Replace or substantiate them with reproducible runs from the submitted version before using them as evidence.

The demonstration should show the actual outcome, including remaining failures or insufficient evidence. Distinguish recorded examples from live operation.

## 17. Definition of completion for the core proposal

- An organizer can describe, inspect, correct, and lock a venue through the simple workflow.
- Existing, proposed, assumed, imported, and confirmed/measured inputs are distinguishable.
- Both AI and standard proposals obey shared geometry and resource constraints.
- The evaluated plan includes its operational measures and survives save/reload/export.
- Final comparisons use compatible conditions and evaluate the combined changes.
- Failed, partial, skipped, and fallback results retain accurate status everywhere.
- Material edits invalidate affected evidence.
- Important numerical claims link to the correct results, units, and versions.
- A scoped validation study and declared robustness suite have inspectable results.
- AI benefit is demonstrated through useful behavior; superiority claims receive appropriate comparisons.
- Organizer exercises and runtime/cost measurements support the impact and efficiency claims made.
- The eventual submitted build demonstrates the required platform use and accessible deliverables.

The proposal retains the core idea. Its competitive case rests on feasible decisions, trustworthy evidence, and a clear collaborative experience. Adding features alone does not establish any of those outcomes.

## 18. References and related documents

### Repository

- [Full implementation roadmap](plan.md)
- [Reviewed product priorities](PRODUCT_PRIORITIES.md)
- [Application README](../nebius/README.md)
- [Architecture](../nebius/docs/ARCHITECTURE.md)
- [Assumptions and modeling limits](../nebius/docs/ASSUMPTIONS.md)
- [Handoff and reported status](../nebius/docs/HANDOFF.md)
- [Nebius integration status](../nebius/docs/NEBIUS_SWITCH.md)
- [Red-team demonstration screenshot](../nebius/docs/screenshots/redteam.png)

### External sources checked during the discussion

- [Hackathon overview](https://nebiusglobalaihackathon.devpost.com/)
- [Official rules](https://nebiusglobalaihackathon.devpost.com/rules)
- [Official judging update](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works)
- [OpenRouter key settings](https://openrouter.ai/settings/keys)
- [OpenRouter Nemotron 3 Super free model](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free)
- [OpenRouter pricing](https://openrouter.ai/pricing/)
- [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits)

This file records the discussion and its corrected conclusions. It does not claim that the proposed changes, new evaluations, platform integrations, or final submission have been completed.
