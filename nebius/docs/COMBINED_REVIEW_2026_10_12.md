# Showtime combined review — 12 October 2026

> Historical review: Docker was subsequently resumed and real simulator checks ran.
> New P2-02 implementation followed; see [current branch status](P2_P3_BRANCH_STATUS.md).
> The verification table below describes the earlier checkpoint, not this branch’s final source.

## Scope and branch status

Reviewed the existing application, local P2-01/P2-02 work, and the P3 guided journey together.

- Local `main`: `0d42430` — P2-02 constrained plans and atomic bundles.
- Last fetched `origin/main`: `0d53ab5` — P2-01 spatial inspection.
- P3 branch reviewed: `origin/feat/p3-01-guided-journey`, `7a3f1f9`.
- Combined code and review fixes are isolated in `cache/p2-p3-audit/nebius`.
- Main application code has not been merged with P3 or pushed during this review.
- This document is a local review artifact, not a merge approval.

## OpenRouter result

The supplied curl response proves that the credential and
`nvidia/nemotron-3.5-lightning:free` work for a chat completion. I also tested the model
through Showtime's actual structured agents, with caching disabled and local fallback disabled.

| Live check | Observed result |
| --- | --- |
| Exact headcount edit | One validated `set_people` operation set the requested zone to 120 people; one request, about 3.1 seconds. |
| Locked exit | The model attempted the edit again after feedback; the backend still rejected it. Two requests, about 1.9 seconds. |
| Venue designer | Built a 30 × 20 m, single-floor venue for 300 people with two specified exits; one request, about 4.9 seconds. |
| Red team | Returned a valid incident-linked attack using an existing exit; one request, about 2.7 seconds. |
| Initial complete session | Live red, blue, and judge calls completed; one valid attack and one candidate fix. The fix was not accepted. Three requests, about 14.9 seconds. |
| Complete session after summary correction | Finished with one accepted candidate and an explicitly labeled mock outcome summary. Four requests, including a repaired blue-team response; about 90.6 seconds. |

The complete session used **mock simulations**. These checks establish provider and
agent integration; they do not establish accurate disaster prediction or measured improvement.
One standalone blue-team harness check initially failed because the harness passed typed
operations to a dictionary-only validator. That was a harness error; the complete session
successfully produced a validated blue-team candidate.

The live judge exposed a real defect: it claimed that fixes had improved the plan when
the recorded accepted-fix list was empty and there was no after-fix result. Its numbers
passed membership checks. The session outcome summary now comes from recorded facts;
the language model supplies separate follow-up suggestions. Number matching is not
semantic validation of those suggestions. For example, the original model used a
baseline density measurement as an alert threshold; that remains a reason to implement
typed evidence and recommendation validation before treating suggestions as instructions.

The designer also supplied an unspecified roof height without listing it as an assumption.
Its geometry passed the checks, but every inferred physical input still needs organizer review.

The key pasted into chat was passed to temporary test processes with terminal echo
disabled. It was not written into source files or commands, committed, or copied into
this report. Rotate that key and store the replacement in your local `.env`.

## Verification

| Gate | Result |
| --- | --- |
| Full fast backend suite, after summary fix | **225 passed, 1 skipped**; 12.70 seconds. |
| Frontend unit suite | **33 passed**, six files. |
| Browser journeys | **5 passed**; desktop, guided creation/edit/lock/test/accept, reports, help, old routes, and 390 px mobile layout. |
| Production build | Passed TypeScript and Vite build. |
| Frontend lint | Passed with zero permitted warnings. |
| Strict Python typing | Passed for 42 configured files. |
| Python lint and formatting | Passed; 142 files formatted. |
| Import contracts | Three kept, none broken. |
| Patch whitespace | `git diff --check` passed. |
| M1 P2-02 test command | Dry run inspected; includes current API **and plugins** bind mounts. |
| Visual capture | Desktop home, venue editor, result page, and mobile editor captured; no uncaught page errors. |
| Real Docker simulation | **Blocked:** Docker Desktop reports that it is manually paused. |
| Real Nebius integration | Not run; the credential-dependent test was skipped. |

The five browser journeys used mock AI/simulation providers. Their text-edit branch
deliberately skips real AI requests when the provider is fake. Live AI was checked
separately above. The browser suite ran before the final summary correction; backend
regressions verify that correction, and the preview API was restarted to load it.
The final readable-name adjustment was verified with the production build and lint.

## Fixes in the combined review copy

1. **Server-enforced organizer locks.** P3 locks now affect backend preview, patches,
   whole-venue replacement, and agent edits. Organizer-only annotation operations cannot
   be used by agents to unlock geometry. Locked floors protect their child objects.
2. **One policy interpretation.** Typed P2 constraints take precedence over legacy
   annotations. Organizer edits synchronize the representations and retain actions.
   Undo captures the original policy. Malformed annotations return a validation error.
3. **Atomic edits and stale previews.** Failed combined changes roll back together.
   AI previews carry an expected version; applying an old preview returns a conflict.
4. **Complete plan freshness.** Result freshness uses the plan identity, including
   saved actions, constraints, and environmental inputs. Session acceptance rejects a
   changed plan even when its geometry stayed the same.
5. **Session acceptance preservation.** Accepting a fix retains organizer metadata,
   resources, saved measures, and the candidate's correctly pruned constraints.
6. **Honest evidence labels.** Fake results are previews. Failed, cancelled, queued,
   running, and incomplete runs cannot receive an ordinary passing verdict. Reports,
   cards, and countdown descriptions distinguish previews and estimates.
7. **Recorded outcome summaries.** Sessions display a deterministic assessment of the
   tested attacks and accepted fixes. Unaccepted candidate metrics cannot become an
   improvement claim, and live judge event summaries do not repeat unchecked conclusions.
8. **Readable proposed-object names.** The result page also reads names from the tested
   scene, so newly proposed exits can be named before they are accepted.
9. **Integration gates.** Repaired typing issues, regenerated shared schemas, and added
   regressions for the P2/P3 boundaries and evidence/reporting failures.

These fixes are local to the isolated review copy. They are not yet on GitHub main.

## Implemented features checked

| Area | Included behavior |
| --- | --- |
| Projects | Templates, creation, versioned edits, undo/redo, persistence, imports/exports. |
| P2-01 | Lossless scene snapshots, provenance/hash, geometry validation, usable area, connectivity, routes and clearance, explicit incomplete routing budgets. |
| P2-02 | Object/construction constraints, resources, staff/budget/approval/dependency checks, atomic geometry/action bundles, persisted operations, version conflicts. |
| P3 guided journey | Describe → check venue → AI at work → your plan, with Expert view retained. |
| Collaborative editor | Numeric changes, door placement, barriers, headcounts, provenance, existing/proposed status, locks, and AI patch preview before applying. |
| Sessions | Progress events, attack/fix cards, stop controls, stored replay, candidate comparisons, acceptance and report links. |
| Existing services | Instant estimates, plugin contracts, scenario/operation validation, report exporters, provider adapters, and failure handling covered by automated tests. |

## Remaining limitations and next work

1. **Finish P2-03 evidence identity.** A failed sandbox run can currently be replaced
   in memory by an instant estimate with the failed run's identifier. Separate those
   records and carry the complete plan/scenario identity through every result.
2. **Grounded agent tools and explanations.** Agents still see a compact venue summary,
   not all P2-01 spatial facts. Number membership and incident links cannot prove causal
   explanations, source applicability, or correct threshold use.
3. **Connect P2 operational planning to P3.** The API supports constraints/actions, but
   the guided screens do not yet provide full staffing, equipment, approvals, dependency,
   or budget editing. Blue-team output still uses patches and operational events rather
   than the complete typed planning bundle.
4. **Proposed construction in legacy plans.** An unconfigured legacy plan can simulate
   a proposed exit. A badge alone does not establish that construction is permitted or
   physically possible. Use configured constraints and explicit approval before relying
   on that scenario.
5. **Complete handover and evaluation.** Add an operational handover tied to the tested
   plan and compare agent proposals with fixed scenarios and standard fixes.
6. **Measure claims.** Free inference usage excludes compute, hosting, and search.
   A short model call does not prove that a complete event is planned in minutes.
7. **Physical validation.** Walking/queuing, simplified stairs, and wind screening remain
   the documented model scope. This review did not validate pushing forces, structural
   safety, site feasibility, or compliance with a particular event's applicable rules.
8. **Repeatability of free models.** Successful requests establish compatibility for
   those requests. They do not guarantee availability, consistency, or quality at scale.

Existing stored sessions retain their original text. Run a new session to receive the
corrected summary behavior; this review does not silently rewrite historical records.

## Review it locally

- Combined preview: **http://localhost:5175** — mock providers for reproducible UI review.
- The earlier P3-only preview remains on port 5174; use 5175 to review the integration fixes.
- Screens: `cache/p2-p3-audit/nebius/cache/review-screens/`.
- Live-session evidence: `cache/p2-p3-audit/nebius/cache/live-session/result.json`.

For your normal OpenRouter setup, use the actual setting names in `nebius/.env`:

```dotenv
LLM_PROVIDER=openai
OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPAT_API_KEY=your_rotated_key
MODEL_FAST=nvidia/nemotron-3.5-lightning:free
MODEL_MAIN=nvidia/nemotron-3.5-lightning:free
MODEL_LONG=nvidia/nemotron-3.5-lightning:free
MODEL_JUDGE=nvidia/nemotron-3.5-lightning:free
LLM_SUPPORTS_JSON_SCHEMA=false
LLM_EXTRA_BODY={"reasoning":{"enabled":false}}
LLM_FALLBACK=none
```

The normal `.env` inspected during this audit still had an empty key and a different
model ID. A successful separate curl request does not populate the application's settings.
Restart the API after saving settings, and unpause Docker Desktop before testing real
simulations through the M1 startup workflow.
