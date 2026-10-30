# Try it: start here

## 1. What it is

Showtime lets AI agents (NVIDIA Nemotron) try to break an event or building evacuation plan,
while a crowd simulator (JuPedSim), not the AI, measures what breaks. The AI then proposes fixes,
and only fixes the simulator shows to help are kept; every run happens in a sealed sandbox.

Planning aid, not a safety certification.

## 2. Try it online

If someone hosts Showtime for you, they give you its address and a user name and password: the
whole hosted app sits behind a password, because the API spends model credit. To host it
yourself on any server with Docker, see [HOSTING.md](HOSTING.md). To run it on your own
machine, see section 5.

## 3. A 5-minute path through the app

| # | Do this | What you should see |
| --- | --- | --- |
| 1 | **Projects › New project › School wing › Create project**, then **Standard › Test this plan** | **AI tests it**: the agents' steps and tool calls, and the sandbox feed with every run's container, state and time. A live test takes a few minutes and ends on **Your plan**; carry on meanwhile |
| 2 | Click the **Sandbox** badge in the header, then **What it stopped in tests** | The sandbox's limits (no network, read-only system, memory, CPU and process limits, no keys) and 14 recorded attacks on it, each with what stopped it ([SANDBOX_PROOF.md](SANDBOX_PROOF.md)) |
| 3 | **Home › Describe it**, paste `Metro station: underground platform level 120 x 14 m with 800 waiting passengers, three stairs up to the street-level ticket hall, which has exits on the west and east.` and click **Just draw my venue** | Two levels in 3D, three stairs, two street exits, 800 people. The Designer agent writes the structure; a solver builds the geometry |
| 4 | Back on the test's **Your plan**: the **Sandboxes** tab (an **AI-written scenario** › **Show the code**, then **Rewind the worst moment**), then **Scenarios** (failure map and **Evidence** panel) | The Python the red team wrote, if it wrote one this time (at most one script per round; the other attacks are picked from a menu of scenario events). "Do nothing" and each fix run from the same worst second, side by side. Each attack's source with its origin badge |
| 5 | **Download checklist**; **Help › How good is the simulator?**; **Meet the AI team** | The handover checklist; the simulator against a real bottleneck experiment; each agent with its model and tools |

No model available (for example the free daily quota is used up): choose **Offline** above *Test
this plan*. Rule-based attacks and fixes still run in the sandbox, and nothing is labelled
AI-written. The four sample projects in **Projects** open with finished tests.

Replayed answers: with the default `LLM_CACHE_MODE=record_replay`, a model call identical to an
earlier one on the same server is answered from the cache. Your plan › **How this plan was made**
shows how many calls were answered that way.

## 4. What runs live, and what does not

| Service | Status (checked 2026-10-26, [LIVE_STATUS.md](LIVE_STATUS.md)) |
| --- | --- |
| NVIDIA Nemotron on OpenRouter (free tier) | **Live.** Nemotron 3.5 Lightning for the fast roles (red team, what-if planner, router), Nemotron 3 Ultra for the rest |
| Local Docker sandbox | **Live.** Every simulation and every AI-written script |
| Tavily web search | Built and tested with a fake client. **Not run live**; without a key the red team cites the incident dataset and the app says web search is off |

Why: we had no Tavily key. It switches on with `.env` alone and is checked by
`make verify-live`; where each key goes is in [PROVIDERS.md](PROVIDERS.md). The AI can also run
on a local llama.cpp server (`make use-local`, `make llm-up`).

## 5. Run it yourself

Needs Docker (with Compose v2) and `make`. A free OpenRouter key gives the AI; without one, use
**Offline**.

```bash
cd nebius && cp .env.example .env     # then set OPENAI_COMPAT_API_KEY=<your OpenRouter key> in .env
make up                               # builds and starts everything in Docker (the first build takes a while)
# open http://localhost:5173
```

Host it on a server: [HOSTING.md](HOSTING.md). More: [README](../README.md),
[the pitch and its evidence](PITCH.md), [hard questions](QA.md).
