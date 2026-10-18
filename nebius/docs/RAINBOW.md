# The failure map: a quality-diversity red team scored by physics

Red Team Night used to ask the model for "N different attacks" each round and keep the ones
that broke the plan. Models drift towards the same few ideas (block the busiest exit, again),
so the search found the worst failure but said little about *where else* the plan is weak.
The failure map turns the red team into a quality-diversity search: it looks for the
strongest attack of every kind, in every part of the venue.

Code: `api/orchestrator/archive.py` (pure, unit-tested in `api/tests/test_archive.py`), the
loop in `api/orchestrator/session.py`, rule fills in `api/orchestrator/fallbacks.py`, UI in
`web/src/panels/FailureMap.tsx`.

## Research basis

- **Rainbow Teaming** — Samvelyan et al., *Rainbow Teaming: Open-Ended Generation of Diverse
  Adversarial Prompts*, NeurIPS 2024 ([arXiv:2402.16822](https://arxiv.org/abs/2402.16822)).
  A MAP-Elites archive over feature descriptors (risk category × attack style); a mutator LLM
  proposes a candidate for a chosen cell; a judge decides whether it replaces the cell's elite.
  The authors note the search learned to exploit their LLM / reward-model evaluator.
- **RainbowPlus** — [arXiv:2504.15047](https://arxiv.org/abs/2504.15047) (2025). Keeps several
  elites per cell instead of one, and uses a cheaper fitness evaluation.
- **MAP-Elites** — Mouret and Clune, *Illuminating search spaces by mapping elites*, 2015
  ([arXiv:1504.04909](https://arxiv.org/abs/1504.04909)).

## What is different here: the judge is physics

In Rainbow Teaming the fitness comes from a language model, so the search can learn to please
that judge instead of finding real failures. Here **the model only proposes; the simulator
scores**. Fitness is a formula over simulated metrics (JuPedSim in the sandbox, or the instant
estimate when a sandbox run fails), so there is no evaluator to talk round: an attack only
scores high if the simulated crowd really ends up too dense, too slow, or stuck inside.

## The archive

**Cells = hazard kind × where.** Both axes are computed from the attack's events, never from
the model's description of it.

| Hazard kind (row) | Event types |
| --- | --- |
| Exit blocked | `block_exit`, `unblock_exit` |
| Surge or late arrival | `surge` (also late `at_s`), `late_arrival`, `staggered_release` |
| Counterflow | `counterflow` |
| Slowdown, smoke or dark | `slowdown`, `smoke`, `darkness`, `power_cut` |
| Wrong route or one-way | `marshal_redirect` (misdirection as an attack), `one_way`, `route_change` |
| Adaptive scenario (code) | `script` (AI-written `on_step` code) |

Event types other plugins add later are placed by keyword (e.g. `smoke_spread` → slowdown),
else as adaptive. An attack that mixes events is named by its most specific failure
(adaptive > exit blocked > counterflow > wrong route > surge > slowdown).

**Where (columns, at most 4 + "Whole venue").** Several floors: one column per floor.
One floor with 1–4 exits: one column per exit, holding the zones nearest to it. Otherwise
the west / east / north / south sides that hold something. The place is the region of the
event's target (`exit_id`, `to_exit_id`, `zone_id`, …); a script's place is the region of the
ids its code names, else the whole venue. A cell exists only when it is possible (no "exit
blocked" on a floor without exits; only slowdowns and scripts can hit the whole venue), so the
grid is at most 6 × 5 and coverage counts only reachable cells.

**Fitness (severity).** Each part is 1.0 at the threshold of the matching rule in
`break_reasons` (session.py), a plain ratio below it, and grows linearly above it to 2.0 at
"twice as bad":

| Part | Below the break | 1.0 (break) | 2.0 |
| --- | --- | --- | --- |
| evacuation | RSET × SF / target | RSET × SF = target | RSET × SF = 2 × target |
| danger time | t / `DANGER_MIN_DURATION_S` | t = 5 s | t = the evacuation target |
| people inside (Tier 3) | n / (tolerance + 1) | n = tolerance + 1 | 10 % of the crowd |
| trapped | – | one person | 10 % of the crowd |
| partial Tier 2 run | (1 − fraction out) / 0.5 | half out | nobody out |
| peak density | 0.9 × min(1, peak / danger) | never | never |

`severity = max(parts)`, each capped at 3 so one extreme metric cannot dominate the QD-score.
Hence **severity ≥ 1.0 exactly when the run breaks the plan** (tested over a grid of metrics;
tolerance = max(5, 0.5 % of people)); the density part gives the search a gradient below the
break but can never reach 1 on its own. Failed runs score 0 and are not inserted.

**Elites.** Each cell keeps its 2 strongest attacks (RainbowPlus). A new attack enters if the
cell has room or it beats the weakest elite. When a kept fix is simulated against an elite,
the elite records `fixed_by` and its re-measured `severity_after`; the cell's colour follows
the current plan, while the QD-score keeps what the search found.

**Metrics.** Coverage = filled cells / possible cells. QD-score = sum of elite severities.
`open_breaks` = cells whose strongest attack still breaks the current plan. `aim` = how many
gaps the model was asked to fill and how many its own attacks landed in.

## The loop (per round)

1. **Pick targets**: `ATTACKS_PER_ROUND` cells for menu attacks plus one for the scenario
   script — empty cells first, spread over rows and columns, then the weakest filled ones.
2. **Propose**: the red-team prompt gets one short line per target ("Exit blocked · Near West
   stairwell: event block_exit; exits stair_w"). With no model, or a replay-cache miss, the
   rule generator stages one attack per target cell (`rule_attacks_for_cells`). In the default
   hybrid mode the rules also fill the targets the model missed, so they compete.
3. **Screen** with the instant estimate and **simulate** at most `ATTACKS_PER_ROUND` menu
   attacks plus one script (the same simulation budget as before): aimed gaps first, then
   other gaps, then candidates that would enter their cell, then the highest estimate.
   Candidates screened out are logged and may be proposed again later.
4. **Insert** each simulated attack into the map (`archive` event).
5. **Blue team** fixes the worst breaks that are elites of the map, as before; kept fixes
   update the elites they were measured against.
6. A round without breaks no longer ends the session while the map still has gaps.

Budgets (rounds, runs, tokens, wall clock) are unchanged and still end the session gracefully.

## Where it shows

- `archive` session events (full snapshot each time), `summary.archive`, and
  `GET /api/v1/sessions/{id}/archive` (contract `FailureMap` in `api/models/failure_map.py`).
- **Failure map** tab in the red-team panel: rows with icons, columns per place, colour by
  severity with an icon and the number in every cell (colour is never the only signal), dashed
  gaps; clicking a cell shows its elites' numbers and opens the attack's simulation.
  `FailureMap` is exported for other views.

## Live check (2026-10-18)

One session per template, in-process: Nemotron 3 Super (OpenRouter free tier, spare key on a
429), the mock sandbox (scaled instant estimates, no Docker), `MAX_ROUNDS=2`,
`ATTACKS_PER_ROUND=3`, `FIX_TARGETS=1`, hybrid agents. "Before" is the same session on the
base commit (no map), its simulated attacks placed on the same grid with the same score
afterwards. 31 live model calls in all.

| Template | Version | Round 1: cells · coverage · QD | Round 2: cells · coverage · QD | Hazard kinds |
| --- | --- | --- | --- | --- |
| school_wing (14 cells) | before | 4 · 29% · 3.96 | 4 · 29% · 4.62 (1 new attack; stopped: no new breaks) | 4 of 6 |
| school_wing | failure map | 4 · 29% · 3.37 | 8 · 57% · 6.15 | 6 of 6 |
| conference_hall_2f (11 cells) | before | 4 · 36% · 8.01 | 5 · 46% · 9.80 (1 attack off the map) | 4 of 6 |
| conference_hall_2f | failure map | 4 · 36% · 7.59 | 7 · 64% · 15.59 | 6 of 6 |

Without the map the model repeated its round-1 ideas in round 2 (same blocked stairwell, same
surge), which the duplicate check dropped. Aimed at gaps, it wrote attacks for the empty cells:
its own attacks landed in 7 of 8 aimed cells on the school and 5 of 8 on the hall, and the
rules filled the rest. Round 1 is slightly weaker (the search spreads before it deepens).
These numbers come from the mock sandbox, so they show the search behaviour, not the venues'
real risk.

## Honest limits

- Severities of elites from earlier rounds were measured on the plan as it was then; only
  elites a kept fix was simulated against are re-measured.
- With the mock sandbox the numbers are scaled instant estimates (labelled as such), and the
  instant estimate cannot model misdirection or scripts, so those cells score near the
  baseline there; only a real simulation shows their effect.
- Tier 1 screening still decides which candidates are simulated, so a gap can stay empty when
  every candidate for it looks weak in the estimate.
