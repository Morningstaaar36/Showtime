# Showtime: reviewed product priorities

Review date: 2026-10-09. This document refines the feature recommendations from the conversation. It does not replace the full implementation inventory in `plan.md`. Findings below come from static code inspection; no application or simulation tests were run for this review.

## Objective and scope

Help a small event organizer find and compare feasible crowd-flow improvements, inspect the evidence, and hand over the exact plan that was tested.

Primary demonstration: a measured, single-level venue with existing gates, temporary barriers, and a specified staffing inventory. Use the current pedestrian model within its stated limits. Keep multi-floor and wind features available, but avoid making their simplified models the central proof of accuracy.

Development remains on OpenRouter and local Docker. Nebius and Tavily work is deferred at the user's request. The final competition entry still needs the required Nebius runtime integration and submission deliverables. No feature set guarantees a prize.

## Corrections to the previous proposal

1. Eight substantial additions were presented without a dependency order or enough attention to compute and free API limits. Deliver one thin complete workflow first, then improve its evidence.
2. Autopilot, the simple interface, multi-seed runs, cost reporting, validation, and steward packs already exist in the roadmap. Extend those milestones rather than create parallel systems.
3. Rules already contribute fixes to agent sessions. A benchmark must distinguish rules-only, model-only, and the actual hybrid workflow; otherwise attribution is misleading.
4. An organizer confirmation is not independent verification. Use precise provenance such as imported, assumed, organizer-confirmed, and measured, including date and source where supplied.
5. A favorable scenario pass count is not a probability of real-world safety. Failed, cancelled, timed-out, or skipped runs must remain unknown and visible.
6. Repeated seeds do not establish physical validity. Validation against experiments and sensitivity to assumptions answer different questions.
7. A feasible physical change can still depend on unrealistic operational behavior. Staff availability, start time, response delay, and assumed compliance need explicit treatment.
8. A field trial is evaluation work, not a reason to build a survey product. Use observed planning exercises, including unsuccessful outcomes.
9. The previous proposal missed combined-fix regressions, downstream crowd displacement, and faithful persistence of operational measures.

## Evidence from the current implementation

- `api/orchestrator/session.py::_fixes` mixes model proposals and standard rule responses. Preserve origin on every proposal and selected action.
- `_hurts_baseline` checks instant estimates; `_finish` confirms one selected attack before and after. This is weaker than confirmation across a fixed scenario suite.
- `_sim` substitutes an instant estimate after a simulation failure or timeout when available. Keep this useful preview, but prevent it from satisfying full-simulation acceptance gates.
- `_countdown` includes unconditional confirmation wording when a run exists. `plugins/export_html_report/__init__.py` also contains unconditional confirmation wording for the before/after table. Derive wording from result provenance and successful completion.
- `_apply_ops` can skip conflicting edits while accepted fix identifiers remain tracked. Final evidence must reference the exact successfully applied bundle.
- `apply_final` replaces venue geometry; operational measures are stored separately in the session summary. There is no explicit persistence of those measures in this apply path. Verify and implement an active plan containing both geometry and operations.
- `api/agents/numbers.py` checks membership in a pool of allowed values and exempts small integers. It does not establish that a number belongs to the correct metric, scenario, or unit.
- `sim/plugins/events.py::one_way` can hold incoming people outside the modeled area. A lower internal density must not conceal external demand or imply that an outside queue was assessed.
- The saved calibration data compares instant estimates with full simulations. It is not independent validation against real observations.

## Foundation: valid evidence and reproducible plan versions

Implement before expanding autonomous acceptance:

- A typed result basis: instant estimate, partial simulation, completed simulation, or unknown; preserve the original failed run and any fallback as distinct linked records.
- Acceptance requires the specified completed simulation evidence. Unknown results cannot pass or be treated as zero risk. Session completion and plan evaluation status are separate fields.
- Store the exact geometry, operational measures, constraints, scenario configuration, engine/settings version, and random seed with each evaluated plan. Cache identities include every input that affects behavior.
- Apply fixes as a validated bundle. Conflicting operations return a reviewable conflict; do not silently claim that the whole bundle was applied.
- Saving, loading, exporting, and rerunning a selected plan preserves operational measures as well as geometry.
- A change to relevant geometry, attendance, operations, or assumptions marks affected evidence stale until rerun.
- Report people remaining and incomplete clearance alongside time for 95% to exit. The 95% metric must not be described as everyone evacuated.

Acceptance examples: a timed-out confirmation stays unknown; a fallback estimate cannot produce a confirmed badge; a selected steward redirect survives save/reload; a conflicting fix bundle is not partially labeled accepted; an edited gate invalidates the old comparison.

## Six connected capabilities

### 1. Feasible planning constraints

Let the organizer mark fixed structures, movable objects, existing usable gates, staffing inventory, and restrictions on structural work. Separate planned audience dispersal from hazard-driven evacuation; do not transfer measures such as delayed release into emergency scenarios without a suitable reviewed policy.

Enforce constraints in code for both rules and model proposals. Prompt instructions alone are insufficient. Add explicit support for opening an existing gate where the current blue-team action schema does not expose it.

Each action declares dependencies: staff posts and active intervals, equipment, approval state, start time, and assumed response. Reject simultaneous assignments exceeding available resources. Use user-provided setup times and costs, or mark them unknown; do not invent precise estimates.

Done when: locked objects cannot be changed by either proposal source; staffing cannot be double-counted; unavailable gates cannot be recommended as immediately usable; unresolved dependencies stay visible.

### 2. Tested plan alternatives

Produce at most a few distinct feasible alternatives and a clear comparison with the original. Use the same baseline, population demand, scenario definitions, engine settings, and paired seeds for comparisons wherever applicable.

Evaluate the final combined bundle against baseline conditions and a predefined regression suite, including scenarios beyond the one that motivated the fix. Apply explicit acceptance thresholds per important metric. A weighted severity score may rank candidates, but must not hide a new trapped group or other unacceptable regression.

Check people moved outside the simulation boundary. Either include the receiving area in the model or identify it as unassessed; never treat preventing entry as making those people disappear from the planning problem.

Allow outcomes of improvement with remaining failures, insufficient evidence, or no feasible option found. Do not guarantee that every request produces a passing plan.

Done when: a fixture that improves one scenario but creates a disallowed regression is rejected; combined actions are checked together; outside demand remains accounted for; comparisons use equivalent evaluation conditions.

### 3. Assumptions that affect the decision

Attach provenance to critical inputs, including gate width, access, staffing, attendance, response delay, and operational compliance. Distinguish organizer confirmation from measured evidence.

Run a small bounded sensitivity screen to identify which uncertain inputs change the recommendation. Ask the organizer the most consequential unresolved question, rather than displaying a long compulsory checklist. Confirm important screening findings with the simulator before claiming a measured effect.

Show a useful outcome such as: "The preferred option depends on this gate being available. Confirm access before choosing it." Do not invent a statistical confidence score.

Done when: changing a consequential assumption can alter the preferred option, the UI identifies that dependency, and an assumed gate is never displayed as measured.

### 4. One simple planning journey

Extend the existing Copilot/LangGraph flow and planned Autopilot. Preserve three main screens: Describe, AI at work, and Your plan. Put a brief critical-input review within that flow. Keep the existing studio as Expert view.

On Your plan, show the main finding, recommended feasible option, unresolved conditions, and a before/after replay. Allow choosing another tested option. Advanced graph, metrics, and validation detail are one click away.

The complete first version can use an existing venue template. Add map intake after the evidence and selection flow works reliably.

Done when: a first-time organizer completes a template-based journey and exports the chosen plan without needing the expert panels. Record observed usability results; choose timing targets after initial measurements.

### 5. Exact handover with inspectable evidence

Export the selected geometry and operations with a concise map, gate actions, staff assignments, timing, unresolved dependencies, and assumptions. Human approval records the selected plan; it does not certify safety.

Generate numerical comparisons from structured metric references: run, metric, unit, scenario, plan version, and calculation. Link explanations to replay and evidence. Distinguish computed observations from model interpretations of causes.

Use existing report infrastructure. Start with a small English operational checklist. Expand to the planned Bangla steward cards after the numbers, actions, and names survive export accurately.

Done when: export and reload reproduce the selected operational plan; every displayed measured comparison resolves to compatible results; stale, partial, and unknown evidence retain their labels in the report.

### 6. Reproducible evaluation and usage record

Keep most evaluation tooling outside the main organizer flow.

Physical validity: reproduce a narrowly defined published bottleneck experiment with compatible geometry, population, measurement method, and the actual modified simulator used by the app. Separate calibration and evaluation examples. Publish error even if it misses the target. Limit conclusions to tested conditions.

AI contribution: compare rules-only, model-only, and hybrid proposals with equal simulation budgets and constraints, and reported LLM usage. Freeze evaluation scenarios before running comparisons and keep them out of selection. Attribute selected actions to their source. Measure distinct failures found, feasible proposals, final regressions, runtime, and cost. If rules perform as well, report that and evaluate whether language intake or explanation saves user effort.

Use paired seeds and compatible demand. Vary important operational assumptions separately from seed randomness. With limited compute, start with a small declared suite; publish completed, failed, and skipped counts without treating skipped runs as passes. For scale, comparing two plans over three scenarios and three seeds already needs 18 full runs per venue; measure runtime before expanding.

Record API inference charges separately from local compute usage and any unmeasured hosting costs. Tag cached versus fresh runs and include retries. A free endpoint means zero API inference charge, not zero total operating cost.

Run observed planning exercises with a few organizers on real or accurately reconstructed layouts. Record corrections, feasible/rejected suggestions, task time, and limitations. Do not equate simulation improvements with demonstrated prevention of injuries.

## Delivery order and scope cuts

1. Valid-result handling, complete plan persistence, and constraints.
2. One template through Autopilot to one feasible alternative, completed comparison, and exact report.
3. A bounded regression suite and sensitivity checks for the most consequential assumptions.
4. Validation, fair agent evaluation, observed organizer exercises, and usage measurements.
5. Broader venue intake, interface polish, accessibility, deployment checks, and submission materials.

These are completion gates, not calendar estimates. Preserve time for the eventual Nebius switch and a reproducible live demo. Tests with fake providers can cover most development behavior without consuming free API quota; final model-behavior claims require live runs on the claimed provider.

Defer broad local-rule research, live sensor integrations, a new physics engine, a survey dashboard, large translation coverage, and additional administrative portals. Keep full Live Ops, sharing links, and independent simulation export behind the core workflow in priority. Existing features can remain in Expert view.

## Demonstration

Use one organizer, one venue, fixed infrastructure, and a stated staffing limit. Show a real simulated bottleneck, a feasible alternative, a repeated test, and the exact handover. Open one unresolved assumption and show its effect on the decision. Include a brief evidence view with validation limits, proposal provenance, and measured cost/runtime.

Show the actual outcome, including remaining failures or unknowns. Use measured values from the demonstrated version. The primary promise is that the organizer can inspect what changed, why it helped in the tests, and what still needs checking.

## Competition references

- [Judging guidance](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works): autonomous tool workflows and four equally weighted criteria.
- [Official rules](https://nebiusglobalaihackathon.devpost.com/rules): final platform eligibility, required submission materials, and judge access.
