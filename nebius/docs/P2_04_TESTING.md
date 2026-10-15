# P2-04 — fixes tested together and sensitivity: testing guide

What P2-04 (R-02 in `TEAM_TASK_ALLOCATION.md`) adds, and how to check it. Method and limits are
in [ASSUMPTIONS.md](ASSUMPTIONS.md#sensitivity-how-sure-your-plans-numbers-are).

- **Chosen changes tested together.** Accepting only some kept changes on Your plan saves the
  version and starts one run of exactly those changes under the test's worst attack (same tier
  and seed as its after-fixes run). The version is "tested together", and can be "confirmed", only
  once that run finished as a simulation. `GET/POST /api/v1/sessions/{id}/together`.
- **How sure are these numbers?** Your plan's key run again with 20% fewer and more people and
  walking 15% slower and faster, with the range and which assumptions break the plan.
  `GET/POST /api/v1/sessions/{id}/sensitivity`.

## Automated checks

Fake LLM and sandbox, no keys, no Docker simulations. From `nebius/`, with the M1 API image:

```bash
docker run --rm --platform linux/arm64 -w /app/api \
  -v "$PWD:/app" -v "$PWD/cache/uv-tests:/root/.cache/uv" \
  showtime-api:latest uv run --frozen pytest -q --basetemp=/tmp/p2-04 \
  tests/test_together.py tests/test_sensitivity.py tests/test_seeds.py \
  tests/test_apply_subset.py tests/test_checklist.py
```

Frontend helpers: `cd web && npx vitest run src/journey/plan/range.test.ts`.

| Requirement | Automated checks |
| --- | --- |
| A subset runs as one plan under the worst attack, same tier and seed | `test_a_subset_is_simulated_together_under_the_worst_attack` |
| Only a simulation makes it "tested together"; evaluation by the session rules | same test (`completed_simulation` → `confirmed`), `test_accepting_a_subset_starts_the_check` (mock sandbox → `preview`, not tested together) |
| A failed run keeps it untested, its numbers are not used, it can be retried | `test_a_failed_run_keeps_the_subset_untested_and_can_be_retried` |
| Older sessions without an evaluation | `test_a_session_saved_before_evaluations_finds_its_before_run` |
| Every kept fix accepted needs no extra run | `test_every_kept_fix_needs_no_extra_check` |
| One assumption changed per run; seed, attack, events and tier kept | `test_each_assumption_changes_one_input_of_the_after_run` |
| A variant that breaks the plan is named | `test_a_variant_that_breaks_the_plan_is_named` |
| Failed runs listed, left out of the range, no "holds" claim | `test_a_failed_variant_is_listed_and_left_out` |
| The range follows the chosen subset | `test_the_range_follows_the_chosen_changes` |
| Baseline when nothing was kept; rerun after a setting change | `test_baseline_when_nothing_was_kept_and_rerun_after_a_setting_change` |
| Speed only enters the run identity when used | `test_speed_factor_changes_the_run_identity_only_when_used` |
| Routes, 404 and 409 | `test_sensitivity_routes`, `test_the_check_is_unavailable_without_a_subset` |

## By hand in the app

1. Test a venue that breaks (for example the full School wing or the T-shaped alley) until
   Your plan lists two or more kept changes.
2. Untick one change and press **Accept these changes**. The card says the changes are being
   simulated together; when the run ends it says they were simulated together (or why not, with
   **Simulate them together again**), and the verdict and numbers come from that run.
3. Under **How sure are these numbers?** press **Check the range**. Five rows fill in (as tested,
   ±20% people, ±15% walking speed), each with its result and what it is based on, then the range
   and either "holds under every assumption tested" or the assumptions that break it.
4. Press **Check again**: the same runs are reused, nothing new is simulated.
