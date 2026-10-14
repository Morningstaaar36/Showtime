# Demo script

A walk through everything Showtime does, in the order an organizer meets it. Part A takes about
5 minutes; Part B shows the deeper tools when there is time. For a full test checklist see
[TESTING_GUIDE.md](TESTING_GUIDE.md).

## Before the demo

1. In `.env`: a working `OPENAI_COMPAT_API_KEY` (OpenRouter) with `LLM_PROVIDER=openai`, and
   `SANDBOX_PROVIDER=docker`. The badge in the app header should read OPENROUTER with a
   green dot.
2. Start everything: `make up`, then open <http://localhost:5173>.
   (`make build-sim` once if the simulator image is missing.)
3. Free OpenRouter keys allow about 50 requests a day. One red-team test uses about 4–8 of them;
   rehearse once, then keep the rest for the live demo.

## Part A — the organizer's journey (5 min)

1. **Home.** "Where is your event?" Three choices; say the three steps out loud: show us the
   venue, the AI tests it, you get a plan.
2. **Pick it on the map.** Search `Ramna Park Dhaka`, pick the result (it is outlined), set
   *People* to `3000`, press **Build venue**, then **Use this venue**.
   Other good searches: `BUET`, a stadium or a convention centre.
3. **Check your venue.** Three questions:
   - *Are the doors right?* Drag **Door** from the palette onto a wall; it snaps to the wall.
   - *How many people?* Type a headcount straight into a crowd area.
   - *Anything in the way?* Grab the stage or a stall and drag it.
   Every change can be undone from the toast.
4. **Test this plan.** The AI red team invents what could go wrong (citing real incidents), each
   idea runs as a crowd simulation, the blue team proposes fixes and each fix is re-simulated.
   The progress bar shows the step; it takes a few minutes.
5. **Your plan.** Verdict, evacuation time, peak density and the latest safe time to start
   evacuating; before/after replay; **Accept these changes**; **Download report**.

## Part B — deeper tools (pick any)

- **Expert view** (top right): the full studio with Plan, Simulate, Red Team and Report tabs.
  In Simulate, *Block an exit* ("break it yourself") updates the instant estimate, then confirm
  with a simulation.
- **Finished sample "Halloween night · T-shaped alley"**: open from *Your plans* for a complete
  red-team result, replay with the density heatmap, and the report.
- **Wind sample "Waterfront Spring Festival · Wellington"**: the stage wind limit and the
  countdown to the latest safe time to start evacuating.
- **Describe it** on Home: one sentence such as "an open field 80 by 50 m with a stage in the
  north and 5,000 people" becomes a checked venue.
- **Ask the AI to change the venue** (box under the 3D view): "make the south doors 3 m wide".

## If something goes wrong

- Header badge not green: the model provider is down or the key expired; the app falls back
  to rule-based attacks and fixes and says so.
- A map build fails: draw the area with **Draw an area** instead, or pick a smaller place.
- Always say: *planning aid, not a safety certification*.
