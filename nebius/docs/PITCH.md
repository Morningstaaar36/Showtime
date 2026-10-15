# Showtime: the pitch

**Will everyone get out safely? Test your event before the gates open.**

## Who it is for

Organizers of concerts, weddings, religious gatherings, university events and club nights, and
the permit offices that approve them. Large venues hire crowd-safety consultants with licensed
simulation software; most events can't, so they are planned by instinct.

## The problem

Crowd crushes happen at bottlenecks nobody tested: a narrow door, a blocked gate, people
pushing in while others leave. Itaewon (Seoul, 2022: 159 deaths in a 3.2 m alley) is still being
reconstructed with crowd models years later ([PLOS One 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11244771),
[Ewha kinodynamic reenactment](https://graphics.ewha.ac.kr/Crowd/), [open data](https://zenodo.org/records/10074509)).
Most guidance treats about 5 people per m² as the level where serious crush risk begins
([crowd risk guidance](https://eiai.ie/crowd-risk-analysis-and-crowd-safety/)).

## What Showtime does

1. **Your venue:** pick it on a map, describe it in one sentence, or open an example; check the
   doors, headcount and obstacles (drag and drop).
2. **AI red team, written as code:** Nemotron agents invent what could go wrong, grounded in 388
   real crowd incidents, and write new failures as small programs (for example "close the
   stairwell when its queue passes 40 people").
3. **Real crowd simulator:** every scenario runs in [JuPedSim](https://www.jupedsim.org)
   (Forschungszentrum Jülich) inside a sealed sandbox. Numbers come from the simulator, never
   from the AI.
4. **AI blue team:** proposes fixes; each fix is simulated again; the worst moment can be rewound
   and every response tried from that same second.
5. **Your plan:** an honest verdict ("confirmed" only when full simulations finished), the fixes
   you choose, an AI analyst that answers questions by running code on the results, a report and
   a printable handover checklist.

## Why sandboxes are essential

The AI writes code: disaster scenarios and data analyses. That code runs only in sealed,
disposable sandboxes (no network, read-only data, memory and time limits), locally in Docker and
in the cloud on Nebius. Snapshots let us save the crowd at the worst second and branch many
responses from it in parallel; stress tests fan out over parallel sandboxes. A script that tries
to reach the network is refused before it runs, and the sandbox has no network anyway.

## Evidence

- **Live runs** (OpenRouter Nemotron 3 Super + real JuPedSim): on a two-floor conference hall the
  red team broke the plan in 2 of 3 scenarios; the kept fixes cut peak density from 6.95 to 4.6
  people per m² and the 95% evacuation time from 4 min 39 s to 2 min 48 s, confirmed by full
  simulations with no one left inside. On a school wing the model wrote its own scenario script,
  which closed a stairwell at 25 s and rerouted 168 people; the analyst answered "longest queue
  13 people at 62 s" from code it ran.
- **Simulator check against real people:** on the Jülich bottleneck experiments (Seyfried et al.
  2009; doors 0.9–2.5 m, about 175 people each) the simulator's flow is within about 6% of the
  real crowd's at every width (median error 4.0%). One parameter, the time gap to the person
  ahead, was calibrated on half the widths and checked on the other half (held-out error 4.4%);
  with the model's default the simulator let only half as many people through. See
  [VALIDATION.md](VALIDATION.md).
- **Cost:** every plan shows its measured AI cost, model calls and simulations.

## Honest limits

- A **screening and planning aid**, not a prediction of deaths and not a safety certification.
- The simulator finds where density climbs past the danger level; it does not model crushing
  pressure itself (real crushes reach 7–10 people per m², beyond what pedestrian models capture).
- Results hold under the stated assumptions (headcount, walking speed, behaviour); map data must
  be checked on site. Commercial tools say the same: results "supplement the informed judgment of
  the qualified user" ([Pathfinder V&V](https://files.thunderheadeng.com/support/files/verification_validation.pdf)).
- AI output varies; it is validated, sandboxed and backed by rule-based fallbacks, and every
  number shown is computed.

## Related work

- **LLMs writing safety-critical scenarios as code:** ChatScene, CVPR 2024
  ([arXiv 2405.14062](https://arxiv.org/abs/2405.14062)). An LLM turns scenario descriptions into
  simulator code for autonomous driving and finds more failures than baselines. Showtime applies
  the same pattern to crowds.
- **LLM agents in crowd and evacuation models:** [Ntarouis & Geraerts 2026](https://ojs.cvut.cz/ojs/index.php/APP/article/view/11557),
  [Yang et al., Reliability Engineering & System Safety 2026](https://meetingorganizer.copernicus.org/EGU26/EGU26-3725.html),
  [language-driven crowd dynamics 2025](https://arxiv.org/pdf/2508.15047).
- **Bottleneck flow data:** Seyfried et al., "New insights into pedestrian flow through
  bottlenecks", Transportation Science 43 (2009), doi:10.1287/trsc.1090.0263.
- **Evaluating pedestrian simulators:** [Federici et al. 2014](https://arxiv.org/pdf/1404.7717v2.pdf).

## The 3-minute demo

[DEMO.md](DEMO.md), Parts A and A2: map → check → test (AI-written scenario) → Your plan
(choose fixes, analyst, rewind) → checklist.
