# Showtime: the pitch

**AI agents try to break your event plan. Every attack is code the AI wrote, and it only ever
runs inside a sealed sandbox. A physics simulator, not the AI, decides what breaks. Then the AI
fixes the plan and the sandbox proves the fix.**

## The problem

Crowd crushes happen at bottlenecks nobody tested: a narrow door, a blocked gate, two flows
meeting in an alley. Itaewon (Seoul, 2022) killed 159 people in an alley 3.2 m wide at its
narrowest (sources in [REAL_CASES.md](REAL_CASES.md)). Crowd modelling takes specialists and
licensed software, so most events, venues and permit offices never test a plan before the gates
open.

## What Showtime does, in three things

1. **Agents that act.** Twelve NVIDIA Nemotron agents:
   - **build** the venue from one sentence, a map or a template;
   - **attack** it, writing new failures as Python code;
   - **look up** real incidents for each attack;
   - **fix** it;
   - **answer questions** by writing analysis code.

   The AI team page lists each agent's model and tools.
2. **Sandboxes at the core.** Every crowd simulation and every AI-written script runs in a
   throwaway container. It has no network, a read-only system, memory, CPU and process limits,
   and no keys. The header badge, the live sandbox feed on AI at work and the Sandboxes tab on
   the plan show it.
3. **Evidence.**
   - Attacks cite real crowd accidents: 388 from the Feliciani dataset (1900–2024) and 7
     well-known ones with Wikipedia sources, 395 in all, with
     an origin badge on each source.
   - Numbers come only from the simulator, and a number check rejects any AI text that quotes
     another.
   - The simulator is checked against a real experiment.

The Event Copilot (one sentence → a planned, tested event) and the planning estimates support
this loop. They are not a separate story.

## How it maps to the judging criteria

| Criterion | Our answer | Evidence in the repo |
| --- | --- | --- |
| **Technological implementation** | Nemotron agents drive proven simulators (JuPedSim, PedPy, Pynite) as tools. AI-written code is checked statically, then run in a hardened container. Providers are plug-ins behind registries. Every number is computed and checked | [SANDBOX_PROOF.md](SANDBOX_PROOF.md) (14 attacks on the real container, recorded by `make sandbox-proof`); [ADDING_A_PROVIDER.md](ADDING_A_PROVIDER.md) and `api/tests/test_provider_registry.py`; `make check`: 857 tests pass; the full Playwright suite in Chrome: see [BUILD_LOG.md](BUILD_LOG.md), Step 7 |
| **Design** | Three simple screens: *Your venue → AI at work → Your plan*. Expert view keeps the full studio. Every number says if it is an instant estimate or confirmed by simulation | WCAG 2.2 AA and phone-width checks in `web/e2e/release-quality.spec.ts`; screenshots in `docs/screenshots/` |
| **Potential impact** | Organizers, venue managers and permit offices who can't hire a crowd consultant get a stress test, the fixes and a handover checklist in minutes | Real cases (Love Parade, Hillsborough, Itaewon) rebuilt by the same designer and simulated: [REAL_CASES.md](REAL_CASES.md); a printable report and checklist |
| **Quality of the idea** | The AI operates validated simulation software instead of guessing. Red and blue teams play against a physics judge that cannot be flattered. The red team writes code, not just picks from a menu | [RAINBOW.md](RAINBOW.md) (failure map, after Rainbow Teaming); the "Show the code" button on AI-written scenarios; [VALIDATION.md](VALIDATION.md) |

## Extensible: Nebius and Tavily plug in through .env

Nebius Token Factory, Nebius Sandboxes and Tavily web search are built as plug-ins (one file each
in `api/adapters/providers/`) and tested with fake clients:
- `api/tests/test_provider_readiness.py`;
- `api/tests/test_search_adapter.py`;
- `api/tests/test_web_evidence.py`.

To switch one on, edit `.env` only: the provider name, the key, and for Nebius Sandboxes the
project ID. Model ids left from another provider switch to the Nebius preset on their own. Then
`make verify-live` gives each service a pass or the exact reason, written to
[LIVE_STATUS.md](LIVE_STATUS.md). No code changes. **None of the three has run live yet**: we had no keys
([WHEN_YOU_GET_THE_KEYS.md](WHEN_YOU_GET_THE_KEYS.md)).

## Every claim and its source

| Claim | Source | Kind |
| --- | --- | --- |
| On a two-floor conference hall, the red team broke the plan in 2 of 3 scenarios. The kept fixes cut peak density from 6.95 to 4.6 people per m², and the 95 % evacuation time from 4 min 39 s to 2 min 48 s. Full simulations confirmed it, with no one left inside | [PROGRESS.md](PROGRESS.md), 2026-10-14 | **single live run** (OpenRouter Nemotron + JuPedSim) |
| Real cases: peak density 5.7 /m² (Itaewon), 5.5 /m² (Love Parade) and 9.9 /m² (Hillsborough), near where the real crush was | [REAL_CASES.md](REAL_CASES.md) | **single live run each**; a rebuild, not a forensic finding |
| The designer built 8 of 8 different venues cleanly, with 32 of 32 requested features | [BUILD_LOG.md](BUILD_LOG.md), Step 5 | **single live run per description** |
| The simulator's bottleneck flow is within about 6 % of the real crowd's at every width (median 4.0 %; held-out 4.4 %) | [VALIDATION.md](VALIDATION.md) | deterministic, 3 seeds per width |
| 14 attacks on the sandbox; each was stopped or contained | [SANDBOX_PROOF.md](SANDBOX_PROOF.md) | recorded by `make sandbox-proof` |
| 395 real crowd accidents ground the attacks | 388 from the Feliciani dataset (Zenodo 19483010; `make setup` writes 388) plus a curated list of 7 with Wikipedia links (`plugins/incidents_feliciani/seed.json`), counted live at `/api/v1/agents` | dataset |
| Nebius Token Factory, Nebius Sandboxes and Tavily: built, not run live | [LIVE_STATUS.md](LIVE_STATUS.md) | SKIPPED (no keys) |

> **Honest limits**
> - A **planning aid, not a safety certification**. It does not predict deaths, and a competent
>   person signs off the plan.
> - The simulator finds where density climbs past the danger level (5 people per m²). It does
>   not model crushing forces, and simulated bodies cannot overlap, so crush densities are out of
>   reach.
> - Validated against one experiment (calm walkers, one kind of bottleneck).
> - Results hold under the stated assumptions (headcount, walking speed, behaviour). Map data must
>   be checked on site.
> - The AI's choices vary between runs. Each is validated, run in the sandbox and checked by
>   simulation, with rule-based fallbacks. The headline results above are single live runs.
> - It runs today on OpenRouter's free Nemotron tier (about 50 requests a day) and local Docker.
>   Nebius and Tavily are not live yet.

## Related work

- **LLMs writing safety-critical scenarios as code:** ChatScene, CVPR 2024
  ([arXiv 2405.14062](https://arxiv.org/abs/2405.14062)). Its LLM turns scenario descriptions into
  simulator code for autonomous driving and finds more failures than baselines. Showtime applies
  the pattern to crowds.
- **Red teaming as quality-diversity search:** Rainbow Teaming, NeurIPS 2024. Our judge is the
  simulator, not a language model.
- **LLM agents in crowd and evacuation models:** [Ntarouis & Geraerts 2026](https://ojs.cvut.cz/ojs/index.php/APP/article/view/11557),
  [language-driven crowd dynamics 2025](https://arxiv.org/pdf/2508.15047).
- **Bottleneck flow data:** Seyfried et al., *Transportation Science* 43 (2009),
  doi:10.1287/trsc.1090.0263.

## The 3-minute demo

[DEMO.md](DEMO.md) and [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md) tell the same story, beat by beat.
[JUDGE_GUIDE.md](JUDGE_GUIDE.md) is the 8-step walkthrough for judges.
