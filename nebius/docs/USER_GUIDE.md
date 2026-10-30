# Showtime user guide

Showtime helps you find where a crowd plan fails, fix it, and know when you must start
evacuating, with evidence you can show a safety team or permit office.

*Planning aid, not a safety certification.* For a guided 30-minute tour, see
[TESTING_GUIDE.md](TESTING_GUIDE.md).

## Concepts

| Term | Meaning |
| --- | --- |
| **Project** | One event or building. Holds the venue, its versions, runs, red-team sessions and reports. |
| **Venue version** | Every change (typed, dragged, applied fix) creates a version. Undo, redo, restore any version. |
| **Instant estimate** | A formula-based result in milliseconds (walking distance + exit capacity + queues). Good for "what if" exploration. |
| **Confirmed by simulation** | Every person simulated with JuPedSim. Slower (seconds to minutes) and the number to trust. |
| **Stress test** | One simulation of the current plan. |
| **Red team** | AI attackers that design failure scenarios inspired by real incidents. |
| **Fix** | A change proposed by the blue team. It is kept only if the simulation shows it helps. |
| **Peak density** | Highest crowd density on a 1 m grid, in people per m². Warning 3.5, danger 5. |
| **Evacuation time (95%)** | Time until 95% of people are out. |
| **Latest safe time to start evacuating** | Hazard time − (pre-movement time + evacuation time × safety factor). |

## Screens

### Projects
Create a project from a template, open a sample, search, duplicate, import or export a
`.showtime.zip` (includes versions, runs and sessions).

**New project** has three ways to start:
- **Template:** four validated venues.
- **Describe it:** write what the venue is like ("a 40 × 25 m hall for 1,200 people, stage on the
  north wall, two doors south, a balcony with 300 seats"). The AI chooses sizes and positions; the
  exact geometry is computed and checked in code. The preview lists everything that was assumed.
- **Real place:** search a place, zoom in, **Load buildings here**, then click a building (indoor)
  or a park, square or campus (open-air), or **Draw an area** with two clicks. Buildings, water and
  fences become obstacles; paths and gates that cross the edge become exits. Where the map shows
  no entrances, two exits are assumed and labelled "(assumed)": move them to the real doors.
  Limits: 40 ha and 1 km long. Map data © OpenStreetMap contributors.

### Plan
The 3D venue. Rotate (drag), pan (right-drag), zoom (scroll). Left toolbar:

| Tool | Key | What it does |
| --- | --- | --- |
| Select / move | `V` | Click an object, drag the arrows; snaps to 0.5 m |
| Draw barrier | `B` | Click points, double-click to finish |
| Add exit | `E` | Click near an outer wall |
| Draw zone | `Z` | Click corners of a standing area |
| Measure | `M` | Click two points |
| Block exit | `X` | Toggle an exit as blocked (Break it yourself) |
| Reset view | — | Fly back to the overview |

Type edits in the command box (`/`): "add a 3 m exit on the east wall", "move the stage 3 m
south", "set the audience to 900 people", "block door_s1". The right inspector shows the
verdict, selected object, checks and rules (click a problem to fly to it), the stage wind limit
and the wind forecast for outdoor venues.

### Simulate
**Run stress test** (`R`). The replay shows people, the density heatmap (cividis scale; the red
outline is 5 people per m²) and hotspot rings. The timeline plays at 1×/4×/16× (`Space`).
Metrics: evacuation time (95%), peak density, time above danger, people inside over time, exit
use. Click any number for its source (run id, tier, formula). Click a hotspot → **Ask the
venue**. Block an exit with `X` to see the instant effect, then **Confirm with simulation**.

### Red Team
**Start red team** (the ⚙ button sets rounds, attacks per round and fixes per attack). Each
round: attack cards (with the incident that inspired them), simulated branches, fixes and
whether they were kept. The branch tree shows the whole search; click a node to replay it.
At the end: judge summary, before/after table, **Compare before and after** (split screen),
**Apply fixed plan**. *Time travel*: pause a replay and click **Apply from m:ss** on a fix to
test it as a late intervention.

### Report
A printable document: verdict, countdown, metrics, evacuation map, attacks with sources, fixes,
assumptions with sources, calibration of instant estimates. **Export PDF** uses the browser's
print dialog. Also: evacuation map (SVG), data bundle (JSON), project file (.showtime.zip).

### Settings
Providers (local or hosted), API keys status (keys stay on the server), budgets, thresholds,
units (metric/imperial), plugins, theme. Invalid values are refused with a reason.

### Help
How every number is computed, glossary, limits of the tool, keyboard shortcuts.

## Keyboard shortcuts

| Keys | Action |
| --- | --- |
| `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z` | Undo, redo |
| `Space` | Play / pause replay |
| `R` | Run stress test |
| `/` | Focus the command box |
| `V B E Z M X` | Tools (see Plan) |
| `1` `2` `3` `4` | Plan, Simulate, Red Team, Report |
| `Esc` | Cancel the current tool or close a dialog |

## When something is off

| Message | What to do |
| --- | --- |
| Provider badge amber | Click it: it says why (a used-up daily quota until a stated time, a rejected key, or a stopped local model) and what to do. Tests still run in **Offline** mode. |
| "Live search is off" | No Tavily key. Attack cards cite the incident dataset instead. |
| "Weather unavailable" | Enter a gust value by hand in the wind panel. |
| "Stopped at N s of simulated time" | The run hit its time cap; results cover that window. Raise `MAX_SIM_S` in Settings. |
| A check says a zone cannot reach an exit | Add or move an exit, or remove the barrier that cuts it off. |
