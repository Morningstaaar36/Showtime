# Showtime — local M1 test setup

This profile is for local startup and testing on an M1 Mac. It also accepts other Apple
Silicon Macs, but the recorded verification below was performed on the user's M1.
The M1 test launcher uses OpenRouter for AI, ARM containers for the API and web UI, and an
x86 Linux container for JuPedSim. Application dependencies are installed inside Docker.

Profile files: `scripts/m1_test.py`, `docker-compose.m1-test.yml`, and
`config/m1-test.env.example`. Commands use the `m1-test-*` prefix. Shared API/Docker
changes support this profile as well as the existing application setup.

## Start

Prerequisites: Docker Desktop for Apple Silicon and `python3` on the host. The machine
this setup was prepared on already has both. Allow at least 4 GB of memory for Docker;
builds and larger simulations may need more. Start with small crowds and one simulation
at a time on an 8 GB Mac.

```bash
cd /Users/ridhwanasif/Downloads/Nebius/Showtime/nebius
make m1-test-init
```

This creates a private, ignored `.env` from `config/m1-test.env.example` and the runtime
directories. Existing `.env` contents are preserved. Add your OpenRouter API key to:

```dotenv
OPENAI_COMPAT_API_KEY=YOUR_KEY
```

Then:

```bash
make m1-test-up
```

The launcher starts Docker Desktop when necessary, builds the simulator and application
images, and starts the Compose project named `showtime`. The profile retains the existing
project name, runtime directories, and ports, so it reuses the previously tested local
stack and saved projects; it is not a separate simultaneous installation.
Initial builds download dependencies;
later builds reuse Docker layers. Services listen only on the local machine.

- App: <http://localhost:5173>
- API documentation: <http://127.0.0.1:8000/api/docs>

Without an API key, you can still use templates, saved examples, the manual editor, estimates,
and real crowd simulations. AI features report unavailable rather than trying to start a
CUDA model on your Mac. Nebius and Tavily keys are optional for this development path.

## Existing configuration

If `make m1-test-init` finds an existing `.env`, configure the following values yourself:

```dotenv
LLM_PROVIDER=openai
OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPAT_API_KEY=YOUR_KEY
OPENAI_COMPAT_LABEL=OPENROUTER
MODEL_FAST=nvidia/nemotron-3-super-120b-a12b:free
MODEL_LONG=nvidia/nemotron-3-super-120b-a12b:free
MODEL_MAIN=nvidia/nemotron-3-super-120b-a12b:free
MODEL_JUDGE=nvidia/nemotron-3-super-120b-a12b:free
LLM_SUPPORTS_JSON_SCHEMA=false
LLM_EXTRA_BODY='{"reasoning":{"enabled":false}}'
LLM_FALLBACK=none
SANDBOX_PROVIDER=docker
SANDBOX_MAX_PARALLEL=1
SIM_PLATFORM=linux/amd64
SIM_IMAGE=showtime-sim:latest
SIM_MEM_LIMIT=2g
SIM_CPUS=2
```

The free model ID is configurable and its availability and quota can change. Check the
[OpenRouter model page](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free).
Every session can make several requests; begin with the small session defaults in the Mac
template. Disabling local fallback avoids requests to a nonexistent local model server.

After changing only `.env`, use `make m1-test-start` to recreate services with the existing
images. Use `make m1-test-up` after application code or dependency changes.

## Verify

```bash
make m1-test-status
make m1-test-smoke
```

Status distinguishes service availability from provider readiness. A running API does
not mean the model key or quota is valid. The container readiness check uses the templates
endpoint so an unavailable external provider cannot prevent the UI from starting.

The smoke check consumes no model requests. It creates a temporary 20-person room, saves
and reloads a manual door-width edit, runs JuPedSim through the API, confirms everyone
exits, downloads trajectory and density data,
and removes the temporary project. It exercises the host directory mount used by simulation
containers. It does not claim to verify AI responses or comprehensive modeling accuracy.

## Explore without an API key

Open the app and choose one of the three projects marked **Sample**. They contain saved
sessions and replay data, so reviewing their layouts and results requires no AI requests.
These are recorded examples rather than new live model runs.

To create your own project, pick a venue template on the Projects screen. Use the visual
editor and inspector to adjust objects, then choose **Simulate → Run stress test**. Start
with a small headcount while testing your setup. The conversation, Copilot, new red-team
sessions, and AI explanations become available after adding an OpenRouter key.

## Verification on this Mac

Verified on 10 October 2026 with an ARM Docker Desktop daemon:

- API and web containers started successfully and passed readiness checks.
- All three bundled samples loaded with 29 saved simulation runs in total.
- A manual exit-width edit was saved and reloaded through the API.
- A fresh 20-person JuPedSim run completed through the Docker adapter with no people
  remaining; its time for 95% to exit was 12.1 simulated seconds.
- Trajectory and density artifacts were downloaded through the running API.
- The 30 selected API, OpenRouter-adapter, and persistence regression tests passed.

The isolated test command used `--basetemp=/tmp/showtime-tests` because the production
image does not contain the host's runtime cache directory. Initial builds were slow on
this machine and encountered a registry timeout; `make m1-test-start` successfully started
the completed images without contacting registries. OpenRouter completions were not
tested because no key was supplied.

## Logs and shutdown

```bash
make m1-test-logs
make m1-test-down
```

Shutdown retains projects, caches, and simulation output. `Ctrl+C` exits log following.
Restart with `make m1-test-start` to use the built images without registry or package downloads.
If an image is missing, it directs you to `make m1-test-up` to build it first.
For the M1 test stack, use the `m1-test-*` commands consistently so the same Compose project and
ARM override are used. They work regardless of the shell's current `PWD` because the
launcher resolves the application directory from its own location.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker unavailable | Start Docker Desktop and wait for it to finish initializing; retry `make m1-test-up`. |
| AI unavailable | Check the key, configured model IDs, and quota; recreate services after editing `.env`. |
| Build cannot download packages or images | Check network/proxy access and retry. If all images were already built, use `make m1-test-start` to run them without contacting registries. |
| Port 8000 or 5173 occupied | Stop the application using that port, then retry. |
| Simulation exits with code 137 | Increase Docker memory or reduce crowd size; keep concurrency at one. |
| Simulation reports a mount or permission error | Use the launcher so `HOST_RUNS_DIR` is the absolute host directory; check Docker file sharing for this repository. |
| API fails its readiness check | Inspect `make m1-test-logs`; dependency imports and migration errors appear there. |
| x86 simulation fails to execute | Confirm Docker Desktop supports amd64 emulation; optional Rosetta acceleration can improve speed. |

The API Docker client is selected using Docker's `TARGETARCH`; only simulations are forced
to x86. This avoids emulating the complete stack. Docker documents the architecture and
emulation behavior in its [multi-platform guide](https://docs.docker.com/build/building/multi-platform/).

The legacy `make setup`, `make llm-up`, and native `make dev` paths target Linux/NVIDIA
development. Use this Mac workflow for hosted models and local Docker simulations.
