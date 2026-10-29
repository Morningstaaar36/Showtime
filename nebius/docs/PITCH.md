# Showtime: the pitch

**AI agents try to break your event plan. The red team can write attacks as code, and that code
only ever runs in a sealed sandbox. A physics simulator, not the AI, decides what breaks. Then the
AI proposes fixes, and only the fixes the simulator confirms are kept.**

Judges: the one page to start from is [JUDGE_GUIDE.md](JUDGE_GUIDE.md).

## The problem

Crowd crushes happen at bottlenecks nobody tested: a narrow door, a blocked gate, two flows
meeting in an alley. Itaewon (Seoul, 2022) killed 159 people in an alley 3.2 m wide at its
narrowest (sources in [REAL_CASES.md](REAL_CASES.md)). Crowd modelling takes specialists and
licensed software, so most events, venues and permit offices never test a plan before the gates
open.

## What Showtime does, in three things

1. **Agents that act.** Eleven NVIDIA Nemotron agents (the AI team page lists twelve entries:
   the Analyst's planning and answering steps are shown separately; the Router is a small
   classifier with a keyword fallback). They:
   - **build** the venue from one sentence, a map or a template;
   - **attack** it: menu attacks from scenario events, plus at most one scenario written as
     Python code per round;
   - **look up** real incidents for each attack;
   - **fix** it;
   - **answer questions** by writing analysis code.

   The AI team page lists each agent's model and tools.
2. **Sandboxes at the core.** Every crowd simulation and every AI-written script runs in a
   throwaway container. It has no network, a read-only system, memory, CPU and process limits,
   and no keys. The header badge, the live sandbox feed on *AI tests it* and the Sandboxes tab on
   the plan show it.
3. **Evidence.**
   - Attacks cite real crowd accidents: 388 from the Feliciani dataset (1900–2024) and 7
     well-known ones with Wikipedia sources, 395 in all, with an origin badge on each source.
   - Numbers come from the simulator, formulas and cited data. Every number in AI text is checked
     against the computed results (it must appear in the tool output), and text that quotes
     another is rejected.
   - The simulator was calibrated on a real bottleneck experiment and fits it closely (one
     experiment; see the limits below).

The Event Copilot (one sentence → a planned, tested event) and the planning estimates support
this loop. They are not a separate story.

## How it maps to the judging criteria

| Criterion | Our answer | Evidence in the repo |
| --- | --- | --- |
| **Technological implementation** | Nemotron agents drive proven simulators (JuPedSim, PedPy, Pynite) as tools. AI-written code is checked statically, then run in a hardened container. Providers are plug-ins behind registries. Every number is computed by the tools, and numbers in AI text are checked against them | [SANDBOX_PROOF.md](SANDBOX_PROOF.md) (14 attacks on the real container, recorded by `make sandbox-proof`); [ADDING_A_PROVIDER.md](ADDING_A_PROVIDER.md) and `api/tests/test_provider_registry.py`; the tests: `make check` locally and CI (`.github/workflows/ci.yml`); browser journeys in `web/e2e/` (`make e2e`) |
| **Design** | Three simple screens: *Your venue → AI tests it → Your plan*. Expert view keeps the full studio. Every number says if it is an instant estimate or confirmed by simulation | WCAG 2.2 AA and phone-width checks in `web/e2e/release-quality.spec.ts`; screenshots in `docs/screenshots/` |
| **Potential impact** | Organizers, venue managers and permit offices who can't hire a crowd consultant get a stress test, the fixes and a handover checklist in minutes | A printable report and checklist. Real cases (Love Parade, Hillsborough, Itaewon) as illustrations: hand-written descriptions from published reports, built by the designer and simulated ([REAL_CASES.md](REAL_CASES.md)); organizers can add their own |
| **Quality of the idea** | The AI operates validated simulation software instead of guessing. Red and blue teams play against a physics judge that cannot be flattered. The red team can also write a scenario as code (at most one per round), not only pick from a menu | [RAINBOW.md](RAINBOW.md) (failure map, after Rainbow Teaming); the "Show the code" button on AI-written scenarios; [VALIDATION.md](VALIDATION.md) |

## Extensible: Nebius and Tavily plug in through .env

Nebius Token Factory, Nebius Sandboxes and Tavily web search are built as plug-ins (one file each
in `api/adapters/providers/`) and tested with fake clients:
- `api/tests/test_provider_readiness.py`;
- `api/tests/test_search_adapter.py`;
- `api/tests/test_web_evidence.py`.

To switch one on, edit `.env` only: the provider name, the key, and for Nebius Sandboxes the
project ID. Model ids left from another provider switch to the Nebius preset on their own. Then
`make verify-live` gives each service a pass or the exact reason, written to
[LIVE_STATUS.md](LIVE_STATUS.md). **None of the three has run live**: we had no keys
([NEBIUS_SWITCH.md](NEBIUS_SWITCH.md)). Tavily in particular is built and tested with a fake
client only (basic-depth search, up to 5 results, cached and capped), so we make no claim about
its live results.

**Models.** Live runs use OpenRouter's free tier: Nemotron 3.5 Lightning for the fast roles (red
team, what-if planner, router) and Nemotron 3 Ultra for the main and judge roles. Results logged
up to 2026-10-19 used Nemotron 3 Super, until its free endpoint returned 404. The Nebius preset
(not run live) maps fast and long to Nemotron 3.5 Lightning, main to Nemotron 3.5 Super VL and
judge to Nemotron 3 Ultra. JSON is asked for in the prompt (`LLM_SUPPORTS_JSON_SCHEMA=false` in
both presets), validated with Pydantic and repaired with one extra call.

## Every claim and its source

| Claim | Source | Kind |
| --- | --- | --- |
| On a two-floor conference hall, the red team broke the plan in 2 of 3 scenarios. The kept fixes cut peak density from 6.95 to 4.6 people per m², and the 95 % evacuation time from 4 min 39 s to 2 min 48 s. Full simulations confirmed it, with no one left inside | [PROGRESS.md](PROGRESS.md), 2026-10-14 | **single live run** (OpenRouter Nemotron 3 Super + JuPedSim) |
| Real cases: peak density 5.7 /m² (Itaewon), 5.5 /m² (Love Parade) and 9.9 /m² (Hillsborough), near where the real crush was. Above about 6 /m² (the most the simulated bodies can pack) the density exists only because of the squeeze rule (below), so read it as "a severe jam here", not a measured crush density | [REAL_CASES.md](REAL_CASES.md) | **single live run each** (Nemotron 3 Ultra, 2026-10-25); illustrations built from hand-written descriptions, not evidence or a forensic finding |
| The designer built 8 of 8 different venues cleanly, with 32 of 32 requested features | [archive/BUILD_LOG.md](archive/BUILD_LOG.md), Step 5 | **single live run per description** (OpenRouter Nemotron) |
| After calibrating one parameter (time gap 0.25 s) on half the widths of the Jülich 2006 bottleneck series, the simulator's flow is within about 6 % of the measured flow at every width (median 4.0 %; the other half of the widths 4.4 %) | [VALIDATION.md](VALIDATION.md) | deterministic, 3 seeds per width; calibration and test widths come from the **same experiment** |
| 14 attacks on the sandbox; each was stopped or contained | [SANDBOX_PROOF.md](SANDBOX_PROOF.md) | recorded by `make sandbox-proof` |
| 395 real crowd accidents ground the attacks | 388 from the Feliciani dataset (Zenodo 19483010; `make setup` writes 388) plus a curated list of 7 with Wikipedia links (`plugins/incidents_feliciani/seed.json`), counted live at `/api/v1/agents` | dataset |
| Nebius Token Factory, Nebius Sandboxes and Tavily: built, not run live | [LIVE_STATUS.md](LIVE_STATUS.md) | SKIPPED (no keys) |

> **Honest limits**
> - A **planning aid, not a safety certification**. It does not predict deaths, and a competent
>   person signs off the plan.
> - The simulator finds where density climbs past the danger level (5 people per m²). It has no
>   pushing forces. Simulated bodies are hard discs that pack to about 6 per m² at most; where
>   a door clogs (a queue but nobody through for 4 s), the **squeeze rule** shrinks the people
>   near it from 0.22 m to 0.15 m radius so the model does not deadlock
>   ([ASSUMPTIONS.md](ASSUMPTIONS.md)). That is how Hillsborough reaches 9.9 per m²: higher
>   densities flag a severe jam, they are not measured crush densities. The crowd-pressure
>   (turbulence) layer is **indicative**.
> - Validated against one experiment (calm walkers, one kind of bottleneck), and calibrated on
>   that same experiment.
> - Results hold under the stated assumptions (headcount, walking speed, behaviour). Map data must
>   be checked on site.
> - The AI's choices vary between runs. Each is validated, run in the sandbox and checked by
>   simulation, with rule-based fallbacks. The headline results above are single live runs.
> - Model replies are cached (`LLM_CACHE_MODE=record_replay`, the default): a call identical to an
>   earlier one is answered from the cache, and Your plan › *How this plan was made* says how many.
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
[JUDGE_GUIDE.md](JUDGE_GUIDE.md) is the judges' entry point, with a 5-minute path.
