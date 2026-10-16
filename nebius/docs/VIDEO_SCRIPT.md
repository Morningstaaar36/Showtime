# Demo video script (S-10 / P1-04)

Owner: Saif. Status: **script ready; not recorded or published yet.** It needs Shahraz's live
Nebius runs (N-04: their run ids go in the table at the end) and a person to record and upload
it to YouTube (public). Three minutes at most; say "NVIDIA Nemotron" and "Nebius" out loud.

## Before recording

- `make use-nebius`, key in `.env`, `make smoke-nebius` green; `make up`; header badge NEBIUS.
- Load the precomputed demos (`make demo-precompute`): the 4-storey hospital
  (`hospital_4f`) and the T-shaped alley replay offline if the network fails.
- 1600 × 900 window, light theme, browser zoom 100%, notifications off, cursor highlight on.
- Rehearse once; keep the live test for the take (free keys and budgets are limited).

## Shots (≈ 2 min 50 s)

| Time | Screen | What happens | Voice-over |
| --- | --- | --- | --- |
| 0:00–0:15 | Home | Title, the three steps | "Crowd crushes happen about once a month. Showtime lets any organizer test a plan before the gates open." |
| 0:15–0:40 | Pick it on the map | Draw an area → Building, 4 floors, Hospital, Rooms → Build venue | "Any building from the map: here a four-storey hospital, with wards, two stairwells and the people who are really there: patients in beds, wheelchair users, staff." |
| 0:40–0:55 | Check your venue | Floor switcher: one floor alone; type a headcount; a zone's people mix | "Check the doors and the crowd in a minute; every change is a saved version you can undo." |
| 0:55–1:25 | AI tests it | Test this plan; the steps and the attack cards | "NVIDIA Nemotron on Nebius Token Factory plays the red team: it invents what could go wrong, citing real incidents, and writes scenarios as code. Each one runs as a real crowd simulation in a Nebius Sandbox." |
| 1:25–1:55 | Your plan | Verdict and its one-line reason; "Every scenario the AI tested"; click the attack that broke the plan; caption "… blocked at 1:00"; people on each floor | "A supported weakness: <say the attack and the number the screen shows, e.g. the stair lost at 1:00 and the 95% time it causes>." |
| 1:55–2:20 | Your plan | What the AI suggests: the fix with its own test; before / after replay | "The blue team proposes a feasible fix; the simulation, not the model, decides if it is kept. Before and after, side by side." |
| 2:20–2:35 | Your plan | Check with more seeds: the range | "Every number comes from simulations, with its range over several random crowds." |
| 2:35–2:50 | Your plan | Accept these changes; Download checklist; the cost card | "Accept, hand the checklist to your stewards. This test cost <the cost card's amount> of Nemotron tokens." |
| 2:50–3:00 | Home | "Planning aid, not a safety certification." | "Showtime. Run the disaster before the gates open." |

## Evidence to show (fill in from N-04)

| Item | Run / session id | Provider | Notes |
| --- | --- | --- | --- |
| Live red-team session on the hospital | | Nebius Token Factory + Sandboxes | |
| The attack that broke the plan | | | |
| The kept fix (before / after runs) | | | |
| Seed range | | | |

Rules for the cut: no numbers the screen does not show; no claim of "confirmed" unless the badge
says so; keep the planning-aid notice on screen at the end.
