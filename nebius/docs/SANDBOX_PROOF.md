# Sandbox proof: attacks on the sandbox and what stopped them

The AI writes code: scenario scripts (the red team's "AI-written scenario") and analysis scripts (the
analyst). You can also write your own on the Scripts page. That code is untrusted, so it only ever runs
inside a sealed, throwaway Docker container. This page lists what was thrown at that container and
what happened.

**Nothing below is typed in by hand.** `make sandbox-proof` runs
`api/tests/test_sandbox_attacks_docker.py` against the real sandbox and records each result, in the
sandbox's own words, in `api/data/sandbox_proof.json`. The app shows that file in Help > Sandbox
(`GET /api/v1/sandbox/proof`), and `python scripts/sandbox_proof_md.py` writes the tables below
from it.

## How the attacks are run

- **Production path.** Every container is started by the app's own code. Scenario scripts go
  through `RunService.build_job` → `DockerRunner.run`; code jobs through `DockerRunner.run_code`.
- **Container flags** come from settings:
  - `--network=none`
  - `--read-only` (writable `/tmp` only)
  - `--cap-drop=ALL` and `--security-opt=no-new-privileges`
  - `--pids-limit` (`SIM_PIDS_LIMIT`, `CODE_PIDS_LIMIT`)
  - `--memory` and `--memory-swap` (`SIM_MEM_LIMIT`; the attack suite uses 1 GB)
  - `--cpus` (`SIM_CPUS`)
  - a non-root user
  - a wall-clock limit (`MAX_WALL_S`)
- **No API keys** are passed into the container: the "read the environment" attack checks this.

There are two layers:
1. **A static check before anything runs.** `api/core/scripts.py` for scenario scripts,
   `api/core/analysis_check.py` for analysis scripts. It is a quality filter that gives a clear
   reason.
2. **The container**, which is the security boundary. A copy of the static check runs again inside
   it, and the script API enforces budgets. Each budget is a setting sent with every run that has a
   script:
   - `SCRIPT_CALL_S` and `SCRIPT_TOTAL_S`: time per call and per run;
   - `SCRIPT_LINE_BUDGET`: lines run per call;
   - `SCRIPT_MAX_ACTS_STEP` and `SCRIPT_MAX_ACTS_TOTAL`: actions per call and per run;
   - `SCRIPT_MIN_SPEED_SHARE`: how far slow-downs may go in total;
   - `SANDBOX_MEMORY_SHARE`: heap growth once untrusted code runs.

Scripts the static check refuses are also written straight into the job, as if they had slipped
past the API. This proves the container refuses them on its own.

## Results

<!-- proof:start (written by scripts/sandbox_proof_md.py) -->
Recorded 2026-10-25T10:06:15+00:00 on Docker 29.9.2 with `showtime-sim:latest` (`make sandbox-proof`).

### Scenario scripts (AI-written disasters, run inside the crowd simulation)

| Attack | Static check | Inside the container (the sandbox's own words) | Result |
| --- | --- | --- | --- |
| Connect to the internet | refused: Line 1: import of 'socket' is not allowed (only math, statistics, random). | it failed the safety check (Line 1: import of 'socket' is not allowed (only math, statistics, random).) | ok, 0.8 s |
| Run shell commands | refused: Line 1: import of 'os' is not allowed (only math, statistics, random). | it failed the safety check (Line 1: import of 'os' is not allowed (only math, statistics, random).) | ok, 0.8 s |
| Open a file | refused: Line 2: 'open' is not allowed in scenario scripts. | it failed the safety check (Line 2: 'open' is not allowed in scenario scripts.) | ok, 0.8 s |
| Reach Python's internals (__class__) | refused: Line 2: attribute '__subclasses__' is not allowed (no dunder attributes). | it failed the safety check (Line 2: attribute '__subclasses__' is not allowed (no dunder attributes).) | ok, 0.8 s |
| Walk interpreter frames | refused: Line 3: attribute 'f_back' is not allowed in scenario scripts. | it failed the safety check (Line 3: attribute 'f_back' is not allowed in scenario scripts.) | ok, 0.8 s |
| Run forever | passes (valid code) | one step ran more than 200,000 lines | ok, 0.9 s |
| Grab 8 GB of memory | passes (valid code) | it tried to use more memory than the sandbox allows (MemoryError) | ok, 0.8 s |
| Flood the crowd with actions | passes (valid code) | one step took longer than 50 ms | partial, 1.8 s |

### Code jobs (the analyst's code and your own scripts)

| Attack | Static check | Inside the container (the sandbox's own words) | Result |
| --- | --- | --- | --- |
| Connect to the internet | refused: Line 1: importing 'socket' is not allowed (only json, math, numpy, pandas, showtime_data, statistics). | OSError: [Errno 101] Network is unreachable | error, 0.28 s |
| Write a file | refused: Line 1: open() is not allowed in an analysis script. | OSError: [Errno 30] Read-only file system: '/work/x.txt' | error, 0.27 s |
| Read the environment for API keys | refused: Line 1: open() is not allowed in an analysis script. | ran; no API keys in its environment | ok, 0.27 s |
| Run forever | passes (valid code) | The script ran longer than 5 s and was stopped. | timeout, 5.27 s |
| Grab 8 GB of memory | passes (valid code) | The script stopped with an error (out of memory). | error, 0.65 s |
| Start thousands of processes | refused: Line 1: importing 'os' is not allowed (only json, math, numpy, pandas, showtime_data, statistics). | BlockingIOError: [Errno 11] Resource temporarily unavailable | error, 0.76 s |
<!-- proof:end -->

In every scenario-script case the crowd simulation still finished, so an attack cannot take a test
down with it.

## What this session changed to make these pass

The suite found two real gaps; both are fixed:

- **Memory.** A scenario script that allocated 8 GB got the whole simulation killed by the kernel
  (exit 137, run lost). Now, once the simulator is loaded and just before untrusted code runs,
  `sim/memory_cap.py` sets a heap limit. The limit is the process's current data size plus
  `SANDBOX_MEMORY_SHARE` of the memory the container has left. A runaway allocation becomes a
  `MemoryError` that stops only the script. This applies only inside the image
  (`SHOWTIME_SANDBOX=1`).
- **Freezing the crowd.** `act.slow_down` multiplied speeds with no floor: repeated calls could bring
  people to almost zero speed and make any plan look broken. All of a script's slow-downs together
  now stop at `SCRIPT_MIN_SPEED_SHARE` of normal speed.

## Limits (honest)

- **Nebius Sandboxes** (`SANDBOX_PROVIDER=nebius`) cannot set a per-job network or memory limit
  the way Docker does. There, the static check and the in-sandbox budgets are the protection. The
  Nebius runner has **not been run live** (no access yet).
- The static check is a filter, not a proof. The container is the boundary, and it is what the
  "inside the container" column tests.
- The memory cap uses `RLIMIT_DATA`. Native code that maps memory another way is still stopped by
  the container's `--memory` limit, but then the run is lost rather than only the script.
