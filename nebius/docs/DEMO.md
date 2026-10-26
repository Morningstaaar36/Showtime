# The 3-minute demo

One story: **AI agents try to break your event plan. Every attack is code the AI wrote, and it
only ever runs inside a sealed sandbox. A physics simulator, not the AI, decides what breaks.
Then the AI fixes the plan and the sandbox proves the fix.**

[VIDEO_SCRIPT.md](VIDEO_SCRIPT.md) has the same beats with the voice-over and the shot list. The
voice-over says only what the screen shows.

## Before the demo

1. In `nebius/`, start everything with `make up` and open <http://localhost:5173>.
   - If `showtime-sim` is missing, run `make build-sim` first.
   - The header badges show the AI provider and the sandbox (DOCKER).
2. Prepare the tested plan ahead of time, because a live test takes a few minutes:
   - Projects › New project › **School wing** › name it `Spring open day` › Create project;
   - **Standard** › **Test this plan**, and let it finish.

   Check that Your plan › **Sandboxes** lists an **AI-written scenario**. If the red team wrote
   none this time, run **Test again**.
3. The free OpenRouter tier allows about 50 requests a day, and one test uses 4–8 of them.
   Rehearse once, and keep the rest for the take.
4. Have a terminal open in `nebius/` for the last beat (`make verify-live`).

## The beats

| Time | Beat | Do this | The screen shows |
| --- | --- | --- | --- |
| 0:00–0:20 | **The stakes** | Home › Learn from real cases › **Itaewon 2022** | The case card: "159 people died and 196 were injured", the 3.2 m alley, the sources as links, and where this rebuild's simulation put its peak density |
| 0:20–0:50 | **Describe a venue, watch it build** | Home › Describe it › type the metro sentence below › **Just draw my venue** | Check your venue: a two-level station in 3D, three stairs, two street exits, 800 people on the platform |
| 0:50–1:40 | **The agents attack** | Open `Spring open day` › Your plan › **Sandboxes**: the **AI-written scenario** › **Show the code**. Then the header **Sandbox** badge, and the tab's list of runs. Then Expert view › **Scripts** › New script › `import socket` › **Run in sandbox** | The Python the red team wrote and what it did. The sandbox's guarantees. Every run's container, with its state and time. The unsafe script refused with its reason |
| 1:40–2:10 | **The evidence** | Your plan › Scenarios › **Evidence** panel | The incident-dataset group, each source with its origin badge, and "Web search: off": the slot a Tavily key switches on |
| 2:10–2:40 | **The fix, proved in a sandbox** | Your plan › **Sandboxes** › **Rewind the worst moment** | The crowd at its worst second; "do nothing" and the fix run from that same second, side by side, and the measured difference |
| 2:40–3:00 | **The plan, the proof, the road to Nebius** | **Download checklist**; Help › **How good is the simulator?**; the terminal: `make verify-live` | The handover checklist; the simulator's flow within a few per cent of a real bottleneck experiment; Nebius and Tavily shown as SKIPPED (no keys); "Planning aid, not a safety certification" |

The metro sentence: `Metro station: underground platform level 120 x 14 m with 800 waiting
passengers, three stairs up to the street-level ticket hall, which has exits on the west and
east.`

## If something goes wrong

- **The AI badge says the hosted model is paused** (for example the daily free quota is used up,
  until a stated time). Use the prepared plan for beats 3–5. For beat 2, choose a template
  instead.
- **No key at all:** **Offline** above *Test this plan* runs rule-based attacks and fixes, still in
  the sandbox. Do not call those AI-written: the scenario card only says so when the model wrote
  it.
- Always say: *planning aid, not a safety certification*.

## After the demo: deeper tools

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
