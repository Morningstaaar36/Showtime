# P2/P3 branch status — 13 October 2026

This branch captures the current implementation at the user's requested stopping point.
It is work in progress, not a completed or fully verified P2/P3 release. Main was not merged.

## Included

- P2-01 scene contracts and the existing P2-02 constraints, atomic bundles and persistence.
- P3-01 guided journey and collaborative editor from the reviewed P3 branch.
- Combined review fixes for server locks, stale previews, plan acceptance, honest result
  labels, computed session summaries, and separate mock/Docker run identities.
- New shared plan-bundle validation for API, model proposals, rule proposals and simulation
  requests. Typed fixes carry actions, replacements, removals and new-object policies.
- Guided forms for staff/equipment availability, permission records, object policy,
  declared budgets, and preview/apply/edit/remove operational actions.
- Saved actions and proposed resource allocations displayed in the result page/report.
- New backend pipeline regressions and a browser operational-plan scenario.

## Verification

### Earlier combined review, before the latest implementation

- Native backend: 225 passed, 1 skipped.
- Frontend: 33 unit tests and 5 browser journeys passed; browser providers were mocks.
- Build, lint, typing and import contracts passed.
- Real local Docker/JuPedSim simulator: 9 tests passed in 31 minutes 29 seconds.
- M1 Docker startup smoke passed, including a saved edit and a real 20-person evacuation.
- Full ARM64 backend: 224 passed, 1 skipped, 1 failure in the 50 ms warmed-estimate
  performance gate. school_wing took about 497 ms; its retest took about 294 ms.
- Earlier live OpenRouter checks used nvidia/nemotron-3.5-lightning:free. Complete agent
  sessions used mock simulations; no combined live-model/real-simulation claim is made.

### Latest P2-02 integration work

- API schema export succeeded in local ARM64 Docker; TypeScript contracts regenerated.
- TypeScript checking passed at an intermediate checkpoint, before the final UI additions.
- Frontend lint passed at an intermediate checkpoint, before the final UI additions.
- A focused Docker backend command timed out after 180 seconds during collection;
  dependency setup had consumed about 66 seconds. No test passes were reported.
- A reusable isolated Docker container was then prepared; cached dependency setup succeeded.
- Development/testing was interrupted by the user's request to commit and push this snapshot.
- The new backend and browser tests have NOT been verified. The entire combined pipeline
  has NOT been rerun successfully after these changes.

## Required next work

Items 1–5 were completed on `integration/p2-p3` on 14 October 2026; see
[PROGRESS.md](PROGRESS.md). Remaining:

1. Live OpenRouter session (the configured key has expired) and a combined
   live-model/real-simulation run.
2. Complete P2-03 and the remaining separately allocated P2/P3 milestones afterward.

Nebius inference, cloud sandbox execution and Tavily remain deferred. Local simulation
execution uses Docker. Successful software tests do not establish real-world safety.
