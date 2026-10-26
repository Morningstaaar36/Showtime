# Hard questions, honest answers

**Is the simulator validated?**
Against one published experiment, yes. That is the Jülich bottleneck series: Düsseldorf 2006,
doors 0.9–2.5 m wide, about 175 people per run (DOI 10.34735/ped.2006.2, method of Seyfried et
al., *Transportation Science* 2009).
- **The result:** with one parameter calibrated (the time gap to the person ahead, 0.25 s, on
  half the widths), the simulator's flow through the door is within about 6 % of the real crowd's
  at every width. The median error is 4.0 %, and 4.4 % on the widths held out from calibration.
- **Without calibration:** the model's default let only about half as many people through.
- **The limits:**
  - one experiment, one group (calm young soldiers) and one kind of layout;
  - no pushing forces;
  - simulated bodies cannot overlap, so it cannot reach crush densities.

Help › *How good is the simulator?* shows this in the app; details are in
[VALIDATION.md](VALIDATION.md).

**Is this a safety certification?**
No. It is a planning aid, and every results screen and the report say "Planning aid, not a safety
certification". It finds where density climbs past the danger level (5 people per m²) under
stated assumptions (headcount, walking speed, behaviour) that are printed in the report. A
competent person still signs off the plan.

**Why sandboxes?**
The AI writes code: scenario scripts ("close the stairwell when its queue passes 40 people") and
analysis scripts that compute answers from the simulation data. That code is untrusted, so it only
ever runs inside a throwaway container. Every crowd simulation runs in one too. The same boundary
lets a crowd be saved at its worst second and many responses run from that point, and a stress
test fan out over many runs.

**What if the AI-written code is malicious?**
Two layers stop it.
1. **A static check before anything runs.** Only `math`, `statistics` and `random` may be
   imported in scenario scripts. There is no `open`, no dunder attributes and no frame walking.
2. **The container, the real boundary.** It has:
   - no network and a read-only system;
   - memory, CPU and process limits;
   - a non-root user and no API keys;
   - a time limit;
   - budgets per step inside the script API.

`make sandbox-proof` throws 14 attacks at the real container and records what stopped each one,
in the sandbox's own words (network unreachable, read-only file system, `MemoryError`, stopped
after 5 s, process limit). In every scenario-script case the crowd simulation still finished.
See [SANDBOX_PROOF.md](SANDBOX_PROOF.md) and the Sandbox section of Help.

**What is not live on Nebius?**
None of it has run live yet.
- **Built and tested with fake clients:** the Nebius Token Factory provider and the Nebius
  Sandboxes runner. `make verify-live` reports both as SKIPPED: no key, no access
  ([LIVE_STATUS.md](LIVE_STATUS.md)).
- **What runs today:** NVIDIA Nemotron (3.5 Lightning and 3 Ultra) through OpenRouter, and local
  Docker sandboxes.
- **Switching:** `.env` only. Set `LLM_PROVIDER=nebius` and `NEBIUS_API_KEY`; for the
  sandboxes, also `SANDBOX_PROVIDER=nebius` and `NEBIUS_PROJECT_ID`. `make verify-live` then
  checks each one live. No code changes: [WHEN_YOU_GET_THE_KEYS.md](WHEN_YOU_GET_THE_KEYS.md).

**What did Tavily add?**
Nothing live yet: we had no key, so Tavily has not been run live. The plug-in is wired in:
- the red team searches for incidents like the venue's and may cite only URLs that came back;
- the evidence desk looks up capacity and guidance;
- every source carries an origin badge.

Tests with a fake client prove that plumbing. Without a key the app says "Web search is off (add
a Tavily key to switch on)", and attacks cite real crowd accidents instead: 388 from the
Feliciani dataset (1900–2024) and 7 well-known ones with Wikipedia sources.

**Where do the numbers come from?**
From the simulator (JuPedSim), formulas and cited data, never from the language model. A number
check rejects any agent text that quotes a number the tools did not produce. Each number on
screen says whether it is an instant estimate or confirmed by simulation.

**How do you know a fix works?**
- Each fix is simulated again against the attack that broke the plan.
- It is kept only if it removes the break or measurably improves without making any outcome
  worse.
- "Rewind the worst moment" runs "do nothing" and each response from the same second.
- "Check with more seeds" gives the range over several random crowds.

**Are the real cases accurate?**
They are rebuilds, not forensic findings. The designer builds them from published dimensions,
with at most 3,000 simulated people. They show that the layout and the flows produce dangerous
density near where the real crush was. They reproduce no forces, falls or timeline.

The current designer still gets some things approximate:
- Itaewon's alley is drawn mirrored;
- Love Parade's ramp is as wide as the tunnel.

[REAL_CASES.md](REAL_CASES.md) and the Step 5 entry in [BUILD_LOG.md](BUILD_LOG.md) list what
is approximate.

**Are the headline results repeatable?**
They are single live runs, labelled as such: the two-floor conference hall result, the
real-case densities and the designer fidelity scores. The simulator itself is deterministic per
seed. The model's choices vary between runs, and every one of them is checked by simulation.

**What happens when the model is down or out of quota?**
- The badge says so: the hosted model is paused until a stated time, and whether a local model
  is taking over.
- Errors say what to do.
- **Offline** mode tests the plan with rule-based attacks and fixes, still in the sandbox.
