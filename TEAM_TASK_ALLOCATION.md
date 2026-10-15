# Showtime — remaining work allocation for three people

Prepared: 11 October 2026.

## 1. Allocation and scope

Person 1 has already built the current project alone. Their remaining workload should be smaller. Persons 2 and 3 take equal estimated effort, including implementation, verification, and integration.

| Person | Primary role | Core effort points | Share |
| --- | --- | ---: | ---: |
| Person 1 | Product decisions, organizer evaluation, documentation, submission | 20 | 20% |
| Person 2 | Scene geometry, plan correctness, simulation, deployment | 40 | 40% |
| Person 3 | Guided interface, agent workflow, model integration, explanations | 40 | 40% |
| **Total** | | **100** | **100%** |

Points represent relative effort, not hours or a delivery promise. They include each task's checks and fixes. Estimate again after the first working slice; redistribute whole tasks or clearly defined subtasks if actual effort diverges. Equal task counts would not ensure equal work.

Use Person 1/2/3 as placeholders for the actual team members. Roles assume Person 2 is comfortable with Python/backend work and Person 3 with React and Python agent code.

This allocation follows [the revised proposal](revised_proposal.md) and [reviewed product priorities](PRODUCT_PRIORITIES.md). The older [implementation roadmap](plan.md) provides supporting detail. The revised scope and the user's current preference take precedence: **develop with OpenRouter and local Docker first; implement Nebius/Nemotron and Tavily later.** Required Nebius inference remains part of final submission preparation. Tavily and live cloud sandbox branching are optional extensions unless the team chooses to claim them.

## 2. Starting point: extend the existing application

Existing foundations include project/version management, templates, conversational venue creation, a 3D editor, geometry checks, crowd simulations, replay, scenario sweeps, red/blue agent sessions, weather screening, reports, imports, and sample projects. These should be extended rather than assigned as entirely new builds.

The M1 startup work already provides local launch commands, Docker architecture configuration, and sample projects. The recorded verification includes startup, manual scene editing and persistence, a real 20-person simulation, and 30 selected regression tests. See [M1 test setup](nebius/docs/M1_TEST_SETUP.md); commands use the `m1-test-*` prefix. This does not establish completion of the proposed planning workflow or live AI/provider integration. Keep this local test profile working during handoff.

The principal remaining work is trustworthy plan state and evidence, feasible recommendations, a simpler complete journey, and demonstrated usefulness. Additional panels or models alone do not resolve those gaps.

## 3. Person 1 — smaller, bounded responsibility

| ID | Task | Points | Deliverable and acceptance |
| --- | --- | ---: | --- |
| P1-01 | Initial handoff and demonstration brief | 2 | Two bounded walkthroughs of the current app and architecture. Choose one single-level venue, organizer problem, staffing inventory, allowed changes, and demo story. Record decisions so the others can work independently. |
| P1-02 | Organizer exercises and product acceptance | 6 | Recruit a small declared group of organizers or representative users; observe the complete planning task. Record task time, corrections, confusion, accepted/rejected suggestions, and failures. Prepare a prioritized issue list and review one correction round. Persons 2/3 implement fixes in their areas. |
| P1-03 | Repository and submission documentation | 5 | Update the root README, setup links, architecture summary, modeling limits, provider-use explanation, feedback, and pre-existing-work/change statement where applicable. Confirm an appropriate open source license is visible at repository root. Describe only demonstrated capabilities. |
| P1-04 | Demo script and public video | 5 | Assemble a video of at most three minutes using verified runs supplied by Persons 2/3. Show venue correction, a supported weakness, a feasible change, before/after evidence, a remaining condition, and the exact handover. Identify recordings and cached runs accurately. |
| P1-05 | Submission package and final access check | 2 | Prepare track/category, description, repository URL, demo URL, public video URL, and tool feedback. Check the official requirements and access window before submission; organize the final submission. |
| **Total** | | **20** | |

**Workload boundary:** Person 1 is not the default engineer, PR reviewer, deployment troubleshooter, or integration owner. Questions should be consolidated into the initial walkthroughs or a short scheduled decision check. New engineering work assigned to Person 1 must replace an equivalent existing task rather than accumulate.

## 4. Person 2 — scene, evidence, simulation, and release backend

| ID | Task | Points | Deliverable and acceptance |
| --- | --- | ---: | --- |
| P2-01 | Canonical scene and computed spatial facts | 8 | Extend the shared JSON contract with relevant geometry, stable object IDs, units, provenance, and versioning. Compute connectivity, reachable exits, route lengths, and relevant clearances through geometry tools. Editor, agent tools, and simulator use the same scene version. Add known spatial fixtures, including blocked routes and disconnected areas. |
| P2-02 | Constraints, atomic edits, and complete plan persistence | 8 | Enforce locks, fixed/movable status, existing/proposed gates, access, staffing intervals, equipment, approvals, and action dependencies for both rules and AI. Validate a whole fix bundle before acceptance. Save geometry plus operational measures; reload and rerun the same plan. Relevant changes invalidate affected evidence. |
| P2-03 | Typed simulation evidence and metric references | 6 | Separate execution status from evaluation status. Preserve failed runs and linked estimate fallbacks as distinct records. Implement run/metric/unit/scenario/version references and complete cache identities. Unknown, partial, cancelled, or failed results cannot satisfy completed-simulation gates. Expose people remaining alongside p95 clearance time. |
| P2-04 | Comparable experiments and scoped physical validation | 8 | Provide bounded paired-seed runs, predefined regression scenarios, combined-fix evaluation, and operational sensitivity support. Preserve external demand instead of hiding people held outside the scene. Build a reproducible narrow validation case against suitable independent observations or a published experiment; report error and scope. If suitable evidence is unavailable, record that gap rather than substituting simulator-to-simulator calibration. |
| P2-05 | Backend release and reproducible execution | 6 | Own deployment configuration, CI backend gates, job limits, queueing, project isolation, cancellation, artifact cleanup, and backend health diagnostics. Keep local Docker working. Supply a clean-checkout launch path and public backend/API configuration for Person 3's frontend. Implement complete selected-plan JSON export/import. |
| P2-06 | Backend integration and failure checks | 4 | Own final backend integration. Verify stale evidence, timeout fallback, conflicting bundles, resource over-allocation, external queues, save/reload, and combined-fix regressions. Review Person 3's agent/API integration changes and fix backend issues discovered by organizer exercises. |
| **Total** | | **40** | |

Person 2 owns the canonical scene/plan contract and simulation result contract. This includes adapters needed to preserve current templates and importers. General mesh reconstruction and new simulator physics are outside the core allocation.

## 5. Person 3 — product journey, agents, and model explanations

| ID | Task | Points | Deliverable and acceptance |
| --- | --- | ---: | --- |
| P3-01 | Three-screen journey and collaborative editor | 9 | Deliver Describe → AI at work → Your plan, retaining the existing studio as Expert view. Connect drag/numeric door and barrier edits to the shared scene, display provenance and locks, distinguish existing openings from proposed construction, preview AI patches, and show stale evidence. An unfamiliar user can finish a template-based journey without expert panels. |
| P3-02 | Autopilot, unified input, and grounded scene tools | 8 | Extend the existing graph and “ask/change” input for drafting, consequential clarification, inspection, edits, scenario execution, and result explanation. Call Person 2's geometry tools rather than infer numerical geometry from prose alone. Bound questions, model calls, retries, and simulations. Preserve unresolved assumptions and proposal origin. |
| P3-03 | Feasible alternatives and selection workflow | 6 | Generate a few distinct candidates within enforced constraints, request Person 2's experiment API, compare exact applied bundles, and display regression failures and unresolved dependencies. User selection persists the chosen plan. Support no feasible option and insufficient evidence outcomes. Own the orchestrator integration; Person 2 owns simulation scheduling and evidence production. |
| P3-04 | Model routing and eventual Nebius inference | 4 | Keep the immediate OpenRouter path configurable and usable with recorded/mock responses while no key is available. Later configure and verify an available NVIDIA open model on the required Nebius runtime, tool/structured-output compatibility, model escalation where justified, and actual call records. Recheck model availability at implementation time; do not assume an Ultra endpoint exists. |
| P3-05 | Evidence explanations and environmental context | 4 | Replace number-membership reassurance with typed metric-backed claims from Person 2's results. Distinguish computed findings from model interpretations. Display source/time/location and limits for weather or wind inputs; document which scenarios actually consume them. Label planning mode clearly. Basic source records are included; broad Tavily/rule research is deferred. |
| P3-06 | Your plan, replay, and exact English handover | 5 | Build before/after selection and replay, evidence drilldown, remaining conditions, and a concise English map/checklist with gate actions, staffing, timing, and dependencies. Render from the selected persisted plan and typed results. Reports preserve stale/unknown labels and cannot imply unconditional safety. Use existing export infrastructure. |
| P3-07 | Agent evaluation, usage, and frontend release | 4 | Run a bounded rules-only/model-only/hybrid comparison using equal constraints and simulation budgets. Record spatial errors, feasible proposals, regressions, latency, retries, cache use, and inference charges with explicit compute/hosting exclusions where unmeasured. Own frontend deployment, onboarding/judge tour, UI accessibility checks, and workflow fixes from user exercises. |
| **Total** | | **40** | |

Person 3 owns frontend and orchestration integration. They review Person 2's contract changes for consumer compatibility and maintain the end-to-end demonstration flow. Final model performance claims require live runs on the claimed model/provider; saved responses are development support.

## 6. Shared contracts and handoffs

Agree these before implementing dependent components. Extend existing schemas and modules where practical.

| Contract | Owner | Required consumer / handoff |
| --- | --- | --- |
| Scene and plan snapshot | Person 2 | Person 3 receives IDs, units, geometry, provenance, operations, constraints, version/hash, and migration examples. |
| Proposed edit bundle | Person 2 defines validation; Person 3 produces proposals | Exact operations, source attribution, dependencies, explicit conflicts, and applied bundle identity. All proposal sources pass the same validator. |
| Spatial inspection tools | Person 2 | Person 3 receives documented calls and fixtures for reachability, clearances, routes, and permitted changes. |
| Experiment request/result | Person 2 | Person 3 supplies candidates and consumes baseline/scenario/seed/settings identity, status, artifact references, metrics, and acceptance decisions. |
| Selected plan and handover | Person 2 persists/exports data; Person 3 renders | The UI, downloaded report, saved plan, and rerun describe the same geometry and operations. |
| Demo evidence bundle | Persons 2/3 supply their own verified outputs | Person 1 receives reproducible projects, completed run IDs, provider records, measured usage, and limitations for the video and documentation. |

Person 2 reviews backend correctness; Person 3 reviews workflow and consumer compatibility. Each person tests their own changes and responds to feedback. Avoid requiring Person 1 to approve every merge or understand every implementation detail.

## 7. Delivery order and dependencies

| Stage | Person 1 | Person 2 | Person 3 | Exit condition |
| --- | --- | --- | --- | --- |
| 1. Handoff and trustworthy contracts | P1-01 | Start P2-01/02/03 | Start P3-01 with contract fixtures | Versioned plans, constraints, and typed status work; failure cannot become a pass. |
| 2. One complete local journey | Prepare organizer task | Finish persistence and initial experiment/export path | Connect P3-01/02/03/05/06 using OpenRouter-compatible fixtures | Template → correction → scenario → feasible option → completed rerun → exact report. No key needed for recorded/mock development. |
| 3. Evidence and usefulness | P1-02; draft P1-03 | P2-04 and failure cases | P3-07 baseline study and measured scene-tool behavior | Comparable tests, explicit unknowns, user observations, and bounded measured claims. |
| 4. Required model and release integration | Finish P1-03; assemble P1-04 | P2-05/06 | Live portion of P3-04; frontend release | Actual required Nebius/NVIDIA inference, public access, clean setup, and verified demo evidence. |
| 5. Final submission | P1-04/05 | Supply artifacts and resolve backend blockers | Supply provider evidence and resolve frontend/agent blockers | Public repository, license, setup, working demo, video, description, and feedback checked. |

These are dependency gates, not promised dates. Confirm required provider access early enough to expose account blockers, without starting the deferred implementation now. A single usable slice comes before expanding the number of scenarios, venue types, or models.

### 7.1 How to read dependencies

**Yes, the work is dependent.** Person 2 supplies scene, constraint, persistence, and experiment interfaces that Person 3 integrates into the product. Person 1's final evaluation and submission depend on their working outputs. However, nobody needs to wait for another person to finish their entire allocation before starting.

- **Can start now:** planning, scaffolding, fixtures, isolated implementation, recruitment, or documentation drafts can proceed against the existing app.
- **Needs a checkpoint:** integration waits for a specific working interface or artifact, not necessarily completion of the whole upstream task.
- **Needs completion:** final acceptance, measured claims, and submission wait for actual verified outputs. Mock responses do not satisfy these gates.

The checkpoints below divide the larger tasks into useful handoffs. They are included in the existing points, not additional assignments.

### 7.2 Exact handoff checkpoints

| Checkpoint | Produced by | What must exist first | Ready when / what it unblocks |
| --- | --- | --- | --- |
| C0 — Demo brief | Person 1, P1-01 | Existing app walkthrough | One venue, demand, permitted changes, staffing, and target user task are recorded. Unblocks shared acceptance fixtures and the demo-specific implementation. |
| C1 — Scene contract | Person 2, first part of P2-01 | Existing scene/schema review; C0 for the demo fixture | Schema, stable IDs, units, provenance, version/hash, and representative JSON fixtures are agreed with Person 3. Unblocks scene-aware frontend and backend work in parallel. |
| C2 — Validated saved plan | Person 2, P2-02 | C1 | Constraint validation, atomic bundle application, complete plan save/reload, and invalidation behavior work. Unblocks real edit application and selected-plan persistence. |
| C3 — Spatial inspection tools | Person 2, remaining spatial part of P2-01 | C1 | Reachability/clearance/route tools return checked, version-matched results. Unblocks grounded agent inspection. C2 is not required to build these read-only tools. |
| C4 — Typed run evidence | Person 2, P2-03 | C1; C2 for operational-plan identity and invalidation integration | Status, basis, metric references, cache identity, and failed/fallback records work. Unblocks truthful result displays and comparison consumption. |
| C5 — Local experiment and export interfaces | Person 2, initial portions of P2-04/05 | C2 + C4 | A baseline and candidate can run under compatible settings; exact bundle IDs, artifacts, results, and plan export are returned. Unblocks an initial real before/after journey. The full multi-seed study and public deployment can follow. |
| C6 — Complete local journey | Person 3, integrated P3-01/02/03/05/06; Person 2 supplies C2–C5 | C0 + C2 + C3 + C4 + C5; OpenRouter-compatible adapter from P3-04 | A user can correct a template, propose/select a constrained alternative, inspect a completed rerun, and export the saved plan. Recorded/mock AI may support an explicitly labeled development trial; actual model-quality claims require live calls. Unblocks organizer exercises. |
| C7 — Credible comparison evidence | Person 2, remaining P2-04; Person 3, evaluation part of P3-07 | C3 + C4 + C5; candidate workflow from P3-02/03; live calls on any model whose performance is reported | Paired seeds/regressions, sensitivity, baseline comparisons, validation scope, and usage records are available. Unblocks measured benefit claims and the final demo evidence bundle. |
| U1 — Initial organizer findings | Person 1, initial observation part of P1-02 | C6 + initial backend failure checks from P2-06 | Task observations and a prioritized issue list are supplied to Persons 2/3. Unblocks their bounded correction round; recruiting participants can happen earlier. |
| U2 — Correction-round acceptance | Person 1, remaining P1-02 | U1 + relevant fixes verified by Persons 2/3 | One review of corrected workflow issues is recorded. Unblocks final usability claims and final documentation. |
| C8 — Verified public release | Person 2, P2-05/06; Person 3, live part of P3-04 and release part of P3-07 | C6 + actual required Nebius/NVIDIA inference + backend/frontend deployment controls + U1 fixes and U2 acceptance | Public access, clean setup, job limits/isolation, integration checks, and a current provider-backed demonstration work. C7 additionally supplies evidence for claims of improvement; publishing a test deployment need not wait for the full study. |

C7 and U1/U2 can proceed in parallel after C6. Start release scaffolding early, then verify C8 against the corrected version. These checkpoints avoid making organizer feedback depend on a finished release that itself needs organizer feedback.

### 7.3 Prerequisites for every core task

| Task | Work that can start before prerequisites finish | Required before integration or completion |
| --- | --- | --- |
| P1-01 | Start immediately. | Existing code and sample projects available; no new task blocks it. |
| P1-02 | Recruit users and prepare observation notes after C0. | Initial exercises need C6 and initial P2-06 failure checks. Final acceptance needs U1 findings addressed by the responsible engineers, then U2. |
| P1-03 | README outline, license placement, existing setup instructions, and change-history draft can start now. | Final feature, evaluation, deployment, and provider claims need C7, U2, and C8 evidence. |
| P1-04 | Script/storyboard can start after C0; collect footage as features become usable. | Final public video needs C7 evidence, C8's verified version/provider records, and finalized factual claims from P1-03. Re-record any affected segment after a material change. |
| P1-05 | Check official requirements and prepare submission fields early. | Final submission needs P1-02/03/04 complete, C7/C8, license/public repository/setup, and confirmed demo/video access. |
| P2-01 | Inspect existing schemas and prototype geometry tools now. | Demo fixtures need C0. Publish C1 before dependent schema integration; complete the task with C3 and compatible simulator/editor adapters. |
| P2-02 | Prototype validators/storage against C1 fixtures while geometry tools are built. | C1 is required before real plan integration. Finish constraint/persistence/invalidation handoff C2; no need to wait for all of P2-01's spatial tools. |
| P2-03 | Design status/metric types and failed-run fixtures alongside P2-02 after C1. | C2 is required to finish cache/operational identity and evidence invalidation. Complete C4 before dependent comparison/report acceptance. |
| P2-04 | Select an independent validation example and define regression cases after C0; freeze evaluation cases before model selection. | Experiment integration needs C2 + C4. Deliver C5 first, then the bounded paired-seed/sensitivity/validation outputs for C7. Agent benchmarking additionally needs Person 3's candidate workflow. |
| P2-05 | CI, Docker/deployment scaffolding, job controls, and access checks can start now. | Full plan export needs C2 + C4. Experiment cleanup/limits integrate with C5. Public release verification needs the integrated C6 application, frontend release, and actual provider calls from P3-04. |
| P2-06 | Build failure fixtures and review changes as C2/C4 become available. | Initial checks of the C6 slice precede U1. Final integration checks need the expanded P2-04/05 outputs, Person 3's integrated workflow, and backend corrections from U1. Do not wait for U2 before implementing those corrections. |
| P3-01 | Screen layout, navigation, and editor UI can start with existing components and C1 fixtures. | Real edits/locks/save require C2; stale/evidence labels require C4. Complete journey acceptance also needs integrated P3-02/03/05/06 at C6. |
| P3-02 | Intent routing, graph scaffolding, question policy, and mock tools can start after C0/C1. | Grounded inspection requires C3; applied edits require C2; real run interpretation requires C4/C5 and P3-04's local adapter. Full comparison connects to P3-03. |
| P3-03 | Candidate schemas, comparison layout, and no-feasible-option fixtures can start after C1. | Real constrained candidates require C2 and P3-02; completed comparison requires C4/C5. Final regression-based selection requires the remaining P2-04 evidence in C7. |
| P3-04 | Local OpenRouter adapter/configuration and mock responses can start immediately. | Tool compatibility needs the C3 interfaces used by P3-02. Live Nebius implementation remains deferred until the integration stage and needs account credentials/access plus the working local flow. Verify actual calls before C8 and any claimed Nemotron measurements. |
| P3-05 | Environmental provenance labels, planning-mode text, and explanation templates can start now. | Metric-backed explanations require C4; before/after explanations require C5 and P3-03. Validate displayed claims against actual results before C6/C7 acceptance. |
| P3-06 | Report/replay layouts and English checklist structure can start with fixtures. | Exact handover requires C2 and export from P2-05; metric/replay links require C4/C5; selection must use P3-03's persisted plan. Integration is part of C6. |
| P3-07 | Instrumentation, benchmark design, accessibility, landing page, and frontend deployment scaffolding can start early. | Actual baseline measurements require P3-02/03, C3/C4/C5, and the declared P2-04 suite. Release needs P2-05's backend, C6, live P3-04 calls, and U1 fixes. Claims about the final model must be rerun on that model, not inferred from OpenRouter results. |

Tasks such as P3-01/02/03/06 are integrated together to deliver C6; their whole-task completion is not a prerequisite for starting each other. Likewise, P2-06 and P3-07 are ongoing verification/release responsibilities, not single tasks that must finish before the first organizer trial.

### 7.4 What each person should do first

1. **Person 1:** deliver C0 through P1-01, then draft documentation and recruit users. Wait for C6 to run the full organizer exercise.
2. **Person 2:** publish C1 first. Implement C2 and C3, with status schema work in parallel; then finish C4 and deliver C5. Expand experiment evidence and deployment afterward.
3. **Person 3:** begin screen scaffolding and the local provider adapter immediately. Use C1 fixtures while waiting for C2/C3/C4/C5, replace each mock with its real interface as it arrives, then deliver C6. Expand evaluation and perform the deferred live provider integration before C8.

**Main sequence:** brief → scene contract → validated/persisted plan and spatial tools → typed evidence → real experiment/export interfaces → complete local journey → evaluations and correction round → verified public release → final documentation/video → submission.

The sequence describes integration readiness. It does not require Person 3 to remain idle while Person 2 finishes the backend or Person 1 to wait until the end to write documentation.

### 7.5 Dependencies for optional packages

All optional implementation waits until the core journey and its evidence are complete and capacity is available, as specified in section 8. The prerequisites below explain the technical order within each selected package.

| Package | Needs first | Work order inside the package |
| --- | --- | --- |
| O1 — Cloud sandbox branches | C2/C4/C5/C7, the local job controls from P2-05, and cloud credentials/access | Person 2 proves live execution and artifact identity first. Person 3 can scaffold progress/budget screens in parallel; real graph branching waits for the working cloud execution interface. Both then verify parallel comparisons. Token Factory inference alone does not provide sandbox execution. |
| O2 — Visual/dual-model review | C1/C3/C4/C7, the grounded P3-02 tools, and access to a suitable visual model | Person 2 produces labeled version-matched renders and truth fixtures. Person 3 integrates visual findings, then the coordinator. Run the three-way comparison only after both inputs and evidence-resolving tools work. CAD/PLY import from O5 is not required for render-based review. |
| O3 — Full event mode | C2/C4/C6/C7 and P3-05's environmental provenance | Person 2 defines timestamped observations and allowed operational actions. Person 3 builds entry/freshness screens against fixtures; real event-mode responses wait for validated observation/action APIs. Test weather-driven scenarios only after their explicit simulator coupling exists. |
| O4 — Tavily/rules | Core evidence ready, P3-05 provenance conventions, and Tavily credentials/access at the deferred stage | Agree the source contract. Person 2 implements retrieval/cache records; Person 3 integrates the desk against fixtures, then verifies context and applicability with actual records. Citation matching alone does not complete the package. |
| O5 — Intake/sharing/translation | C1/C2/C4, P2-05 export/access controls, and P3-06's verified English handover | Imports: conversion schema/validation before accepting imported geometry. Sharing: permission/expiry/revocation backend before publishing links/QRs. Translation: accurate English actions and metric references before Bangla review. Standalone export: working complete plan export and reproducible runner before the bundle. These four strands can run independently once their own prerequisites hold. |

### 7.6 Handoff rule to prevent blocking

For each checkpoint, the producer supplies the interface/schema, a representative success example, relevant failure examples, and one reproducible verification command or procedure. The consumer acknowledges compatibility and replaces fixtures with the real implementation. Track blockers by checkpoint ID, producer, missing artifact, and next action; resolve engineering blockers between Persons 2 and 3 rather than automatically assigning them to Person 1.

## 8. Optional and later work — assigned, but outside the core 100 points

Do not treat every feature discussed as a submission prerequisite. Start a paired optional package only after the core journey and its evidence are complete and there is capacity. Each package gives Persons 2 and 3 equal additional points; Person 1 receives no automatic extra work.

| Package | Person 2 responsibility | Person 3 responsibility | Points each | Acceptance / priority |
| --- | --- | --- | ---: | --- |
| O1: Nebius sandbox branching and parallel experiments | Verify live SDK/auth, persist provider IDs, isolate fresh artifacts, implement cancellation/cleanup and bounded parallel scheduling | Integrate graph jobs/progress, explain branches, expose budgets, verify reproducible user-visible comparisons | 8 | Deferred. Claim cloud sandbox execution only after actual runs. Serverless Jobs is a separate later backend, not an additional required integration. |
| O2: Visual review and dual-model coordination | Produce version-matched labeled renders and spatial truth fixtures; verify visual findings through geometry/simulation tools | Implement visual adapter, structured findings, disagreement coordinator, and JSON-only/visual-only/combined evaluation | 6 | Experimental. Keep only if verified additional findings justify false alarms, latency, and cost. Agreement does not independently validate the venue. |
| O3: Full event mode and environmental scenarios | Add timestamped observation storage, stale-data handling, operational action validation, and explicit weather-to-scenario coupling | Build manual Live Ops observations and available actions with freshness labels; distinguish planning recommendations from event responses | 4 | Later. Manual observations do not imply live sensors or reliable disaster prediction. |
| O4: Tavily and local-rule evidence | Implement bounded retrieval/cache/source records and source metadata, including quote verification for event research inputs (N18) and fix guidance citations (N19) | Integrate Evidence Desk/event brief, the accept/edit/reject flow for web-sourced inputs (N18), and guidance lines on fix cards (N19); review quotation context, jurisdiction, event applicability, and unresolved rule conditions | 3 | Deferred and optional. Retrieved text or a matching quote is not proof of applicability. |
| O5: Additional intake, sharing, and handover | Extend selected CAD/mesh/point-cloud intake only with defined conversion checks; add expiring/revocable share storage and standalone simulation bundle | Build intake review/provenance UI, share/QR controls, and checked Bangla steward cards | 7 | Later. Narrow formats first; verify translation, export fidelity, permissions, and supported geometry. |
| **Optional total** | | | **28 each** | Core plus all optional packages: Person 1 = 20; Person 2 = 68; Person 3 = 68. |

O5 is a broad backlog package, not a single sprint: split it into import, sharing, and handover subtasks and re-estimate before starting. If a package is cut, cut or rebalance both people's corresponding work. Do not leave one person completing a backend for an abandoned frontend.

New physics engines, pushing-force modeling, general-purpose Blender-style modeling, automatic sensing, and guaranteed safety certification are outside this delivery plan. Existing stairs and wind screening retain their documented limits.

## 9. Coverage of the discussed roadmap

This map assigns both the original milestones and the revised additions. An ID can span two owners when one produces data and the other consumes it; the task tables specify the boundary.

| Proposal IDs | Assigned work |
| --- | --- |
| R01, R02 | P2-01; P3-02 consumes the spatial tools. |
| R03 | P3-01 editor; P2-02 enforcement. |
| R04 | P3-02 questions; P2-04 sensitivity runs. |
| R05, R06 | P2-02; P3-03 selection and P3-06 display. |
| R07 | P2-03; P3-05/06 explanations and reports. |
| R08 | P3-03 candidates/orchestration; P2-02/04 apply and evaluate. |
| R09 | P2-04; P3-03 comparison. |
| R10 | P2-01 tool implementation; P3-02 model integration. |
| R11, R12 | O2. |
| R13 | O5. |
| R14 | Planning labels in P3-05; full event mode in O3. |
| R15 | Provenance/limits in P3-05; richer coupling in O3. |
| R16, R17 | O1; local bounded experiment foundation in P2-04/05 and P3-03/07. |
| R18 | P2-01/04 spatial fixtures and physical evaluation; P3-07 model evaluation; O2 dual-model evaluation. |
| R19 | P2-05 and P3-06 English handover; O5 translation/standalone exports. |
| R20 | P3-01/07 journey and release; P1-02/04 observed use and demonstration; P2-05 deployment. |
| N01 | P3-04, at the eventual integration stage. |
| N02, N03 | O4. |
| N04 | O1. |
| N05 | P2-04. |
| N06 | P2-05 backend controls; P3-07 frontend deployment. |
| N07 | O3. |
| N08 | P3-06 English; O5 checked Bangla cards. |
| N09 | O5. |
| N10 | P2-04. |
| N11 | P3-07. |
| N12 | P1-03/05 documentation and submission; P2-05 CI. |
| N13, N14, N15 | P3-01/02/03 with Person 2's shared contracts. |
| N16 | P3-04/07; P2-04/05 execution measurements. |
| N17 | O5. |

Existing maps, templates, imports, plugins, diagnostics, and themes stay available. Repair integration regressions under the responsible core task; expanding these systems is later work, not an unassigned mandatory rewrite.

## 10. Completion and workload rules

- A task is complete when its feature is integrated, its relevant failure cases are checked, and its documented acceptance condition holds. A UI mockup or configuration file alone does not complete a provider or simulation task.
- Persons 2 and 3 integrate frequently and keep the M1 sample workflow working. Backend integration belongs to Person 2; frontend/orchestration integration belongs to Person 3.
- If one person's estimate grows, move a coherent task or subtask to the other and update the totals. Keep the core allocation close to 20/40/40; optional work stays balanced between Persons 2 and 3.
- Changes discovered during organizer exercises are fixed by the implementation owner. Person 1 records and prioritizes them rather than becoming the overflow developer.
- Protect the complete core flow first. Defer O1–O5 before weakening plan persistence, honest result states, feasible fixes, final provider verification, or required submission materials.
- Publish measured improvements under stated scenarios and assumptions. Do not label simulated success as universal event safety or promise that this allocation will win a prize.

The intended result is one coherent product: an organizer can build and correct a venue, compare feasible changes using inspectable evidence, and export the exact selected operational plan.

## 11. Generic venues push (15 October 2026)

Added on branch `shahraz`. Names: Person 1 = Shahraz, Person 2 = Ridwan, Person 3 = Saif.
Background, contract, verified results and how to try it: [GENERIC_VENUES.md](nebius/docs/GENERIC_VENUES.md).

**Why:** an organizer testing the app found it template-bound. A building picked on the map
came in as one ground floor; there were no rooms, no third floor, no hospital patients or
marches, and no way to look at one floor of a replay. This push makes any building or site
usable. It does not replace sections 3–5; it is added on top, with the same rules from section 10.

### 11.1 Done (Shahraz, merged in `shahraz`)

| Area | What exists now |
| --- | --- |
| Contract | `event_kind`, `routes`, zone `groups` / `pre_movement_s` / `route_id` (additive, schema 1) |
| Building ops | add/remove floor, add/remove stair, add wall, add door, add room, set zone profile, add/remove route, set event kind; conformance tests; text-edit agent uses them live |
| Validation | reachability through any number of stairs (was capped at five hops) |
| Map buildings | every storey (map `building:levels` or chosen), two stair cores inside the outline, rooms and corridor grouped into wards, IBC occupant loads; `/places/at` gives levels and use; `/event-kinds` |
| UI | map form: floors, used as, inside, event kind; floor switcher (all / spread / one floor) on every 3D view |
| Review fixes | health detects a rejected or empty key; unknown routes and crashes use the error shape; sim container read-only, caps dropped, no pull, no pipe stall; Docker tests skip with a reason; designer slides features instead of dropping them; edit summaries use labels; rooms slide inside the outline |
| Groundwork for others | tested op payload builders (`web/src/lib/venueOps.ts`), `useEventKinds`, `editFloor` state, geometry helpers for stairs, walls and routes, all UI copy under `editor.*` |

### 11.2 Person 2 (Ridwan): simulation and backend

| ID | Task | Points | Acceptance |
| --- | --- | ---: | --- |
| G2-01 | People groups in the simulator | 5 | Each zone's `groups` give per-agent speeds (wheelchair, bed with assisted speed, elderly, child, staff) with cited values in `docs/ASSUMPTIONS.md`; sim test shows a ward with beds empties slower than the same ward of adults. |
| G2-02 | Pre-movement | 3 | `Zone.pre_movement_s` delays each agent's first step (JuPedSim API checked in the image); metrics count from the alarm; sim test proves no movement before the delay. |
| G2-03 | Routes and marches | 5 | `route_id` makes agents walk the route's waypoints (JuPedSim journey stages) and then the nearest exit; new template `rally_street` (event kind march, a real street width with its source); sim test with a small crowd. |
| G2-04 | `agents.json` and `GET /runs/{id}/agents` | 2 | Sim writes `{"schema": 1, "kinds": {"<agent id>": "<kind>"}}` for non-general agents; the endpoint returns `{"schema":1,"kinds":{}}` for older runs. Unblocks G3-03. |
| G2-05 | Instant estimate with groups | 2 | `api/core/tier1.py` adds pre-movement and the slowest group's speed per zone; a hospital estimate is slower than the same building of adults. |
| G2-06 | Surroundings of a building | 6 | `surroundings_m` (0–200) on `/venues/from-map`: F0 adds the outdoor ground around the building minus neighbours, outer walls with door gaps at entrances, exits where streets leave, an "Outside" zone with 0 people; validates for 3 real outlines. Unblocks G3-05. |
| G2-07 | Red and blue teams per event kind | 4 | Venue features given to the agents include event kind, groups, routes and floors; incidents filtered by kind; blue team may propose `set_zone_profile` and staggered starts; recorded fixtures updated; every number still from simulations. |
| G2-08 | Pre-movement defaults with sources | 2 | `/event-kinds` fills `default_pre_movement_s` only where a cited value exists (e.g. PD 7974-6 occupancy categories), with the source in ASSUMPTIONS. |
| G2-09 | Multi-floor sim tests and rewind | 3 | `sim/tests`: 3- and 4-storey buildings with two stairs evacuate everyone; rewind either works for multi-floor or the UI says why not. Templates `hospital_3f` and `office_tower_6f` made with the generator. |
| | **Total** | **32** | |

### 11.3 Person 3 (Saif): screens, editor and replay

| ID | Task | Points | Acceptance |
| --- | --- | ---: | --- |
| G3-01 | Building tools in the editor | 7 | Tool rail gets wall, door, room, stair, route and add/remove floor, acting on `editFloor`, using the tested `venueOps.ts` builders; undo/redo, autosave, keyboard, accessible names; one Playwright journey adds a floor, a stair and a room. |
| G3-02 | Zone profile and event kind | 4 | Zone inspector edits groups (shares), pre-movement and route; the event kind control (with `useEventKinds`) on the check screen offers "Use the usual people mix in every area". |
| G3-03 | Replay by people kind | 4 | Agents coloured and shaped by kind from G2-04 (colour never the only signal), with a legend; 3,000 people still ≥ 30 fps. |
| G3-04 | Routes, stairs, walls and labels in 3D | 4 | Routes drawn as arrows (`routeMarks`), stairs as ramps between any floors (`stairRun`, `stairProfile`), thin walls crisp (`wallThickness`); labels only for the shown floor and decluttered on big sites. |
| G3-05 | Surroundings option on the map screen | 2 | "Include the surroundings" with a distance slider (copy already in `en.json`), after G2-06. |
| G3-06 | Scenario viewer and event markers | 6 | Your plan lists every tested scenario with its verdict; clicking one plays it; the timeline shows markers and captions ("South door blocked at 1:00"); people per floor over time. Also find and fix the intermittent guided-journey failure (once in two runs on 15 Oct, clicking "Test this plan" started nothing). |
| G3-07 | Multi-storey browser journey | 3 | Playwright: draw an area → 4 floors, hospital, rooms → check → floor switcher → test → one-floor replay; screenshots in `docs/screenshots/`. |
| | **Total** | **30** | |

### 11.4 Person 1 (Shahraz)

Merges the G2 and G3 branches into `shahraz`, re-tests live with the real model, keeps
`GENERIC_VENUES.md` and `PROGRESS.md` current, and records the demo. Integration problems go
back to the task owner (section 10).

### 11.5 Order and handoffs

- Start now, no waiting: G2-01, G2-02, G2-03, G2-05, G2-07, G2-08, G2-09; G3-01, G3-02, G3-04,
  G3-06, G3-07.
- G3-03 needs G2-04. G3-05 needs G2-06.
- Shared files: `engine_jupedsim.py` is Person 2's; `web/src/scene/*` and `state/ui.ts` are
  Person 3's. Contract changes stay additive and go through Person 1.
- Branch from `shahraz`, small Conventional Commits, `make check` and vitest green before each
  merge request.
