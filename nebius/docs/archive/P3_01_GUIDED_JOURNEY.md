# P3-01 — three-screen journey and collaborative editor

Implemented on 12 October 2026 (Person 3). Builds on P2-01's scene contract (C1).
Locks are enforced in the UI only (editor, Expert view inspector, and the Accept buttons for AI
changes); the API still accepts a patch to a locked object. Server-side enforcement for every
patch and agent is P2-02 (C2). Typed run evidence is P2-03 (C4).

## What an organizer can now do

| Step | Route | What it does |
| --- | --- | --- |
| 1. Describe | `/` | Pick a template, or describe the venue for the designer agent to draft. Recent plans below. |
| 1b. Check your venue | `/p/:id/describe` | The collaborative editor (below). Primary action: **Test this plan**. |
| 2. AI at work | `/p/:id/work?session=` | Five plain steps from the red-team session's phases, elapsed time, stop with confirmation, the latest finished simulation in 3D, attack and fix cards. Moves to step 3 by itself only for a test the organizer just started (`live=1`). |
| 3. Your plan | `/p/:id` | Verdict, three numbers with their source, Before/After replay, the AI's changes as a reviewable bundle, top risks with sources, **Accept these changes**, **Download report**. |
| Expert view | `/p/:id/expert/:mode?` | The existing studio, unchanged. Old links (`/p/:id/simulate` …) redirect here. `/projects` keeps the full project list, imports and the map-based start. |

The template journey needs no expert panel; `e2e/journeys.spec.ts` checks it end to end.

### Collaborative editor (Check your venue)

- **Doors**: numeric width, closed in this plan, drag in 3D, remove; **Add door** tool.
- **Barriers and features**: move by a typed distance or drag; **Draw barrier** tool; remove.
- **Areas**: headcount.
- **Existing vs proposed**: every exit and obstacle can be marked *Already there* or *Proposed new*. New doors and barriers ask which one when they are drawn. Proposed items render see-through with a "proposed" label; a proposed exit carries the warning that simulations still count it as open.
- **Provenance**: Not stated / Assumed / Imported / Confirmed by organizer / Measured (requires a source). Read back through the P2-01 `/scene` snapshot when it matches the current version.
- **Locks**: a locked item has no drag handle and read-only fields, here and in Expert view.
- **AI patch preview**: "Ask the AI to change the venue" calls the venue agent with `apply: false`, dry-runs the patch, shows it in 3D with outlines (Now / With change), lists the operations, blocks **Apply** when it touches a locked item or no longer matches the current version, and marks new openings as proposed when applied. Nothing is saved before **Apply**.
- **Stale evidence**: Your plan compares the simulation hash of the tested version, the AI-fixed run and the current version. Locks and provenance never make results stale; geometry or headcount edits do.

## Backend changes (for Person 2's review)

| Change | Where | Why |
| --- | --- | --- |
| `set_annotation` PatchOp (`target`, `provenance?`, `locked?`, `change?`) with exact undo | `plugins/ops_core` | The only write path for provenance (into P2-01's `scene_metadata`) and for locks / existing-proposed (new `plan_annotations` extension). Organizer-only: `user_only = True`. |
| Agents never see organizer-only ops | `api/agents/context.py` (`agent_ops`) | Otherwise the venue agent could unlock what a lock restrains. |
| Removing an exit, obstacle or zone drops its annotations; undo restores them | `plugins/ops_core` | P2-01's snapshot rejects metadata pointing to missing objects with `422 invalid_scene`. |
| `POST /projects/{id}/patch/preview` | `api/app/routes_projects.py` | Dry run for AI proposals; problems returned as data. |
| `apply_final` refuses a plan for an older geometry (`409 stale_plan`), carries the current organizer annotations, name and extensions, and marks exits/obstacles the fixes added as proposed | `api/orchestrator/session.py`, `api/core/annotations.py` | It replaced the whole venue with the session-start copy, silently discarding later edits and locks. |
| `/edit` maps `AgentUnavailable` to `503 llm_unavailable` | `api/app/routes_agents.py` | Pre-existing bug: with no working model the route returned a raw 500. |

`plan_annotations` format (inside `venue.extensions`):

```json
{"plan_annotations": {"schema_version": 1, "objects": {
  "stage": {"locked": true},
  "door_e1": {"change": "proposed"}}}}
```

Absent `change` means "never stated" (templates and imports describe what is there). Both
extension keys are outside the simulation hash. **Proposal for C2:** P2-02 can adopt these
fields or move them into its constraint model; the UI reads them only through
`web/src/lib/annotations.ts`, so a move is a one-file change.

## Not done here (owner)

- Server-side lock enforcement for every patch and agent, permitted actions, staffing, dependencies — P2-02.
- Proposed exits are still simulated as open; excluding them from the current operational plan — P2-02.
- Typed evidence status and metric references; Your plan uses run tier/status and hashes — P2-03, then P3-05.
- Autopilot graph, consequential questions, grounded scene tools — P3-02. "AI at work" currently follows a quick red-team session (1 round, 3 attacks, up to 2 fixes each).
- Feasible alternatives and selection between several candidates — P3-03.
- Handover report rendering from the selected plan — P3-06 (Download report uses the existing session report).

## How it was verified

- `make check`-equivalent: ruff, format, import-linter green; `pytest -m "not slow"` 166 passed, 1 skipped (20 new in `api/tests/test_annotations.py`); vitest 22 passed (12 new); `vite build` OK.
- mypy: 15 errors, all in `api/core/scene.py` (P2-01), present before this change; none in new code.
- Playwright `make e2e`: 5 passed against the app with `LLM_PROVIDER=fake` and `SANDBOX_PROVIDER=fake`, including the new guided journey and the legacy-URL/phone-width check. The fake sandbox does not simulate (no trajectories), so replays and numbers in that run are placeholders; a real run needs Docker (`make m1-test-up`).
- Console: "Attempted to synchronously unmount a root" warnings and an occasional `removeChild` error when leaving a 3D view also occur in the unchanged code (A/B against `HEAD`: 4 vs 2 in 10 navigations); they come from 3D label teardown.
- Likely pre-existing (same code pattern, not verified): the Expert view inspector's number fields may save the same value twice (Enter, then blur). The new editor had this bug and now guards against it.

Run it: `make dev` (or `make m1-test-up`), open <http://localhost:5173>, pick *Conference hall, 2 floors*.
