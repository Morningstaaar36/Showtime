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

One designer call builds the venue (replayed from the LLM cache in `record_replay` mode). The
test then needs no model: `agents: "rules"` (rule-based what-ifs and fixes), `judge: false` (the
computed summary is kept), one round of two what-ifs, two fixes for the worst, what-ifs at tier 2
(`api/orchestrator/real_cases.py`, `CASE_TEST`). Its baseline is the case as it happened; the
fixes are what Showtime would have suggested. A case opened before opens its existing project.

## Results

Simulated with JuPedSim (tier 3, seed 42, 0.025 s step) on 23 Oct 2026, on the venues the solver
builds from the scripted designer replies in `api/tests/fixtures/real_cases/` (what a model
plausibly writes for each description). The instant estimate (tier 1, a flow formula) is shown
for comparison. Live designer runs were not possible on 25 Oct: the hosted model (Nemotron 3
Super on OpenRouter's free tier) returned 404 from its provider for both keys, and Docker was
down for a re-run; see *Gaps*.

| Case | Peak density | Time above 5 /m² | Where | Where the real crush was |
|---|---|---|---|---|
| Love Parade 2010 | **5.7 /m²** (tier 1: 5.4) | 183 s of 542 s | foot of the ramp, west side, by the narrow staircase and the tunnel mouth (x 51.5, y 24.5) | between the staircase and the tunnel entrance at the foot of the ramp: **same place** |
| Hillsborough 1989 | **10.8 /m²** (tier 1: 5.4) | 894 s of 900 s; 2,763 of 3,000 still in the pens at the end | front of the pens at the perimeter gate of pen 4 (x 7.5, y 14.5) | the front of pens 3 and 4 against the perimeter fence, most deaths in pen 3: **same zone, other pen** |
| Itaewon 2022 | not yet simulated (tier 1: 5.4) | tier 1: 63 s | tier 1 puts it at the Itaewon-ro exits, not in the alley | in the alley: **not shown yet** |

### Love Parade 2010, Duisburg (24 July 2010; 21 dead, more than 500 injured)

Sources: Helbing & Mukerji (2012), *Crowd disasters as systemic failures: analysis of the Love
Parade disaster*, EPJ Data Science 1:7, <https://doi.org/10.1140/epjds7> (preprint
<https://arxiv.org/abs/1206.5856>), which also summarises G. K. Still's expert report.

Dimensions used: tunnel about 20 m wide (smallest width); one ramp 26 m wide and 130 m long, the
only way in and out; usable width 10.59 m at two triangular fence structures; flows 15:00–15:40 of
450–750 people per minute in and 40–250 out; most victims between the narrow staircase and the
tunnel entrance.

Approximations: 126 m of tunnel drawn; ramp flat; staircase 1.5 m wide and fence position and
length estimated; 3,000 people (1,150 + 1,150 arriving, 700 leaving: 30 % of the inflow, inside
the published range) for a crowd of tens of thousands; police cordons not modelled.

Run: everyone reached an exit (2,300 the festival grounds, 430 the west tunnel end, 270 the
staircase); warning density for 300 s. With arrivals only (no one leaving) the same layout
peaked at 5.0 /m² at the same corner: the meeting of the two flows is what pushed it into danger.

### Hillsborough 1989, Sheffield (15 April 1989; 97 dead)

Sources: Lord Justice Taylor, *The Hillsborough Stadium Disaster, Interim Report* (1989, Cm 765);
HSE, G. Norton, *An investigation into the number of people in pens 3 and 4* (1989); Wikipedia,
*Hillsborough disaster* (official toll of 97). Links in `api/data/real_cases.json`.

Dimensions used: tunnel about 23 m long, 1 in 6 down to the terrace, its mouth bisected by the
radial fence (Taylor ¶45); perimeter gates 0.82 m (pen 3) and 0.79 m (pen 4) (¶260); pen areas
about 188 and 192 m² (HSE table 2); about 2,000 through gate C in five minutes (¶70); 1,576
people in pen 3 at 15:03, 8.4 /m² (HSE).

Approximations: pens as two 12.5 × 15 m rectangles, crush barriers not drawn; tunnel width
4.3 m (press reports, not the inquiry) and concourse size estimated; flat; pens start at 600
each (the simulator cannot place more than 4 /m² at the start; they were above 5.4 /m² by 14:50)
with 1,800 arriving; the 0.79 m gate drawn 0.8 m; gates open from the start.

Run: only 237 people left through the two gates in 15 minutes; the peak cell is at the pen 4
gate. The front of both pens is where the danger is, as in the inquiry, but this run does not
single out pen 3.

### Itaewon 2022, Seoul (29 October 2022; 159 dead, 196 injured)

Sources: Wikipedia, *Seoul Halloween crowd crush* (alley about 45 m long, 3.2 m at its narrowest,
sloping up from Itaewon-ro); AP via The Boston Globe, 13 Jan 2023 (police special investigation:
about 8 people per m² at 22:15, 9–11 at 22:25).

Approximations: the upper street (6 m) and Itaewon-ro (12 m) widths and the 80 m drawn of each
are estimates; the alley is 3.2 m over its whole length and flat; who walks which way is an
assumption (1,600 down, 800 up); 2,400 people.

No JuPedSim result yet. The instant estimate finds its peak at the Itaewon-ro exits, not in
the alley: a flow formula does not model two crowds meeting head-on, which is the mechanism
here, so this case needs the simulator before it can be said to show the danger.

## Gaps

- The venues above come from scripted designer replies, not yet from the live model; the
  live run (one call per case) still has to be recorded into the LLM cache and checked against
  the dimensions listed here.
- Itaewon has no simulator result yet.
- Slopes, crush barriers, falls and police cordons are not modelled; the crowd is capped at
  3,000 simulated people.
- Jamarat 2006, Mina 2015 and Astroworld 2021 were considered and left out: their published
  geometry is not enough to describe the site credibly.
