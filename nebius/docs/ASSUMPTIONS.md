# Assumptions and default values

Every number that shapes a result, where it comes from, and how to change it. Values are set in
`.env` (see `.env.example`) or in **Settings**; the report prints the same table
(`api/core/assumptions.py`).

| Item | Default | Source / reasoning | Setting |
| --- | --- | --- | --- |
| Free walking speed | 1.34 ± 0.26 m/s, 5% slow walkers at 0.7 m/s | Weidmann (1993); SFPE Handbook of Fire Protection Engineering, ch. 59 (Gwynne & Rosenbaum) | `WALK_SPEED_MEAN`, `WALK_SPEED_SD` |
| Body radius | 0.22 m | Calibrated: at 0.22 m the model's jam density matches Weidmann's 5.4 people/m² and door flow is 1.1–1.5 people/m/s (measured, `docs/PROGRESS.md`) | `AGENT_RADIUS` |
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
| Multi-floor | Upper floor first; stair queue; people re-enter at the stair bottom | Approximation of stair flow; stairs are not walkable ramps | — |
| Tier 1 queue density | D = 1.9 + 3.5·(1 − e^(−Q/150)) people/m² | Screening formula between SFPE capacity density (1.9) and Weidmann jam density (5.4); calibrated on Tier 3 | — |
| Wind pressure | q = 0.613·Kz·Kzt·Kd·V², Kz 1.0, Kzt 1.0, Kd 0.85, G 0.85, uplift 0.8, roof dead load 0.25 kN/m² | ASCE 7 velocity pressure form; screening only | plugin config |
| Stage wind limit | Lowest gust for uplift, sliding or overturning of a ballasted frame | Pynite linear frame; reactions scale with V² | stage parameters |
| Weather | Hourly `wind_gusts_10m` (m/s) from Open-Meteo forecast; ERA5 archive for past dates | Reanalysis smooths thunderstorm downbursts (Indiana 2011: ERA5 shows 9 m/s vs ~26 m/s measured) | manual gust input |
| Real-place headcount when not given | 1.0 people/m² indoors, 1.5 open-air (of open floor) | Mid-range planning densities; always shown as an assumption to change | form field |
| Real-place path widths when not mapped | footway 3 m, pedestrian 6 m, service 4 m, residential 6 m, main roads 8 m; tag `width` wins | Typical urban widths; check on site | `_PATH_WIDTH_M` |
| Real-place narrow gaps | Gaps under 1.2 m between buildings, fences, water and the edge are closed; pockets without an exit are filled | Nobody plans egress through a 1 m slot between buildings; the crowd model would route people into it | `GAP_CLOSE_M` |
| Designed venues | Margins 1.5 m (less in small rooms), 2 m clear in front of a stage, features ≥ 3 m from exits, balcony 4.5 m up with a 9 m stair | Solver defaults; every value the AI assumed is listed in the preview | `api/core/venue_builder.py` |
| T-alley template | Alley 3.2 m wide, 45 m long | Wikipedia, "Seoul Halloween crowd crush" (sources vary 3.2–4 m; we use 3.2 m) | template |

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
