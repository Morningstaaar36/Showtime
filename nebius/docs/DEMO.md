# A live walkthrough

About ten minutes, one story: **AI agents try to break your event plan. The red team can write attacks as code, and
that code only ever runs in a sealed sandbox. A physics simulator, not the AI, decides what
breaks. Then the AI proposes fixes, and only the fixes the simulator confirms are kept.**

Exploring on your own instead: [JUDGE_GUIDE.md](JUDGE_GUIDE.md).

## Before you start

1. In the project folder, start everything with `make up` and open <http://localhost:5173>.
   - If `showtime-sim` is missing, run `make build-sim` first.
   - The header badges show the AI provider and the sandbox (DOCKER).
2. Prepare the tested plan ahead of time, because a live test takes a few minutes:
   - Projects › New project › **School wing** › name it `Spring open day` › Create project;
   - **Standard** › **Test this plan**, and let it finish.

   Check that Your plan › **Sandboxes** lists an **AI-written scenario**. The red team writes at
   most one per round (its other attacks are picked from a menu of scenario events); if it wrote
   none this time, run **Test again**.
3. The free OpenRouter tier allows about 50 requests a day, and one test uses 4–8 of them.
   Plan your tests around that.
4. Have a terminal open in the project folder for the last step (`make verify-live`).
5. **Replayed answers.** With the default `LLM_CACHE_MODE=record_replay`, a model call identical
   to an earlier one (for example a real case or a sentence you rehearsed) is answered from
   `cache/llm/` instead of the model. Your plan › **How this plan was made** shows how many calls
   were answered from the cache. For fully live answers, set
   `LLM_CACHE_MODE=record` in `.env` and run `make up` (it calls the model and still records).

## The steps

| Step | Do this | The screen shows |
| --- | --- | --- |
| 1. **The stakes** | Home › Learn from real cases › **Itaewon 2022** | The case card: "159 people died and 196 were injured", the 3.2 m alley, the sources as links, and where this rebuild's simulation put its peak density (an illustration built from a hand-written description, not evidence) |
| 2. **Describe a venue, watch it build** | Home › Describe it › type the metro sentence below › **Just draw my venue** | Check your venue: a two-level station in 3D, three stairs, two street exits, 800 people on the platform |
| 3. **The agents attack** | Open `Spring open day` › Your plan › **Sandboxes**: the **AI-written scenario** › **Show the code**. Then the header **Sandbox** badge, and the tab's list of runs. Then Expert view › **Scripts** › New script › `import socket` › **Run in sandbox** | The Python the red team wrote and what it did. The sandbox's guarantees. Every run's container, with its state and time. The unsafe script refused with its reason |
| 4. **The evidence** | Your plan › Scenarios › **Evidence** panel | The incident-dataset group, each source with its origin badge, and "Web search: off": the slot a Tavily key switches on |
| 5. **The fix, proved in a sandbox** | Your plan › **Sandboxes** › **Rewind the worst moment** | The crowd at its worst second; "do nothing" and the fix run from that same second, side by side, and the measured difference |
| 6. **The plan and the proof** | **Download checklist**; Help › **How good is the simulator?**; the terminal: `make verify-live` | The handover checklist; the simulator's flow within a few per cent of a real bottleneck experiment; each service without a key shown as SKIPPED (Tavily, for example); "Planning aid, not a safety certification" |

The metro sentence: `Metro station: underground platform level 120 x 14 m with 800 waiting
passengers, three stairs up to the street-level ticket hall, which has exits on the west and
east.`

## If something goes wrong

- **The AI badge says the hosted model is paused** (for example the daily free quota is used up,
  until a stated time). Use the prepared plan for steps 3–5. For step 2, choose a template
  instead.
- **No key at all:** **Offline** above *Test this plan* runs rule-based attacks and fixes, still in
  the sandbox. Do not call those AI-written: the scenario card only says so when the model wrote
  it.
- Always say: *planning aid, not a safety certification*.

## Deeper tools

- **Failure map** (Your plan › Scenarios): every way the plan broke, by hazard and place.
- **Rainbow search:** how the red team fills the failure map ([RAINBOW.md](RAINBOW.md)).
- **Stress test at scale** (Your plan › Sandboxes): every attack × your plan, and each kept fix ×
  several random crowds, with live counters.
- **Check with more seeds** (Your plan › Scenarios › Deeper checks): the range of each number over
  several random crowds.
- **Ask or change anything:** "how long was the longest queue at the East stairwell?" The
  analyst writes code, the sandbox runs it, and **Show the code** displays it.
- **Expert view:** Plan, Simulate (block an exit: "Break it yourself"), Red Team and Report.
- **Event Copilot / Autopilot:** one sentence ("Victory Day concert at Ramna Park, Dhaka,
  16 December 6 pm, 6,000 people") becomes a venue, a test and a plan.
