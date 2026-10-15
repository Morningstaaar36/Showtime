# Simulator validation: Jülich bottleneck experiment (2006)

**Result: with the calibrated time gap (0.25 s, now the app default) the simulator's flow through
a bottleneck is within about 6% of the real crowd's at every width; median absolute error
4.0%. On the widths held out from calibration the median absolute error is 4.4%.**
With the model's out-of-the-box time gap (1.0 s) the simulator let only about half as many people
through (median error −55%); that first result is kept below for the record.

## What was compared

- **Experiment:** Jülich pedestrian dynamics archive, *Bottleneck, Caserne*: Bergische Kaserne
  Düsseldorf, 2006, with soldiers told to walk normally. DOI
  [10.34735/ped.2006.2](https://doi.org/10.34735/ped.2006.2), CC BY 4.0. The experiments were
  funded by the DFG (projects KL 1873/1-1 and SE 1789/1-1). Setup and analysis are described in
  Seyfried et al., *Enhanced empirical data for the fundamental diagram and the flow through
  bottlenecks*, PED 2008 (Springer 2010), [arXiv:0810.1945](https://arxiv.org/abs/0810.1945),
  and in Liddle et al., [arXiv:0911.4350](https://arxiv.org/abs/0911.4350). The group's method
  for bottleneck flow is in Seyfried, Rupprecht, Passon, Steffen, Klingsch, Boltes, *New insights
  into pedestrian flow through bottlenecks*, Transportation Science 43 (2009) 395–406,
  doi:[10.1287/trsc.1090.0263](https://doi.org/10.1287/trsc.1090.0263) (arXiv physics/0702004).
- **Runs:** the width series b090–b250 (b = 0.9–2.5 m, bottleneck length l = 4 m, 170–179
  people, corridor 7 m wide, holding area 4 m before the entrance). Every number is taken from
  the archive metadata (`parameters` and `wkt_geometry`, which the script checks against each
  other). Trajectories: head positions at 25 fps, in cm, with the bottleneck entrance on y = 0.
- **Simulator:** the Showtime sim image (JuPedSim 1.4.2, collision-free speed model) through
  the app's own runner (`RunService` → `DockerRunner`), at Tier 3 with **all app defaults**:
  radius 0.22 m, walking speed 1.34 ± 0.26 m/s with 5% slow walkers, Δt 0.025 s, 4 fps output,
  squeeze and sidestep rules on. 3 seeds per width (1, 2, 3), each deterministic.

## How the flow is measured

The experiment and the simulation are measured by the same code: `sim/bottleneck_flow.py`,
which runs as a code job in the sim image with PedPy 1.5.1.

1. PedPy `compute_n_t` gives each person's crossing frame on the line across the bottleneck
   entrance (y = 0, x from −b/2 to b/2).
2. The crossings are sorted in time. The steady window runs from the 10th to the 150th crossing:
   the first 9 people walk into an empty bottleneck, and Liddle et al. compute the flow from
   "the first 150 people".
3. Flow J = (150 − 10) / (t₁₅₀ − t₁₀) people/s, that is, 1 / mean time gap (Seyfried et al. 2009,
   eq. 3). Specific flow J_s = J / b.
4. Error = (simulated median − measured) / measured.

Check on experimental scatter: run l4 repeats the b120 setup. It gives 2.36 /s against 2.40 /s
for b120 with the same method, a difference of about 2%.

## Results

### Calibration (time gap to the person ahead)

The collision-free speed model keeps a time gap to the person in front; JuPedSim's default is
1.0 s. Calibrated on five widths (0.9, 1.1, 1.4, 1.8, 2.2 m; seed 1), then tested on the other
five (1.0, 1.2, 1.6, 2.0, 2.5 m; seeds 1–3):

| time gap | calibration widths: median error | held-out widths: median absolute error |
| --- | --- | --- |
| 1.0 s (model default) | −55% (all widths) | — |
| 0.6 s | −40.0% | — |
| 0.5 s | −32.2% | — |
| 0.4 s | −23.2% | — |
| 0.3 s | −8.6% | — |
| **0.25 s (chosen)** | **−0.5%** (median abs 2.5%) | **4.4%** |
| 0.2 s | +10.1% | — |

### With the calibrated default (published in `api/data/validation.json`, seeds 1–3)

| b (m) | run | people | measured (1/s) | measured J_s (1/(m·s)) | simulated median (min–max) (1/s) | simulated J_s | error |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.9 | b090 | 170 | 1.62 | 1.80 | 1.61 (1.59–1.85) | 1.79 | -0.5% |
| 1 | b100 | 178 | 1.93 | 1.93 | 1.93 (1.79–1.96) | 1.93 | +0.0% |
| 1.1 | b110 | 179 | 2.09 | 1.90 | 2.08 (2.07–2.15) | 1.89 | -0.5% |
| 1.2 | b120 | 178 | 2.40 | 2.00 | 2.30 (2.28–2.32) | 1.91 | -4.4% |
| 1.4 | b140 | 176 | 2.81 | 2.01 | 2.69 (2.58–2.72) | 1.92 | -4.2% |
| 1.6 | b160 | 178 | 3.01 | 1.88 | 3.20 (3.18–3.22) | 2.00 | +6.2% |
| 1.8 | b180 | 176 | 3.76 | 2.09 | 3.61 (3.61–3.71) | 2.01 | -4.0% |
| 2 | b200 | 178 | 3.77 | 1.89 | 4.00 (3.84–4.06) | 2.00 | +6.1% |
| 2.2 | b220 | 177 | 4.44 | 2.02 | 4.55 (4.31–4.63) | 2.07 | +2.5% |
| 2.5 | b250 | 176 | 5.45 | 2.18 | 5.23 (4.91–5.38) | 2.09 | -4.0% |

Median |error| **4.0%**; mean error -0.3%. The brief's target (median error ≤ 15%)
is met. Each seed's run id is in `api/data/validation.json`, served at `GET /api/v1/validation`
and shown in Help › *How good is the simulator?*.

### First result, model default (time gap 1.0 s)

| b (m) | measured (1/s) | simulated median (1/s) | error |
| --- | --- | --- | --- |
| 0.9 | 1.62 | 0.81 | −49.8% |
| 1.0 | 1.93 | 0.86 | −55.4% |
| 1.2 | 2.40 | 1.03 | −57.3% |
| 1.6 | 3.01 | 1.37 | −54.7% |
| 2.0 | 3.77 | 1.79 | −52.6% |
| 2.5 | 5.45 | 2.18 | −60.0% |

## Interpretation

- **Calibration fixed a constant factor, not the shape.** Both the real and the simulated flow grow
  linearly with width; the default time gap scaled the simulated flow down by about 2.2. One
  parameter, chosen on half the widths and checked on the other half, closes the gap. It is still
  one experiment with one population; other crowds (hurried, mixed ages) may differ.

- **The measured flows are plausible.** The specific flow is 1.8–2.2 people/(m·s), close to
  the J = 1.9·b line that Liddle et al. report for this series, and both grow roughly linearly
  with width.
- **The simulator's flow also grows linearly with width, but at about 0.87 people/(m·s).** So
  the error is a near-constant factor, not a breakdown at some width. This is what the
  collision-free speed model predicts with JuPedSim's default time gap of 1 s. A person keeps
  roughly one second of headway to the person in front, so each lane carries at most about one
  person per second. Real people in a jam accept much shorter gaps and zipper between lanes.
- **Direction:** times through bottlenecks come out too long, by a factor of about 2 for these
  conditions. This is cautious for planning. It is not a calibrated safety margin, because
  real crowds (and other layouts) differ from these participants.
- **The app's own rules are part of the result.** The squeeze rule fired at t = 4 s in every
  run, before anyone had reached the exit: 9–15 people near the bottleneck got the 0.15 m
  radius. At b ≤ 1.2 m it also fired mid-run in 10 of the 12 runs, because the model briefly
  deadlocks. Both effects *raise* the simulated flow, so without them the gap would be larger.
- The app's door-flow figure of 1.1–1.5 people/(m·s) (ASSUMPTIONS, measured on short door
  passages) is higher than the 0.87 measured here in a 4 m long bottleneck with a wide approach.
  The two setups differ; this check covers the long bottleneck only.

## Limits

- No pushing forces. Simulated people steer around each other and never push; real crowds
  press and compress, especially under stress.
- Motivation is not modelled. The participants were asked to walk normally; hurried or
  competitive crowds flow differently (the 2005 series and others report higher flows).
- Density cap. Bodies are hard discs of 0.22 m, so the model cannot reach crush densities.
- One experiment, one population (young soldiers, 2006), one geometry type (a straight 4 m
  bottleneck behind a 7 m corridor).
- Assumed setup. The holding-area size is not published for this series. The venue assumes
  3.3 people/m² over the corridor width (see `docs/ASSUMPTIONS.md`). This affects how the
  jam forms, but not the steady flow that is compared.

## How to rerun

```bash
make get-data      # downloads metadata + trajectories into data/validation/bottleneck2006 (sha256-checked)
make build-sim     # or: docker build --platform linux/amd64 -t <tag> sim/ and SIM_IMAGE=<tag>
make validate      # 10 widths x 3 seeds, about 3 minutes; rewrites api/data/validation.json
```

Options (`scripts/validate_bottleneck.py`): `--runs b090 b120` picks widths, `--seeds 1 2 3`
picks seeds, `--people N` overrides the headcount (used by the slow test), and `--out PATH`
writes the JSON elsewhere. Runs are cached by content hash in a scratch database
(`cache/tmp/validate.sqlite`). Delete it to force fresh simulations; results are identical for
the same seed. Tests: `api/tests/test_validation.py` (contract, 3 seeds per width, geometry,
slow end-to-end test on one width with 40 people) and `web/src/panels/ValidationChart.test.tsx`.
