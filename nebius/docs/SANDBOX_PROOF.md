# Sandbox proof: attacks on the sandbox and what stopped them

The AI writes code: scenario scripts (the red team's "AI-written scenario") and analysis scripts (the
analyst). You can also write your own on the Scripts page. That code is untrusted, so it only ever runs
inside a sealed, throwaway Docker container. This page lists what was thrown at that container and
what happened.

- **Run on:** 2026-10-25, local Docker 29.9.2, image `showtime-sim:latest`.
- **Tests:** `api/tests/test_sandbox_attacks_docker.py`.
- **Command:**
  ```
  cd api && DOCKER_CONTEXT=default uv run pytest -q -s tests/test_sandbox_attacks_docker.py
  ```
- **Production path:** every container is started by the app's own code. Scenario scripts go through
  `RunService.build_job` → `DockerRunner.run`; code jobs through `DockerRunner.run_code`.
- **Container flags:**
  - `--network=none`
  - `--read-only` (writable `/tmp` only: 256 MB, noexec)
  - `--cap-drop=ALL`
  - `--security-opt=no-new-privileges`
  - `--pids-limit=256`
  - `--memory` and `--memory-swap` capped (1 GB in these tests; `SIM_MEM_LIMIT`, default 2 GB, in the app)
  - `--cpus` capped
  - non-root user
  - a wall-clock limit
- **No keys:** the environment holds no API keys (checked by "read secrets" below).
- **Result:** 28 attack tests passed. Together with the earlier simulator script tests and the
  script and code-job unit tests, 93 passed in 47.9 s.

There are two layers:
1. **A static check before anything runs.** `api/core/scripts.py` for scenario scripts,
   `api/core/analysis_check.py` for analysis scripts. It is a quality filter that gives a clear
   reason.
2. **The container**, which is the security boundary. A copy of the static check runs again inside
   it, and the script API enforces time, line, action and memory budgets.

For the in-container rows of the five statically refused scenario scripts, the script was written
straight into the job, as if it had slipped past the API. This proves the container refuses it on
its own.

## Scenario scripts (AI-written disasters, run inside the crowd simulation)

| Attack | Static check | Inside the container (real note from the run) | Run |
| --- | --- | --- | --- |
| `import socket` and connect out | refused: import of 'socket' is not allowed | `scenario script stopped: it failed the safety check (Line 1: import of 'socket' is not allowed (only math, statistics, random).)` | finished (ok, 0.8 s) |
| `import os`, `os.system(...)` | refused: import of 'os' is not allowed | `… it failed the safety check (Line 1: import of 'os' is not allowed …)` | finished (ok) |
| `open('/work/request.json')` | refused: 'open' is not allowed | `… it failed the safety check (Line 2: 'open' is not allowed in scenario scripts.)` | finished (ok) |
| `().__class__.__bases__[0].__subclasses__()` | refused: '__class__' (no dunder attributes) | `… it failed the safety check (Line 2: attribute '__subclasses__' is not allowed (no dunder attributes).)` | finished (ok) |
| generator frame walk `g.gi_frame.f_back` | refused: 'gi_frame' | `… it failed the safety check (Line 3: attribute 'f_back' is not allowed in scenario scripts.)` | finished (ok) |
| `while True: pass` | passes (it is valid Python) | `scenario script stopped: one step ran more than 200,000 lines` | finished (ok, 0.9 s) |
| `x = [0] * 10**9` (8 GB) | passes | `scenario script stopped: it tried to use more memory than the sandbox allows (MemoryError)` | finished (ok, 0.8 s) |
| 100,000 × `act.note` + `act.slow_down(0.5)` | passes | at most 20 actions in one step; slow-downs stop at 10 % of normal speed ("slow_down ignored: people are already at 10% speed"); then `scenario script stopped: one step took longer than 50 ms` | finished (partial: everyone slowed to 10 %, nobody frozen) |

In every case the crowd simulation still finished, so an attack cannot take a test down with it.

## Code jobs (the analyst's code and your own scripts)

| Attack | Pre-check | Inside the container (real output) | Result |
| --- | --- | --- | --- |
| `socket.create_connection(('1.1.1.1', 53))` | refused: 'socket' | `OSError: [Errno 101] Network is unreachable` | error in 0.28 s |
| `open('/work/x.txt', 'w')` | refused: open() | `OSError: [Errno 30] Read-only file system: '/work/x.txt'` | error in 0.28 s |
| read `/proc/self/environ` (steal keys) | refused: open() | ran: the environment holds no API key and no `sk-…` value | nothing to steal |
| `while True: pass` | passes | `The script ran longer than 5 s and was stopped.` | timeout in 5.3 s |
| `x = [0] * 10**9` | passes | `The script stopped with an error (out of memory).` | error in 0.64 s; only this job's container stopped |
| fork bomb (`os.fork()` × 2,000) | refused: 'os' | `BlockingIOError: [Errno 11] Resource temporarily unavailable` (process limit 256) | error in 0.58 s |

## What this session changed to make these pass

The suite found two real gaps; both are fixed:

- **Memory.** A scenario script that allocated 8 GB got the whole simulation killed by the kernel
  (exit 137, run lost). Now, once the simulator is loaded and just before untrusted code runs,
  `sim/memory_cap.py` sets a heap limit. The limit is the process's current data size plus 85 % of
  the memory the container has left. A runaway allocation becomes a `MemoryError` that stops only
  the script. This applies only inside the image (`SHOWTIME_SANDBOX=1`).
- **Freezing the crowd.** `act.slow_down` multiplied speeds with no floor: 20 calls a step could
  bring people to 10⁻²⁰ of their speed and make any plan look broken. All of a script's slow-downs
  together now stop at 10 % of normal speed.

## Limits (honest)

- **Nebius Sandboxes** (`SANDBOX_PROVIDER=nebius`) cannot set a per-job network or memory limit
  the way Docker does. There, the static check and the in-sandbox budgets above are the protection.
  The Nebius runner has **not been run live** (no access yet).
- The static check is a filter, not a proof. The container is the boundary, and it is what the
  "inside the container" column tests.
- The memory cap is set with `RLIMIT_DATA`. Native code that maps memory another way is still
  stopped by the container's `--memory` limit, but then the run is lost rather than only the script.
