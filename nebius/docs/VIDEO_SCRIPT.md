# Demo video script (3 minutes)

Status: **script ready; not recorded.** Same beats as [DEMO.md](DEMO.md). A person records and
uploads it to YouTube (public). It runs three minutes at most, and names NVIDIA Nemotron out
loud.

**Rule for every line:** say only what the screen shows.
- Say **"Docker sandbox"**, never "Nebius Sandbox", unless a Nebius sandbox ran.
- Say **"NVIDIA Nemotron"** for the model. Say "on Nebius Token Factory" only once the AI badge
  reads NEBIUS.

## Before recording

1. In `nebius/`, run `make up`, and open <http://localhost:5173> in a 1600 × 900 window. Use the
   light theme, zoom 100 %, and turn notifications off.
2. Prepare the tested plan: Projects › New project › **School wing**, name `Spring open day`,
   then **Standard** › **Test this plan**, and wait for Your plan. Its Sandboxes tab must list an
   **AI-written scenario**. If it doesn't, **Test again**. Note the tested plan's numbers.
3. Prepare a terminal in `nebius/` with `make verify-live` typed but not run.
4. The free OpenRouter tier allows about 50 requests a day. Record beat 2 (one designer call) live
   or from a rehearsal take.

## Shots

| Time | Screen and action | Voice-over |
| --- | --- | --- |
| 0:00–0:20 | Home › Learn from real cases › **Itaewon 2022**. Hold on the case card: "159 people died and 196 were injured", the sources | "Itaewon, 2022. 159 people died in an alley three metres wide. Nobody had tested that night's crowd. Showtime lets AI agents try to break your event plan first." |
| 0:20–0:50 | Home › **Describe it**: type the metro sentence ([DEMO.md](DEMO.md)) › **Just draw my venue**. Check your venue: rotate the 3D view, show the two levels and the stairs | "One sentence. An NVIDIA Nemotron agent designs the station, and a solver builds every wall, stair and exit: a platform with 800 people, three stairs up to the ticket hall." |
| 0:50–1:15 | Open `Spring open day` › Your plan › **Sandboxes**: the AI-written scenario card › **Show the code** | "This attack is code the AI wrote: a Python script that changes the crowd's situation as the simulation runs. It only ever runs inside a sealed sandbox." |
| 1:15–1:30 | Click the header **Sandbox** badge (facts list), then the Sandboxes tab's list of runs | "Every run is its own throwaway Docker container: no network, read-only, memory and process limits, no keys. The simulator, not the AI, decides what breaks." |
| 1:30–1:40 | Expert view › **Scripts** › New script › `import socket` › **Run in sandbox**: the refusal | "Code that tries to reach the network is refused before it runs, and the reason is shown." |
| 1:40–2:10 | Your plan › **Scenarios** › **Evidence** panel: the incident-dataset group, origin badges, "Web search: off" | "Each attack is grounded in a real crowd accident from the incident dataset, and every source says where it came from. Live web search switches on with a Tavily key; today it is off, and the screen says so." |
| 2:10–2:40 | Your plan › **Sandboxes** › **Rewind the worst moment**: the table with "Do nothing" and the fix from the same second | "Then the AI fixes the plan, and the sandbox proves the fix: rewind to the worst second, then run doing nothing and our fix from that same moment. <read the difference the table shows>." |
| 2:40–2:52 | **Download checklist** (open the file); Help › **How good is the simulator?** | "You get a handover checklist for your stewards. The simulator is checked against a real bottleneck experiment: <read the line on screen>." |
| 2:52–3:00 | The terminal: `make verify-live` (Nebius and Tavily rows SKIPPED); then Home with "Planning aid, not a safety certification." | "It runs on NVIDIA Nemotron and Docker today; Nebius Token Factory and Nebius Sandboxes plug in with a key. Planning aid, not a safety certification." |

## Evidence to note while recording

| Item | Where it is on screen | Fill in |
| --- | --- | --- |
| The tested plan's session id | the URL of Your plan (`?session=s_…`) | |
| The AI-written scenario's title | Sandboxes tab | |
| Rewind: do nothing vs the fix | the Rewind table | |
| The model in use | the AI badge | |

Rules for the cut:
- no number the screen does not show;
- no "confirmed" unless the plan says so;
- keep the planning-aid notice on screen at the end.
