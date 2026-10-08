# How to test Showtime (as an event organizer)

About 30 minutes. You only need a browser once the app is running.

## 0. Start it (once)

```bash
cd /home/lucifer/BUET/nebius
make llm-up        # starts the Nemotron model on your GPU (about 20 s)
make up            # starts the app (Docker); first time builds images
```

Open **http://localhost:5173**. (Lighter alternative without Docker for the app: `make dev`.)
When you are done: `make down` and `make llm-down`.

The top-right badge shows **LOCAL** with a green dot when the model and the simulator are ready.
If it is amber, hover it to see what is missing.

---

## 0a. End-to-end script (15 min, everything)

1. **Projects** → click the example *Food and music festival … Suhrawardy Udyan …* → **Plan it**.
   Watch the agent graph light up node by node (Brief agent → Map lookup → Layout solver →
   Planning ratios → Project → Simulation sandbox → Scenario sandboxes → Safety officer).
2. Read the Safety officer's actions → **Open the plan**. The narrated **tour** starts by itself
   (press Esc to stop; the speaker icon mutes it).
3. **Plan**: planning score (click it for the breakdown) → **What if…**: drag *Crowd size* to 150 %,
   pick *Rain*, close a gate; watch the score and numbers change → **Reset**.
4. **Showtime lights** (top right) → orbit around the stage. **Daylight** to switch back.
5. **Simulate**: the scenario matrix fills in as each sandbox finishes (one at a time locally,
   about 1–2 min each); click a finished card to replay it. Press **Space** to play.
6. **Red Team** → **Start red team** → watch attacks and fixes → **Apply fixed plan**.
7. **Report** → **Export PDF**: verdict, plan for the day with sources, evacuation map.

## 0b. The fastest way in: Event Copilot (3 min)

1. On **Projects**, type one sentence in the box at the top, or click an example. For example:
   *Victory Day concert at Ramna Park, Dhaka on 16 December at 6 pm for 6,000 people, 5 hours, with a bar*.
2. Press **Plan it**. Watch the steps: it reads the request, imports the real park from the map,
   places a stage, barrier, sound desk, toilets and bars, estimates capacity, staff, toilets and
   budget, creates the project and starts a crowd simulation (about 10–20 s).
3. **Open the plan**. The 3D view shows the real park on the street map with its lake and the
   buildings around it. The right panel's **Plan for the day** shows safe capacity, stewards, first
   aid, toilets, fencing and a budget, each with a **source** link. Change *Open for*, *Alcohol* or
   *Standing/Seated* and watch the numbers move.
4. Without a named place (*“Tech conference for 900 people in a hall with a balcony”*) it designs
   the venue instead: walls, doors, stage, balcony with stairs and columns.

## 1. Look around (2 min)

1. On **Projects** you see three sample projects (badge *Sample*) and four templates.
2. Click **Settings** in the header: check *Providers* (language model, simulation sandbox, web
   search off, weather) and the list of plugins. Try **Dark** theme and switch back.
3. Click **Help**: how every number is computed, glossary, keyboard shortcuts.

## 2. Open a finished demo (3 min): "Halloween night · T-shaped alley"

1. Open the project. You land in **Plan**: the 3D street with the narrow alley.
   *Drag* to rotate, *right-drag* to pan, *scroll* to zoom. The left toolbar's last button resets the view.
2. Read the **verdict card** (right): *This plan holds / is at risk / fails* with the numbers behind it.
3. Click **Red Team** (top). You see the scoreboard (breaks per round), the judge's summary, and
   *Attacks and fixes*: each attack card cites the **real incident** that inspired it (click the
   link), shows what happened (peak density, time above danger) and the fixes that were **kept**
   or **not kept**.
4. Click **Show in 3D** on an attack: the crowd replays in 3D. The colours on the floor are crowd
   density; the red outline marks 5 people per m². Use the timeline: play/pause (Space), 1×/4×/16×,
   drag the scrubber. Diamonds on the timeline mark events (red = an exit is blocked).
5. Open the **Branch tree** tab: baseline, each attack with its fixes indented under it, then the
   confirmation runs. Red = breaks, green = holds or kept. Click any box to replay it.
6. Click **Compare before and after** (in the summary): two views side by side on one clock.
7. **Time travel**: while an attack is replaying, pause after ~1 minute; on one of its fixes click
   **Apply from m:ss**. A new simulation runs where the fix starts only at that moment.

## 3. The wind story (3 min): "Waterfront Spring Festival · Wellington"

1. Open it. In **Plan**, the right panel shows the **stage structure** with its **wind limit**
   (from a structural frame model) and the **Wind on the day** chart: forecast gusts versus the
   stage limit, the gates opening, and when to evacuate.
2. The top bar chip shows **Start evacuating by HH:MM**. Click it to see the formula:
   hazard time − (pre-movement + evacuation time × safety factor), and which evacuation time
   it used (the plan you are looking at). The **Report** uses the more cautious basis, the
   worst red-team attack after fixes, so its time is earlier; it says so under the table.
3. Change **Ballast per leg** (e.g. 3000 → 1500 kg) and press Enter: the wind limit drops and the
   countdown moves earlier. Undo with **Ctrl+Z** (or the undo arrow, top left).

## 4. Plan your own event (8 min)

1. Back to **Projects** → **New project** → choose *Conference hall, 2 floors*, give it a name.
2. **Edit by typing**: click the box at the bottom (or press `/`) and type, for example:
   - `add a 3 m exit on the east wall`
   - `move the stage 3 m south`
   - `set the mezzanine to 250 people`
   Each change is saved as a new version (see the version menu next to the venue name) and can be
   undone. Undo itself is saved as a version too, so nothing is ever lost (v1 → v2 → undo = v3).
3. **Edit by dragging**: click an object (e.g. the sound desk) and drag the arrows; it snaps to 0.5 m.
4. **Draw**: left toolbar → *Draw barrier* (click points, double-click to finish), *Add exit*
   (click near an outer wall), *Draw zone*, *Measure*.
5. Watch the **Checks** and **Rules** sections: problems are listed with a fix hint, and clicking
   one flies the camera there. Try removing both south doors to see a blocking error.

## 4b. Make a venue from words or from a real place (5 min)

1. **Projects → New project → Describe it.** Click the chip *Open-air concert* (or write your own:
   size, people, where the stage, doors and bars are) → **Design venue**. In 5–15 s you get a plan
   preview, the checks, and a list of everything the AI assumed. **Create project** opens it in 3D.
2. **New project → Real place.** Search *Ramna Park Dhaka* (or your campus or a hall you know) and
   pick it from the list: the park outline is selected. Or **click any building** on the 3D map (it
   becomes an indoor venue) or a park or campus (open-air), or **Draw an area** with two clicks.
   A click takes 1–20 s the first time (free map servers), then it is cached.
   Set the people (or leave *auto*) → **Build venue** → **Create project**.
3. In the new project, edit what the map got wrong: drag the assumed exits to the real gates, type
   "remove building_3", "set zone_1 to 4000 people", then **R** to simulate.

## 5. Stress test and "Break it yourself" (5 min)

1. Press **R** or go to **Simulate** → **Run stress test**. You see "Simulating 1,200 people…"
   with a progress bar (about 15–30 s).
2. When it finishes the crowd replays, the verdict says *Confirmed by simulation*, and you get
   evacuation time (95%), peak density, a *people inside* curve and exit use. Click any number
   to see where it comes from.
3. Click a red or amber **hotspot ring** → **Ask the venue**: type "Why is this red?". The
   answer quotes only numbers from the simulation.
4. **Break it yourself**: choose the ⊘ tool (or press `X`), click a door to block it. The instant
   estimate updates immediately; press **Confirm with simulation** to run it for real.

## 6. Red Team Night on your plan (5–10 min)

1. **Red Team** → (optional: the ⚙ button sets rounds and attacks) → **Start red team**.
2. Watch it live: phase bar, attack cards dealt in, the branch tree growing, agent activity
   (which AI agent ran, tokens, time). Everything runs on your GPU; cost shows $0.00.
3. At the end: the judge's summary, before/after table, **Apply fixed plan** (saves a new version).

## 7. Report (2 min)

1. **Report** tab: a live preview of the document for your safety team / permit office.
2. **Export PDF** opens the print dialog (choose *Save as PDF*). Also download the **evacuation
   map (SVG)**, the **data bundle (JSON)** and the **project file (.showtime.zip)**.
3. On **Projects**, *Import* that .zip again: you get a full copy with its history.

## Things worth trying to "break"
- Stop the model (`make llm-down`) and try a text edit or a red team: you get a clear message;
  the red team still runs with rule-based attacks and fixes.
- Set an absurd value in Settings (danger density −1): it is refused with a reason.
- Restart everything (`make down && make up`): projects, versions and results are still there.

*Showtime is a planning aid, not a safety certification.*
