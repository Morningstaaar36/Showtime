# ADR 0003: Three simulation tiers

**Status:** accepted · 2026-10-08

## Decision
- **Tier 1 (instant estimate):** geodesic grid distances, min-cost-flow exit assignment, fluid queues. 2–4 ms. Powers "Break it yourself", attack ranking and the exit plan handed to the simulator.
- **Tier 2 (ranking run):** JuPedSim stopped at 180 s, Δt 0.05 s. Ranks attacks and fixes.
- **Tier 3 (confirmed by simulation):** full JuPedSim run, Δt 0.025 s (≤ 2,500 people) or 0.05 s.

The UI always labels which tier a number comes from. Tier 1 / Tier 3 ratios per template are measured (`make calibrate`) and printed in reports.
