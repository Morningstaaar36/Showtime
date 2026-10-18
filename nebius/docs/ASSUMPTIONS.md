# Assumptions and default values

Every number that shapes a result, where it comes from, and how to change it. Values are set in
`.env` (see `.env.example`) or in **Settings**; the report prints the same table
(`api/core/assumptions.py`).

| Item | Default | Source / reasoning | Setting |
| --- | --- | --- | --- |
| Free walking speed | 1.34 ± 0.26 m/s, 5% slow walkers at 0.7 m/s | Weidmann (1993); SFPE Handbook of Fire Protection Engineering, ch. 59 (Gwynne & Rosenbaum) | `WALK_SPEED_MEAN`, `WALK_SPEED_SD` |
| Body radius | 0.22 m | Calibrated: at 0.22 m the model's jam density matches Weidmann's 5.4 people/m² and door flow is 1.1–1.5 people/m/s (measured, `docs/PROGRESS.md`) | `AGENT_RADIUS` |
| Time gap to the person ahead | 0.25 s | Calibrated on the Jülich 2006 bottleneck series (widths 0.9, 1.1, 1.4, 1.8, 2.2 m), held-out median absolute error 4.4%; the model default 1.0 s gave −55% flow (`docs/VALIDATION.md`) | `AGENT_TIME_GAP` |
| Door/gate capacity (instant estimate) | 1.3 people per metre per second | SFPE maximum specific flow for doors and corridors | `SPECIFIC_FLOW` |
| Stair travel and throughput | 0.6 m/s along the stair, 1.0 people/m/s | Conservative values below SFPE stair flows; stairs are a FIFO queue (approximation) | `STAIR_SPEED`, `STAIR_FLOW` |
| Warning density | 3.5 people/m² | Fruin level of service F begins near 2.2/m²; 3.5 marks dense, restricted movement | `DENSITY_WARN_PPM2` |
| Danger density | 5 people/m², sustained ≥ 5 s | Still (2014): crush risk rises sharply above about 5/m²; persistence filter removes single-frame peaks | `DENSITY_DANGER_PPM2`, `DANGER_MIN_DURATION_S` |
| Density measurement | 1 m grid, Gaussian smoothing σ = 0.8 m, divided by walkable fraction | Comparable to a 2–3 m² measurement area | — |
| Evacuation target without a hazard | Indoor 5 min, open-air 8 min (× safety factor) | Planning targets, not code limits; open-air follows UK Green Guide 8-minute egress practice | `TARGET_EVAC_INDOOR_S`, `TARGET_EVAC_OUTDOOR_S` |
| Pre-movement time | 60 s | Typical for alerted, awake audiences; set per event | `PRE_MOVEMENT_S` |
| Safety factor | 1.5 | Common engineering margin on egress time | `SAFETY_FACTOR` |
| Crowd model | JuPedSim collision-free speed model, Δt 0.025 s (≤ 2,500 people) or 0.05 s | Tordeux et al. (2016). Δt 0.05 s is ~8% conservative vs 0.01 s on the 1,200-person hall | — |
| Deadlock handling | Door "squeeze" (radius 0.15 m after 4 s without flow) and 1 m sidestep for isolated deadlocks | Known artefact of collision-free models; bodies compress under pressure. Dense jams are left alone | — |
| Door model | 0.6 m passage through the wall; people standing in a doorway leave through it | Prevents side-entry and doorway "plugs" (measured, `docs/PROGRESS.md`) | — |
| Multi-floor | Each floor runs before the floors its stairs lead to (top down; a basement before street level); stair queue; people re-enter at the far landing | Approximation of stair flow; stairs are not walkable ramps; climbing out of a basement uses the same stair speed as going down | — |
| Tier 1 queue density | D = 1.9 + 3.5·(1 − e^(−Q/150)) people/m² | Screening formula between SFPE capacity density (1.9) and Weidmann jam density (5.4); calibrated on Tier 3 | — |
| Wind pressure | q = 0.613·Kz·Kzt·Kd·V², Kz 1.0, Kzt 1.0, Kd 0.85, G 0.85, uplift 0.8, roof dead load 0.25 kN/m² | ASCE 7 velocity pressure form; screening only | plugin config |
| Stage wind limit | Lowest gust for uplift, sliding or overturning of a ballasted frame | Pynite linear frame; reactions scale with V² | stage parameters |
| Weather | Hourly `wind_gusts_10m` (m/s) from Open-Meteo forecast; ERA5 archive for past dates | Reanalysis smooths thunderstorm downbursts (Indiana 2011: ERA5 shows 9 m/s vs ~26 m/s measured) | manual gust input |
| Real-place headcount when not given | 1.0 people/m² indoors, 1.5 open-air (of open floor) | Mid-range planning densities; always shown as an assumption to change | form field |
| Real-place path widths when not mapped | footway 3 m, pedestrian 6 m, service 4 m, residential 6 m, main roads 8 m; tag `width` wins | Typical urban widths; check on site | `_PATH_WIDTH_M` |
| Real-place narrow gaps | Gaps under 1.2 m between buildings, fences, water and the edge are closed; pockets without an exit are filled | Nobody plans egress through a 1 m slot between buildings; the crowd model would route people into it | `GAP_CLOSE_M` |
| Designed venues | Margins 1.5 m (less in small rooms), 2 m clear in front of a stage, features ≥ 3 m from exits, balcony 4.5 m up with a 9 m stair | Solver defaults; every value the AI assumed is listed in the preview | `api/core/venue_builder.py` |
| Designed buildings | Storeys 3.5 m apart unless the description says otherwise; stairs 1.2 m wide, two near the ends when none are named; an exit on a basement is a stair up to a street door on that wall; an atrium void spans 30% of the width and depth on the upper floors; escalators are obstacles, not ways out | Solver defaults (the model chooses storeys, stairs and headcounts per level; the solver computes the geometry) | `api/core/venue_builder.py`, `api/core/building_gen.py` |
| T-alley template | Alley 3.2 m wide, 45 m long | Wikipedia, "Seoul Halloween crowd crush" (sources vary 3.2–4 m; we use 3.2 m) | template |
| Sensitivity: headcount | Every zone × 0.8 and × 1.2 | Planning bracket set by the team (R-02 in `TEAM_TASK_ALLOCATION.md`), not a published forecast error: headcounts on the day differ from the plan both ways | `api/orchestrator/sensitivity.py` (`VARIANTS`) |
| Sensitivity: walking speed | Free walking speeds × 0.85 and × 1.15 (level mean and spread, stairs) | Planning bracket set by the team (R-02). It stays inside the spread of the default itself (1.34 ± 0.26 m/s, about ±19%, Weidmann) | `api/orchestrator/sensitivity.py` (`VARIANTS`) |

## Sensitivity: how sure Your plan's numbers are

The headcount and the walking speed are estimates, so a single run is one answer to inputs that
could be different on the day. **Check the range** on Your plan repeats the run the verdict rests
on four more times, changing one assumption at a time:

| Run | What changes | What stays |
| --- | --- | --- |
| As tested | nothing (reused when it can be rebuilt exactly) | — |
| 20% fewer / 20% more people | every zone's headcount (`scale_people`, total kept exact) | seed, layout, attack, fixes, walking speed |
| Walking 15% slower / faster | `walk_speed_mean`, `walk_speed_sd` and `stair_speed`, from the start | seed, layout, attack, fixes, headcount, door and stair flow capacities |

- **Which run is repeated.** The after-fixes run under the worst attack; the run of the chosen
  changes together when only some were accepted (see below); the baseline when nothing was kept.
- **What the range covers.** Min–max and median of evacuation time (95%), peak density and people
  still inside, over the runs that finished, the plan as tested included. Runs that did not finish
  stay listed with their reason and are left out, with a note.
- **Verdicts.** Each run is judged by the red team's break rules (`break_reasons`: evacuation time
  × safety factor against the target, sustained danger density, people trapped or still inside).
  "Holds under every assumption tested" is only said when all five runs finished and none broke.
- **Limits.** One assumption changes at a time (no combined worst case); surges and counterflows in
  an attack keep their own numbers; the exit plan is recomputed for the new headcount. Speed
  changes apply from the start; slowdowns *during* the event are attack events, not this check.

## Accepting only some changes: tested together first

A test confirms the complete set of kept changes under its worst attack. A subset was never
simulated as a whole, and changes interact (a wider door and marshals sending people to it), so
accepting a subset starts one more run: the tested venue with only the chosen change bundles and
their operational measures, under the same worst attack, tier and seed as the after-fixes run.

- Until that run finishes as a simulation the version stays **not tested together** (Your plan and
  the handover checklist say so). A failed run, or a preview from the mock sandbox, keeps it that
  way with the reason, and can be started again.
- Once it ran, the version is **tested together** and the run's evaluation compares it with the
  test's before run by the session rules: *confirmed* only when both are full simulations that ran
  to the end, *partly confirmed* when one stopped early.

## Simulator validation (`make validate`, `docs/VALIDATION.md`)

The validation against the Jülich 2006 bottleneck experiment uses **the app defaults above,
unchanged** (radius 0.22 m, walking speed 1.34 ± 0.26 m/s with 5% slow walkers, Tier 3 Δt 0.025 s,
4 frames/s output, collision-free speed model with the squeeze and sidestep rules). No parameter
was tuned to fit the experiment, so there is no before/after pair to report: the published error
(median 55% lower flow than measured) is the app as shipped. If a parameter is ever changed to
improve the fit, record it here with the error before and after.

Assumptions that apply only to the validation venue (also listed in `api/data/validation.json`):

| Item | Value | Why |
| --- | --- | --- |
| Holding area | Full corridor width (7 m), ending 4 m before the entrance, depth for 3.3 people/m² (7.3–7.7 m) | Size not given in the metadata or the 2006 papers; 3.3/m² is the initial density of the same group's 2005 series (Seyfried et al. 2009) |
| After the bottleneck | Open area 8 m × 1 m, exit along its far edge | The metadata's bounding box; the exit must not limit the flow |
| Start | Everyone starts walking at t = 0 | Reaction times were not published; the steady-state window skips the first 9 people |
| Positions | Experiment: head positions at 25 fps; simulation: body centres at 4 fps | Archive format and app default output rate |
