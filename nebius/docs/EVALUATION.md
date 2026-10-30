# Agent evaluation: rules only, model only, hybrid (S-01 / P3-07)

Status: 2026-10-17, branch `saif`. Owner: Saif.

## Question

Does the language model add anything over Showtime's rule-based attacks and fixes, and what does
it cost? Three arms run the same Red Team Night session on the same venues:

| Arm | Attacks from | Fixes from | `config.agents` |
| --- | --- | --- | --- |
| Rules only | `rule_attacks` (busiest exit, biggest zone, stairs; cited incidents) | `rule_fixes` (standard responses) | `rules` |
| Model only | the red-team agent | the blue-team agent | `model` |
| Hybrid (the product) | the agent, plus rule attacks when it returns none and the example script when it writes none | the agent, plus the standard responses it did not cover | `hybrid` (default) |

Everything else is equal: venue version, seed 42, one round, 3 attacks per round, 2 fixes per
attack, 2 attacks fixed, at most 12 simulations, the same Tier 1 screening, Tier 2 fix runs and
Tier 3 confirmation, the same acceptance rule (`FIX_MIN_GAIN`, no harm without the attack). The
judge and analyst run in every arm and are not compared.

## What is measured (all from the session's own event stream)

| Column | Meaning |
| --- | --- |
| Attacks | attack cards that reached screening |
| Broke the plan | attacks whose simulation crossed a break rule (danger density, people left, time) |
| Spatial errors (first answer) | problems the validators found in the agents' first answers: unknown exit, zone or floor ids, events or patches that do not fit the venue (`problems_first` on `agent_call`) |
| Left after repair | the same, after the one repair round (and escalation to `main`) |
| Invalid outputs | red/blue agent calls that ended without a valid answer |
| Feasible / infeasible fixes | fix bundles that applied and validated (and were simulated) / that were rejected before simulation |
| Kept | fixes accepted by the simulation rule |
| Regressions | fixes whose simulation was worse than the attack without them (gain < 0) |
| Repairs, escalations | repair rounds, retries on the `main` model |
| Cached calls | agent calls answered from the record/replay cache (`LLM_CACHE_MODE`) |
| Model time | summed wall time of red/blue agent calls |
| Tokens, cost | all agent calls in the session (cost from the provider's usage fields and `PRICE_*`) |
| Simulations | runs finished in the session (fresh or reused: runs are content-addressed) |
| Wall | session wall time on this machine |
| Evaluation | the session's own evaluation status (confirmed, partly, not confirmed, failed) |

Not measured: compute and hosting cost (local Docker on a laptop; the sim image is amd64 and runs
emulated on ARM, so wall times are slow and say nothing about a native amd64 machine), and energy.
Simulation results reused from an earlier arm (same plan, same seed, same events) cost no new
compute; the wall column shows it.

## How to run it

```
# API with the provider to evaluate (OpenRouter here) and the Docker sandbox
cd nebius/api && SANDBOX_PROVIDER=docker uv run uvicorn api.app.main:app --port 8001
python3 scripts/evaluate_agents.py --base http://127.0.0.1:8001 \
    --venues school_wing,conference_hall_2f:300,t_alley:400 --arms rules,model,hybrid
```

Raw sessions (events and summary) and the table land in `docs/evaluation/<stamp>-*`. A venue is
`template[:people]`: the headcount is scaled so a session fits in minutes on a laptop.

## Results

### Run 1 — rules only (2026-10-17, local Docker sandbox, no model)

| Venue | Arm | Attacks | Broke the plan | Spatial errors (first answer) | Left after repair | Invalid outputs | Feasible fixes | Infeasible | Kept | Regressions | Repairs | Escalations | Cached calls | Model time (ms) | Tokens | Cost (USD) | Simulations | Wall (s) | Evaluation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| school_wing | rules | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 5 | 60.3 | unconfirmed |
| conference_hall_2f:300 | rules | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 5 | 25.2 | unconfirmed |
| t_alley:400 | rules | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 5 | 30.1 | unconfirmed |

Raw sessions: `docs/evaluation/20261016T204751Z-*`.

- Each venue got 4 rule attacks (3 + the built-in example script); none broke the plan at these
  headcounts, so no fixes were proposed and the evaluation is "not confirmed" (nothing to
  confirm). The rules arm never calls a model: 0 tokens, 0 spatial errors by construction.
- **This is not yet a comparison.** Two things are missing:
  1. **The model-only and hybrid arms need a live model.** `OPENAI_COMPAT_API_KEY` is empty in
     this machine's `.env`, so OpenRouter calls fail (`/health`: "OPENAI_COMPAT_BASE_URL and
     OPENAI_COMPAT_API_KEY must be set"). With a key, rerun the command above with
     `--arms rules,model,hybrid` so all three arms share one run and one table.
  2. **Venues that break.** At 100–400 people nothing broke, so the blue team had nothing to fix.
     The next run should use headcounts at which the baseline or an attack crosses the danger
     density (for example `t_alley` at its template headcount, or `conference_hall_2f` at 1,200)
     on a machine that runs the amd64 sim image natively.
- Free OpenRouter models are rate-limited (requests per minute and per day); a full run is about
  6–10 red/blue calls per model session, plus judge and analyst calls.
