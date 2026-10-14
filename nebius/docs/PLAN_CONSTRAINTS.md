# P2-02 — organizer constraints and complete saved plans

## What this adds

P2-01 exposed a venue and computed spatial facts. P2-02 adds organizer policy and
operational actions to that same saved venue, validates complete proposals, and makes
later runs consume the saved actions.

The typed payload is stored in `Venue.extensions.organizer_plan`. Existing SQLite
version snapshots, undo/redo, duplicate, restore, and `.showtime.zip` export/import
therefore retain geometry and operations together. No database migration is required.

## API

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/projects/{id}/plan?version=N` | Complete venue, typed plan, saved version, and plan hash. Omit `version` for current state. |
| `PUT /api/v1/projects/{id}/plan` | Explicit organizer configuration: replace constraints/actions while preserving geometry. Requires `expected_version`. |
| `POST /api/v1/projects/{id}/plan/bundles/preview` | Validate a proposed geometry/action bundle without saving it. Returns `valid`, structured issues, and a candidate when valid. |
| `POST /api/v1/projects/{id}/plan/bundles` | Validate and save the entire bundle as one version, or reject it without a partial save. |
| `GET /api/v1/projects/{id}/plan/evidence` | Run references with `current`, `stale`, or `unknown` input applicability, separately from execution status. |

Use Swagger at `http://127.0.0.1:8000/api/docs` to inspect the actual request schemas.
Plan validation errors return HTTP 422 with issue codes. A changed project version
returns HTTP 409. Obtain a fresh version before retrying; a preview does not reserve it.
The preview candidate's `version` identifies its source version; it is not a saved
version. Saving returns the actual new version.

### Organizer policy

- `objects`: existing IDs mapped to `locked`, `placement` (`fixed`/`movable`),
  `origin` (`existing`/`proposed`), `access`, and `required_approvals`.
- A locked object cannot be edited. A locked floor also protects its child objects.
- Moving, resizing, or removing fixed objects requires allowed construction and approved
  permissions. Movable objects remain subject to geometry checks and any lock.
- New exits must be described in the bundle's `new_objects` as proposed construction,
  with construction allowed and approved permission references. Existing object policy
  cannot be overwritten through `new_objects`.
- Restricted access needs approval; unavailable access cannot be enabled or used by an action.
- `allowed_ops` optionally limits the patch operations permitted by the organizer.
- `approvals` record status, source, and who recorded it. Approved records require both
  source and attribution. These are organizer declarations, not independently verified permits.
- `resources` define staff/equipment pools, available quantities, and availability intervals.

`PUT /plan` is the explicit policy-edit command. Bundles and geometry patches cannot
relax existing policy. This local application has no authentication/organizer role
system; the endpoint is not an authorization boundary against an untrusted API client.

### Actions and dependencies

Each action has a stable ID, start/end times in seconds from the scenario origin,
optional simulator event, target IDs, required approvals, resources, and dependencies.
For an event, `at_s` must equal the action start. Dependencies must exist, have no cycle,
and finish before their dependent action starts.

Resource allocations occupy `[start_s, end_s)`. All overlapping allocations are added,
including repeated allocations to a pool; quantity cannot exceed its declared inventory.
An allocation must fit completely inside the pool's availability interval. Staff and
equipment use the same enforcement. Adjacent intervals may reuse a resource.

`marshal_redirect`, `one_way`, and `staggered_release` require staff allocations by
default. A staggered-release action must cover its entire delay. The current simulator
does not automatically stop marshal/one-way effects when their allocation ends, so a
simulation rejects those actions unless their interval covers the full run horizon.
Administrative actions without simulator events are persisted and validated; they have
no physical simulation effect. Resource checks establish inventory consistency, not
that the staffing level is sufficient for the real event.
The validator does not infer material quantities or installation work from geometry;
those requirements must be supplied as explicit actions and resource allocations.

## Complete bundle semantics

A bundle carries `expected_version`, a geometry `patch`, new `actions`, optional
`replace_actions`, `remove_action_ids`, `new_objects` policies, source
(`user`/`agent`/`rules`), and message. Replacements/removals must reference existing
actions and cannot conflict. Geometry and all action changes are validated together,
including dependencies affected by removal.

Geometry operations and operational validation run before any save. An invalid object,
geometry, permission, resource, or dependency rejects the complete proposal. The save
uses a database version check inside its transaction, so a proposal cannot overwrite
a newer project even if that change happens after preview.

The existing `/patch` API also enforces policy. `allow_new_errors` permits stress-test
geometry errors; it does not override organizer constraints. Full venue replacement
checks existing locks/policies. Undo/redo/restore are explicit history commands and
restore the policies and actions from their selected historical snapshot.

## Reruns and evidence

The run service automatically includes the selected venue's saved events exactly once,
alongside scenario/attack events. Model/rule fixes and direct scenario requests cannot
inject unallocated operational measures into a configured plan; submit structured
actions through the bundle API.

`plan_hash` covers geometry, actions, policy, and venue environmental/extension data.
It excludes project ID and top-level display name/description. Consequently operational
or constraint changes change run identity even if the old geometry-only hash does not.
Undo to identical full content can recover the original identity.

Evidence applicability is derived against the current plan instead of deleting or
rewriting old runs. Runs without this identity are unknown. Runs with additional
candidate fixes are conservatively unknown until their complete inputs are compared.
`current` means the plan inputs match; failed, partial, or queued execution is still
reported as such and cannot be interpreted as a successful evaluation. Full typed
metric/evaluation gates and simulator configuration compatibility belong to P2-03.

## Agent sessions and legacy projects

Sessions now apply each accepted geometry bundle atomically and update the working venue
before evaluating later fixes. They remeasure a later target after an earlier accepted
fix changes the working plan. Applying a finished session checks its original project
version and saves its operational measures with the final geometry.

Existing venues without an organizer plan retain their original editing behavior.
Legacy session measures are preserved as explicit actions with `enforce_constraints=false`
and `require_staff_for_measures=false`: no staff availability or physical feasibility is
invented. The plan API exposes those flags. Migrate by supplying real constraints and
allocations through `PUT /plan`, which requires constraint enforcement to be enabled.

The existing model/rule proposal format does not generate resource allocations or
construction-policy declarations. Such suggestions are rejected for configured plans;
Person 3's agent integration must generate the new bundle contract. The backend can
already accept and test those bundles through the API.

## Scope and verification

These features provide backend enforcement and persistence. Person 3 still needs to
display locks, proposal previews, allocations, approvals, and stale evidence in the UI.
Proposed construction remains labeled proposed after permission is recorded; the model
does not verify construction completion, door operability, or legal compliance.
Crowd and wind modeling assumptions are unchanged.

See [P2-02 testing](P2_02_TESTING.md) for automated cases and the manual workflow.
