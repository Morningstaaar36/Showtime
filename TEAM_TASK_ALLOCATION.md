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

The M1 startup work already provides local launch commands, Docker architecture configuration, and sample projects. The recorded verification includes startup, manual scene editing and persistence, a real 20-person simulation, and 30 selected regression tests. See [Mac setup](nebius/docs/MAC_SETUP.md). This does not establish completion of the proposed planning workflow or live AI/provider integration. Preserve the existing uncommitted startup changes during handoff.

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

## 8. Optional and later work — assigned, but outside the core 100 points

Do not treat every feature discussed as a submission prerequisite. Start a paired optional package only after the core journey and its evidence are complete and there is capacity. Each package gives Persons 2 and 3 equal additional points; Person 1 receives no automatic extra work.

| Package | Person 2 responsibility | Person 3 responsibility | Points each | Acceptance / priority |
| --- | --- | --- | ---: | --- |
| O1: Nebius sandbox branching and parallel experiments | Verify live SDK/auth, persist provider IDs, isolate fresh artifacts, implement cancellation/cleanup and bounded parallel scheduling | Integrate graph jobs/progress, explain branches, expose budgets, verify reproducible user-visible comparisons | 8 | Deferred. Claim cloud sandbox execution only after actual runs. Serverless Jobs is a separate later backend, not an additional required integration. |
| O2: Visual review and dual-model coordination | Produce version-matched labeled renders and spatial truth fixtures; verify visual findings through geometry/simulation tools | Implement visual adapter, structured findings, disagreement coordinator, and JSON-only/visual-only/combined evaluation | 6 | Experimental. Keep only if verified additional findings justify false alarms, latency, and cost. Agreement does not independently validate the venue. |
| O3: Full event mode and environmental scenarios | Add timestamped observation storage, stale-data handling, operational action validation, and explicit weather-to-scenario coupling | Build manual Live Ops observations and available actions with freshness labels; distinguish planning recommendations from event responses | 4 | Later. Manual observations do not imply live sensors or reliable disaster prediction. |
| O4: Tavily and local-rule evidence | Implement bounded retrieval/cache/source records and source metadata | Integrate Evidence Desk/event brief; review quotation context, jurisdiction, event applicability, and unresolved rule conditions | 3 | Deferred and optional. Retrieved text or a matching quote is not proof of applicability. |
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
