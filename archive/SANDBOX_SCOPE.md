<!-- Agreed with the team lead on 2026-10-15; supersedes the sandbox parts of plan.md (N04) and PRODUCT_PRIORITIES.md. -->

# Showtime: make sandboxes crucial (all five ideas)

## Context

Today the AI only fills in forms (JSON), so sandboxes are "nice to have". The new scope makes them essential: **the AI writes code** (new disaster scenarios and data analyses), and that code runs only inside sealed, disposable sandboxes. Snapshots let us rewind a disaster and try many responses from the same second, and parallel sandboxes run many tests at once.

New one-line story: *"AI red-team agents program new crowd-disaster scenarios, run each in its own sandbox against a real crowd simulator, rewind the worst moment to test responses in parallel, analyse the results with code they write, and hand the organizer a tested plan."*

Everything else (map, venue check, Your plan, checklist) stays. The 3 paused agents (real-life examples, Live Ops/share, steward cards/seeds/export) are parked: their branches are kept but not merged now.

## The shared foundation: one sandbox job type for code

- **`SandboxRunner` gains `run_code(job: CodeJob) -> CodeResult`** in `api/adapters/sandbox.py`, implemented for DockerRunner and NebiusRunner, plus a fake.
  - `CodeJob`: `{job_id, kind: "analysis" | "user_script", script, inputs: {filename: bytes}, timeout_s, mem}`.
  - It runs `python /app/run_code.py /work` in the existing sim image (numpy, pandas, shapely, pedpy are already there): no network, non-root, memory/CPU/pids caps, wall timeout.
  - `CodeResult`: `{status: ok | error | timeout, output (JSON the script printed), stdout_tail, stderr_tail, runtime_s}`.
- **Guard layers:** an AST pre-check is a quality filter, not the security boundary. It rejects imports outside an allow-list, dunder access, `open`/`exec`/`eval`/`__import__`, and anything over 8 KB. The sandbox is the security boundary. Every script, its source (AI or user), its output and its runtime is stored and shown.
- **Nebius fix (same work):** a per-run work folder `/work/<run_id>/`, so a child snapshot can never return its parent's results.

## Idea 1: AI writes new disasters as code

- **New scenario event `script`:** `{type: "script", title, code, every_s: 1}` (events plugin plus a sim handler in `sim/plugins/events.py`).
  - The handler compiles the code once and calls `on_step(view, act)` every `every_s` seconds of simulated time.
  - `view` is read-only: `t`, per-zone and per-exit people and density, exits open or closed, queue lengths.
  - `act` is the only way to change the world: `close_exit`, `open_exit`, `redirect(from, to, fraction)`, `add_people(zone, n)`, `slow_down(factor)`, `note(text)`. Each maps onto the existing ctx helpers (`switch`, `hold_at_blocked_exit`, `best_exit`, `log_event`, spawn helpers).
  - The API lives in a small `sim/script_api.py`; script errors become run notes, not crashes.
- **Red team** (`api/agents/red_team.py` + prompt): it may return a `script` attack (title, rationale, incident source, code) next to menu events.
  - Validation: the AST check plus a dry run against a tiny fake view.
  - Instant-estimate screening can't execute code, so script attacks skip tier-1 ranking and go straight to a quick simulation, labelled as such.
- **UI:** attack cards show "AI-written scenario", with the code behind "Show the code" (AI at work, Your plan, Expert view red team).

## Idea 2: AI crowd analyst

- **New ask intent `analyse`:** "How long did people queue at Gate B?" or "Which minute was worst?"
  - The `analyst` agent writes a pandas script against a documented data helper (`sim/showtime_data.py`: trajectories, density grid, exits and zones as DataFrames).
  - `run_code` runs it with the run's artifacts as inputs.
  - The answer quotes only numbers the script printed (number check), and shows a small table or chart plus the code.
- **Router:** `api/agents/router.py` gains the `analyse` intent, with keyword fallback ("how long", "how many", "which minute", "queue", "chart"). Endpoint `POST /projects/{id}/analyse` (also reachable through ask-anything).

## Idea 3: Rewind and branch at the critical moment

- **Sim:** request fields `checkpoint_at_s` and `resume`.
  - With `checkpoint_at_s`, `run_sim` writes `checkpoint.json` at that time: per agent position, target exit, kind and desired speed; exit states; pending spawns.
  - With `resume`, it starts from `checkpoint.json` instead of populating, then applies the response events.
  - Velocities restart (documented approximation). Single-floor venues only at first; multi-floor says "not available yet".
- **Branching:** `SimJob.resume_from = <checkpoint run id>`.
  - Locally the runner copies the checkpoint into the child's folder.
  - On Nebius the child is a snapshot branch of the checkpoint run, so the checkpoint is already inside it. This is where snapshots are essential.
- **Orchestration:** `POST /sessions/{id}/rewind {at_s?, responses?}`.
  - Defaults to the moment of peak danger in the worst attack's run.
  - Responses: the kept fixes plus AI- or rule-suggested quick actions (open a gate, send stewards, pause the show).
  - All branches run in parallel; results are compared with the "do nothing" branch from the same moment.
- **UI:** on Your plan, "Rewind the worst moment" opens a small comparison: each response, its effect and its evidence label.

## Idea 4: Massive parallel tests

- **Session:** the screened attacks of a round, and the fixes for an attack, run with `asyncio.gather`. Concurrency is bounded by the runner: Docker 1–2 locally, Nebius `SANDBOX_MAX_PARALLEL`. Results are processed in a deterministic order, and stop cancels the pending tasks.
- **"Stress test at scale"** (Expert view and Your plan): attacks × kept fixes × seeds fan out at once, with a live counter ("47 of 60 done") and a table of failures. It reuses the existing sweep and seed handling where possible.
- **Local default:** `SANDBOX_MAX_PARALLEL=2` if memory allows; the memguard remains.

## Idea 5: Bring your own model

- **Expert view → "Scripts":** an organizer or engineer writes or uploads their own scenario script (same API as idea 1) or analysis script (same helper as idea 2).
- Scripts are saved per project with author "you". "Run in sandbox" uses the same `script` event or `run_code` job. Output and code are shown and kept with the run.

## Who builds what (three agents in parallel worktrees, then I integrate)

- **A, sim + scripts (ideas 1, 5-sim, 3-sim):** `sim/` (`script_api.py`, the `script` event, checkpoint/resume, `run_code.py`, `showtime_data.py`), the events plugin, red-team script attacks plus validation, script attack cards.
- **B, sandbox code jobs + analyst (foundation, idea 2, idea 5 UI):** `run_code` in Docker, Nebius and fake runners; Nebius per-run folders and checkpoint inheritance; the analyst agent, route and router intent; the Scripts page.
- **C, orchestration (ideas 3, 4):** parallel session branches, the rewind endpoint and UI, the stress-test-at-scale fan-out, request/job fields (`checkpoint_at_s`, `resume`, `resume_from`).
- **Shared contracts, decided now so the work merges:** `CodeJob`/`CodeResult` above; the `script` event fields; the `view`/`act` API names; request fields `checkpoint_at_s` and `resume`; `SimJob.resume_from`; the checkpoint filename `checkpoint.json`.
- **Rules:** many small commits; no live LLM or Docker in agent tests (fakes); I run the real-Docker and live-LLM checks after merging.

## Verification (me, after merging)

1. Lint, mypy, import contracts, pytest, vitest, Playwright: all green.
2. **Real Docker:**
   - an AI-written script attack runs, changes the crowd, and the notes show its actions;
   - a deliberately malicious script (network, file write, endless loop) is rejected by the pre-check or contained by the sandbox (no network, timeout);
   - analyst questions answered from code output;
   - rewind on the conference hall gives a "do nothing" branch plus 3 responses from the same second, in parallel when 2 or more are allowed;
   - a stress test at scale finishes with the right counts.
3. **Live LLM (OpenRouter):** a full session with at least one AI-written scenario; one analyst question.
4. **Browser walk-through** of every screen; then rebuild with `make up`; update the docs (DEMO, NEBIUS_SWITCH, README story).
5. **Nebius Sandboxes:** same tests with `SANDBOX_PROVIDER=nebius` once access exists. The fake-SDK tests cover branching and per-run folders until then.
