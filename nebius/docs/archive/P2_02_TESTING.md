# P2-02 — M1 testing guide

## Requirements

- Docker Desktop running and unpaused, with the existing M1 test profile.
- Work from the `nebius` directory in this checkout.
- Existing API image `showtime-api:latest`; network access if locked test dependencies
  are not cached. These isolated tests use fake LLM and sandbox providers, not API keys.
- Rebuild the application with `make m1-test-up` before testing its new live routes.

Run the focused tests and the affected scene, geometry, persistence, API, and agent
regressions:

For the complete fast API suite, a single command is available: `make m1-test-p2-02`.
It uses the current source code and the existing M1 API image, without starting the app.
The command below runs the focused subset instead.

```bash
docker run --rm --platform linux/arm64 \
  -w /app/api \
  -v "$PWD/api:/app/api:ro" \
  -v "$PWD/cache/uv-tests:/root/.cache/uv" \
  showtime-api:latest \
  uv run --frozen pytest -v --tb=short \
  --basetemp=/tmp/showtime-plan-tests \
  tests/test_plan.py tests/test_plan_api.py \
  tests/test_scene.py tests/test_scene_api.py \
  tests/test_venue_core.py tests/test_api.py \
  tests/test_persistence.py tests/test_redteam.py
```

## Acceptance coverage

| Requirement | Automated checks |
| --- | --- |
| Fixed geometry and locks | `test_fixed_exit_changes_require_construction`, `test_locked_floor_rejects_child_changes`, `test_direct_edits_and_replacements_cannot_bypass_locks` |
| Approval and proposed-exit handling | `test_new_exit_requires_status_permission_and_construction`, `test_approval_record_needs_attribution_and_nested_nan_rejected` |
| Access restrictions | `test_access_policy_blocks_unapproved_open_exit` |
| Whole-bundle rollback | `test_atomic_bundle_rejection_and_preview`, `test_failed_resource_allocation_rolls_back_geometry` |
| Atomic action replacement/removal | `test_atomic_action_replacement_changes_evidence_without_geometry_change`, `test_remove_geometry_and_its_action_in_one_bundle`, `test_conflicting_or_missing_action_edits_do_not_save` |
| Staff/equipment inventory and availability | `test_invalid_actions_rejected`, `test_equipment_and_staff_availability` |
| Dependencies and interval boundaries | `test_resource_boundary_and_dependency_order`, `test_invalid_actions_rejected` |
| Save/reload, undo/redo, export/import, rerun | `test_save_reload_undo_redo_export_and_rerun` |
| Stale previews and concurrent saves | `test_version_conflict_and_commit_guard` |
| Policy cannot be weakened through proposals | `test_new_object_policy_cannot_unlock_existing_object` |
| Saved operational events and stale evidence | `test_runs_use_saved_actions_and_mark_evidence_stale` |
| Resource bypass and simulator horizon | `test_unallocated_operations_and_short_coverage_cannot_start_runs` |
| AI/rules share validation | `test_rules_and_ai_share_constraint_validation` |
| Permitted operations and movable objects | `test_movable_zone_and_allowed_operations`, `test_whole_replacement_respects_allowed_operations` |
| Scenario requests cannot bypass allocations | `test_attacks_cannot_smuggle_unallocated_plan_actions` |
| Session atomicity and operational persistence | `test_agent_applies_ops_atomically_and_persists_legacy_measures` |
| Identity includes operations/policy | `test_plan_identity_tracks_operations_and_policy_not_display_name` |

These tests check software behavior with fake providers. They do not establish crowd
physics accuracy, sufficient staffing, or authentic permissions.

## Manual API workflow

Use Swagger at `http://127.0.0.1:8000/api/docs`. Example requests are actual files in
[docs/examples](../examples/), so you can open them in an editor if terminal copying is difficult.

1. Create a fresh project with [the room request](../examples/p2-01-room-request.json).
   Its first version is 1. Record the returned project ID.
2. Use `PUT /projects/{id}/plan` with [the organizer setup](../examples/p2-02-plan-setup.json).
   It fixes exit E1 in place, declares two stewards and one radio, and saves version 2.
3. Use `POST /projects/{id}/plan/bundles/preview` with
   [the operational bundle](../examples/p2-02-plan-bundle.json). Expect `valid=true` and a
   candidate with one staggered-release action. A fresh `GET /plan` must still show version 2.
4. Submit the same body to `POST /projects/{id}/plan/bundles`. Expect version 3.
   `GET /plan` must contain the action; its hash must match the preview's candidate.
5. Repeat that submission without changing `expected_version`. Expect HTTP 409 and no
   new version. This demonstrates protection against stale proposals.
6. Try `/patch` to resize E1. Expect HTTP 422 `construction_not_allowed`, with no new
   version. Try an action that allocates three stewards; expect `resource_overallocated`.
7. Start a Tier 2 run for version 3 with a fixed seed. Its request should contain the
   saved `staggered_release` event exactly once. Wait for its actual execution outcome;
   the live Docker simulator may have a different result from the fake test provider.
8. Inspect `GET /plan/evidence`. The run's inputs should be `current`, with execution
   status reported separately. Change Z1 from 20 to 10 people through `/patch`:
   applicability should become `stale`. Undo: the full original hash should return.
9. Refresh/restart the API and reopen the project: geometry and action must remain.
   Undo/redo and export/import must preserve the same complete content and rerun events.

For a pre-existing project, use its actual current version in every write; the example
numbers assume a newly created synthetic room. Do not overwrite an unrelated plan.

## Implementation verification record

The fast API suite passed in an isolated native macOS ARM64 Python 3.12 environment
using the repository's frozen dependencies: 185 passed, 1 skipped. Ruff, strict backend
mypy, import-boundary checks, and schema export passed. See [PROGRESS.md](../PROGRESS.md).

Docker Desktop was paused during development. The Docker command and the live browser /
real-simulator workflow above remain to be checked after unpausing it. Native fake-provider
tests verify software behavior; they are not real simulator validation.
