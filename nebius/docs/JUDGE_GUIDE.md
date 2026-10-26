# Judge's walkthrough: 8 steps, about 15 minutes

Start the app: `cd nebius && make up`, then open <http://localhost:5173>. The quickstart is in
the [README](../README.md#quickstart). Every step works without a key in **Offline** mode, except
steps 4 and 5, which need the model.

| # | What to click | What you should see | What it proves |
| --- | --- | --- | --- |
| 1 | Open <http://localhost:5173>. In the header, click the **Sandbox** badge, then **What it stopped in tests** | The sandbox's guarantees: no network, read-only system, memory, CPU and process limits, no keys. Help › Sandbox shows a table of 14 attacks and what stopped each, in the sandbox's own words, with the date it was recorded | The sandbox is real and was attacked. The table is a recording from `make sandbox-proof`, not text typed in by hand |
| 2 | Home › **Learn from real cases** › **Itaewon 2022** (double-click if you like: it opens once) | Your plan with the case card: what happened, the sources as links, and where this simulation put its peak density | The designer rebuilds real places from sourced descriptions. The card says what is approximate; it is a rebuild, not a forensic finding |
| 3 | Home › **Describe it**, type `Metro station: underground platform level 120 x 14 m with 800 waiting passengers, three stairs up to the street-level ticket hall, which has exits on the west and east.`, then **Just draw my venue** | Check your venue: two levels in 3D, three stairs, two street exits, 800 people on the platform | One sentence to any kind of venue (here no stage, two levels). A solver builds the geometry, and checks send errors back to the model |
| 4 | **Projects** › **New project** › **School wing** › **Create project**, then **Standard** › **Test this plan** | AI at work: the agents' steps and tool calls ("similar real incidents found"), and the **sandbox feed** with every run's container, state and time ("N of M done"). It ends on Your plan | The agents act, and every idea is simulated in its own sandbox. Without a key, choose **Offline**: rules stand in for the AI, and the sandboxes still run |
| 5 | Your plan › **Sandboxes**: the **AI-written scenario**, then **Show the code**. Then Your plan › **Scenarios** › the **Evidence** panel | The Python the red team wrote, and what happened when it ran. Each scenario's source has an origin badge (incident dataset, or live web with a Tavily key). Web search says it is off without a key | The attack is code the AI wrote, and evidence is labelled. Nothing claims a live web result that did not happen |
| 6 | Expert view › **Scripts** › **New script**, type `import socket`, then **Run in sandbox** | "Fix these before running:" with the reason (`import of 'socket' is not allowed`). Nothing is sent to the sandbox, and the sandbox has no network anyway (step 1) | Unsafe code is refused before it runs, with its reason shown |
| 7 | Your plan › **Sandboxes** › **Rewind the worst moment** (then **Stress test at scale**) | The crowd saved at its most dangerous second. "Do nothing" and each response run from that same second, side by side, with the measured difference. Then the stress test counters ("8 of 8 done") | The fix is proved in the sandbox from the same starting point, not asserted by the AI |
| 8 | Your plan › **Download checklist** and **Download report**; Help › **How good is the simulator?**; the **AI team** page (`/team`) | The handover checklist and report, both with "Planning aid, not a safety certification". The simulator within a few per cent of a real bottleneck experiment. Twelve agents with their models and tools | The output is usable and honest, and every number is traceable. To check the Nebius and Tavily plug-ins, run `make verify-live` in a terminal: they show SKIPPED (no keys), never a fake pass |

If something goes wrong:
- The AI badge says when the hosted model is paused (for example a used-up daily quota) and until
  when. Use **Offline**.
- The sandbox badge turns red if Docker is not running: run `make up` again.
