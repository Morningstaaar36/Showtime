# Showtime in plain English

Written on 2026-10-25 from the code and docs as they are today. Where I am not sure, I say so.

## 1. What Showtime does

Showtime helps someone who runs an event check that people can get out safely.

The organizer:
1. Describes the place in a sentence, picks it on a map, or starts from a sample.
2. Sees it as a 3D model: floors, doors, stairs and the crowd, with the number of people in each area.
3. Presses "Test this plan".
4. Watches AI agents try to break the plan, for example by blocking a door or sending a late crowd.
   A crowd simulator plays out each idea, and the agents then suggest fixes, which are simulated too.
5. Gets "Your plan": a verdict, the worst case, the fixes that worked, a replay of the crowd, a report,
   an evacuation map and a checklist for the team on the day.

## 2. The features, one by one

- **Describing a venue.** You write one sentence ("a 5-storey mall, 300 shoppers per floor, stairs at
  both ends"). An AI agent turns it into a layout. Ordinary code then draws the exact shapes and checks
  that every person can reach a door.
- **The AI agents.** Eleven agents, all NVIDIA Nemotron models (the AI team page lists twelve
  entries because the Analyst's two steps are shown separately):
  - the Brief reads your sentence;
  - the Designer lays out the venue;
  - the Editor makes typed changes;
  - the Router decides what a typed question means (a small classifier, with a keyword
    fallback);
  - the What-if planner and the Red team decide what could go wrong;
  - the Blue team decides what to change;
  - the Judge writes the verdict;
  - the Safety officer lists the actions that matter most;
  - the Explainer and the Analyst answer questions.

  They decide; they never measure.
- **Red Team Night.** The test itself. The red team proposes attacks, the simulator runs them, the blue
  team proposes fixes, the simulator runs those too, and only fixes that measurably help are kept.
- **The sandboxes.** Sealed boxes that each simulation runs in. Every attack and every fix gets its own
  box. See section 3.
- **The simulator.** JuPedSim, open-source research software that moves each person step by step. It,
  not the AI, says how crowded a spot gets and how long it takes to get out.
- **Real cases.** Three real disasters are rebuilt from a written description by the same Designer:
  - Itaewon 2022;
  - Love Parade 2010;
  - Hillsborough 1989.

  Showtime then tests each one. All three show the danger where it really happened. The layouts are
  approximations, not exact copies.
- **Test modes.** Quick (about 1 minute, short simulations), Standard, Deep (more rounds, full
  simulations) and Offline (no AI: hand-written rules stand in).
- **The plan and the handover checklist.** The results screen, plus downloads: a report with every number
  and its source, an evacuation map, a checklist of doors and staff actions, a 3D model file, and the raw
  data.
- **The Event Copilot ("Plan it for me").** One sentence to a finished, tested plan in a few minutes.
  It runs every step above in a row while you watch.

## 3. Why sandboxes are the core

The red team does not only fill in forms. For one attack per round, it **writes a small program**: a
disaster that reacts to the crowd ("when a door gets crowded, close it" or "smoke spreads from the
fullest area"). The Analyst also writes programs to answer questions from the data.

Code written by an AI is untrusted. It could try to reach the internet, read files on the machine, run
forever or eat all the memory. That would be dangerous to run on the organizer's computer.

So it runs only inside a sandbox: a throwaway container with these limits:
- no network;
- a read-only system;
- no admin rights;
- capped memory, processor and number of processes;
- a time limit.

Before that, a checker reads the code and refuses obviously unsafe things (such as `import socket` or
opening files). The checker is a first filter; the sandbox is the real wall. I checked today that the
containers really have no network, a read-only system, all rights dropped, a 2 GB memory cap, and no
API keys inside.

What a judge can see today: "AI-written scenario" cards with "Show the code", the Scripts page where you
can try your own script (an unsafe one is refused with a reason), and the AI team page listing the
sandbox limits.

What a judge cannot see today: a live view of the boxes starting, running and finishing, and why a
particular script was stopped while the test runs. Step 3 adds that.

## 4. Tavily today and after this session

Tavily is a web-search service. **Today it does nothing**: the code to call it exists (with a cache and a
call limit), but no agent uses it. The attacks are grounded in a dataset of 388 real crowd incidents
instead, cited by row.

After this session, the red team, the Brief and the Designer will be able to search the web for real
incidents and local rules, and cite what they find. They will still use the dataset when there is no key.
I do not have a key, so that part will be built and tested with a fake search service, switched off and
labelled "not run live".

## 5. Two words

- **The venue guide.** The written instructions the Designer agent reads before it lays out a venue
  (`api/agents/prompts/venue_designer.md`). It tells the model what it may choose, such as sizes, walls,
  floors, stairs and headcounts, and shows a few examples. Today it still leans towards stages and
  festival crowds; Step 5 makes it neutral for any building.
- **A provider.** The company or program that does a job for Showtime.
  - Today the AI models come from **OpenRouter** (free Nemotron models) and the sandboxes are **Docker**
    on this machine.
  - Later, the models can come from **Nebius Token Factory** and the sandboxes from
    **Nebius Sandboxes**.
  - Web search is a third kind of provider (Tavily).

## 6. The plan for this session

1. **Baseline.** Record what passes and fails today. Done when it is written in `docs/archive/BUILD_LOG.md`.
2. **Known bugs.** Verify and fix each listed bug. Done when each fix has a test that failed before and
   passes now.
3. **Sandboxes made visible.**
   - attack tests proving the walls hold;
   - a sandbox badge;
   - a live sandbox feed in "AI tests it";
   - the best sandbox moments easy to reach.

   Done when someone watching can say what runs, where, with what limits, and why a bad script stopped.
4. **Agents and evidence.** The red team searches through a search interface: the dataset now, Tavily
   later. It shows an Evidence panel and labels where each source came from. Done when every run shows a
   cited incident with its origin, and the Tavily path passes with a fake.
5. **Venue guide for any venue.** Neutral wording, examples for a metro station, a mall, a mosque and an
   airport or campus, and more feature kinds. Done when a before/after score on 8 descriptions does not
   drop.
6. **Key-ready plug-ins.** One interface and registry each for models, sandboxes and search, driven by
   capabilities. Each gets a readiness check and one command, `make verify-live`. Done when a new
   provider needs one new file and verify-live runs cleanly with no keys.
7. **Browser test and fixes.** Eight flows in Chrome, each logged pass or fail with a screenshot. Done
   when every flow passes or its failure is explained.
8. **The story.** README, pitch, demo, video script, judge guide and Q&A all tell the same, true story.
   Done when every claim matches what ran.
9. **Final check.** Every check, a fresh clone, and a plain-English report.

## 7. What I am unsure about, and what I need

- **The free model limit.** OpenRouter's free models allow about 50 requests a day per account, and a
  red-team test uses several. Two of the three keys may be on the same account. If they run out, live
  checks wait for the next day; tests use recorded replies and fakes.
- **Nebius.** I cannot run anything on Nebius without a key and Sandboxes access. Nebius Sandboxes cannot
  set a per-box network or memory limit the way Docker does (from the docs; to be confirmed live). On
  Nebius, the code checker and the limits inside the box are the protection.
- **The hackathon rule (R1)** asks that the project runs on Nebius Token Factory or AI Cloud. Until you
  have a key, that requirement is not met. It is the single most important key to get.
- **Decisions for you.** Nothing blocks me now. I will ask before pushing, deploying or deleting anything.

**How adding a key will work.** Each outside service (models, sandboxes, search) sits behind a small,
fixed interface. Each provider is one file that says which settings it needs, what it can do, and how to
make one tiny test call. The app picks the provider by its name in `.env`. With no key, it uses what works
today (OpenRouter, Docker, the incident dataset) and says so on screen. When you get a key:
1. Add it to `.env` and set the provider name (for example `LLM_PROVIDER=nebius` or `TAVILY_API_KEY=...`).
2. Run `make verify-live`. It makes one small real call per service and prints a pass/fail table with the
   exact fix for anything missing.

No code changes.
