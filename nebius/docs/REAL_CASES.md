# Real cases: documented crowd disasters, rebuilt and simulated

Home › *Events like yours* › **Learn from real cases** shows one tile per case. A tile sends the
case's sourced description to the Designer agent (the same path as an organizer's sentence:
`POST /api/v1/real_cases/{id}/open`), saves the venue it builds, and starts a test right away.
The case's facts and sources travel with the venue (`extensions.real_case`), so Your plan ›
Overview shows a compact card: what happened, the sources as links, and where this simulation
put its peak density.

Nothing about the sites is hand-drawn. `api/data/real_cases.json` holds, per case, a plain
description (shape, widths, lengths, gates, crowd, who walks where), the sources, the dimensions
taken from them and what is approximate. The designer writes a `VenueSpec` and the solver
(`api/core/venue_builder.py`, `api/core/venue_parts.py`) computes the geometry.

**A reconstruction is not a forensic finding.** It uses published dimensions and a small,
simplified crowd (at most 3,000 simulated people). It shows that the layout and the flows
produce dangerous density in the same place; it does not reproduce the forces, the falls or
the timeline of the day, and it says nothing about anyone's responsibility.

## What the designer gained for these cases (useful for any venue)

| Spec field | What it draws | Case that needs it |
|---|---|---|
| `passages[]` | a tunnel, ramp, alley or access road joined to a wall of the main floor, with its own exits (sides or far end) | Love Parade ramp, Hillsborough tunnel, Itaewon alley |
| `passages[].narrowing` | fences or stalls from both sides leaving a clear width | Love Parade fences (10.6 m) |
| `passages[].end_area` | an open area at the far end (concourse, the street an alley leads to) with its own exits | Hillsborough concourse, Itaewon-ro |
| `dividers[]` | a fence across the whole floor, splitting it into pens | Hillsborough radial fence |
| `zones[].area` / `zones[].heading` | people standing in a passage, and the exits they walk to | arrivals vs. leavers (Love Parade), two-way flow (Itaewon) |

`heading` becomes `Zone.exit_ids` in the venue; the instant estimate (`api/core/tier1.py`) and
therefore the simulator's exit plan send those people only to those exits. Ramps are drawn flat.

## The test that starts when a case opens

The Designer agent builds the venue from the case's description (one call, replayed from the LLM
cache in `record_replay` mode). The test that follows is the normal AI-designed one: the red team
attacks the case as it was, the blue team proposes fixes, the simulator confirms them and the
judge writes the verdict; the rules stand in only when no model answers
(`api/orchestrator/real_cases.py`, `CASE_TEST`). Its baseline is the case as it happened; the
fixes are what Showtime would have suggested. A case opened before opens its existing project; a
case whose first build needed fixes is built again the next time it is opened (or tested as it
stands, if someone edited it since).

## Results (live, 25 October 2026)

Built live by **Nemotron 3 Ultra** (OpenRouter, free tier) from the descriptions in
`api/data/real_cases.json`, then simulated with JuPedSim (tier 3, seed 42) on the as-it-happened
venue. Numbers are the simulator's; "where" is the densest cell of the run.

| Case | What the AI built | Peak density | Time above 5 /m² | Where | Where the real crush was |
|---|---|---|---|---|---|
| Itaewon 2022 | both streets side by side on one floor, with a 3.2 × 45 m alley leading off them to a 3 m opening (not quite the site: see below); 1,200 + 400 people heading for Itaewon-ro, 800 for the upper street | **5.7 /m²** | 98 s | at the top of the alley, where the crowd squeezes into it, 31 s in | in the alley, between the T-junction and Itaewon-ro: **near the same place** |
| Love Parade 2010 | a 26 m ramp, 130 m long, with the fences narrowing it to 10.6 m, above a tunnel with exits at both ends; 2,300 arriving heading up, 700 leaving heading down | **5.5 /m²** | 56 s | the foot of the ramp, west side, 132 s in | between the staircase and the tunnel at the foot of the ramp: **same place** |
| Hillsborough 1989 | the Leppings Lane terrace split into pens by the radial fence, perimeter gates of 0.8 m, the tunnel from the concourse | **9.9 /m²** | 894 s of 900 s; 2,788 of 3,000 still inside at the end | at the gate of pen 3, 133 s in | the front of pens 3 and 4 against the perimeter fence, most deaths in pen 3: **same place** |

The red team's attacks broke every case further (three of three in each, except where the
baseline already failed), and no fix the blue team proposed was kept in these one-round tests:
none removed the break without making another outcome worse.

**What it took to get there** (each fixed in the tools, not by drawing the sites):
- Nemotron 3.5 Lightning misread the long descriptions (it drew Itaewon as one 80 × 170 m
  street); Nemotron 3 Ultra got them right, so the reasoning agents now run on Ultra
  (`MODEL_MAIN`), as the hackathon suggests for serious reasoning.
- A crowd's heading has to reach the simulator: "Tunnel" now matches "West tunnel end" and
  "East tunnel end", "heading for the ramp" means the ramp's ways out, and a heading that
  matches nothing is sent back to the model instead of being dropped. Without the headings,
  everyone at Love Parade walked to the nearest tunnel end and no crush formed.

**Approximations to know:**
- Itaewon: the live build put the upper street and Itaewon-ro side by side on one floor instead
  of at the two ends of the alley, so the alley is not the only way between them (the crowd can
  also walk to the street's own ends). The danger still forms where the crowd squeezes into the
  alley; a build that places the streets at both ends of the alley is the next step.
- Love Parade: the tunnel runs north–south (26 × 126 m) instead of west–east (126 × 20 m); the
  ramp, its narrowing and where the two flows meet are as described.

The earlier runs on scripted designer replies (23 October) gave the same places: Love Parade
5.7 /m² at the foot of the ramp, Hillsborough 10.8 /m² at the front of the pens.

## Gaps

- One live build per case so far (Itaewon's streets not yet placed at both ends of the alley); a model can answer differently next time (the replies are
  recorded in the LLM cache, so the app replays the ones above).
- Slopes, crush barriers, falls and police cordons are not modelled; the crowd is capped at
  3,000 simulated people.
- Jamarat 2006, Mina 2015 and Astroworld 2021 were considered and left out: their published
  geometry is not enough to describe the site credibly.
