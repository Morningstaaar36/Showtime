# Showtime: Red Team Night

**From one sentence to a crowd-safety plan you can defend.**

Showtime is a crowd-safety planning studio for event organizers, venue managers and permit
offices. Describe an event in one sentence and the **Event Copilot** (NVIDIA Nemotron) pulls the
real site from OpenStreetMap, lays out the event, estimates safe capacity, exits, stewards and
budget from published planning guides, and runs a real crowd simulation (JuPedSim). **Red Team
Night** then lets AI attackers break the plan with scenarios grounded in real crowd incidents and
AI defenders fix it, keeping only measured improvements, down to **the latest safe time to start
evacuating**.

> Planning aid, not a safety certification.

![Event Copilot planning a concert at Ramna Park](nebius/docs/screenshots/copilot.png)

The full product description, screenshots and how NVIDIA Nemotron, Nebius Token Factory and
Nebius Sandboxes are used are in [nebius/README.md](nebius/README.md).

## Repository layout

```
.
├── README.md             # this file
├── requirements.txt      # Python API dependencies for a plain pip install
└── nebius/               # the application
    ├── api/              # FastAPI backend: agents, orchestrator, adapters, core, SQLite (uv project)
    ├── sim/              # simulation sandbox image: JuPedSim + PedPy
    ├── web/              # Vite + React + React Three Fiber frontend
    ├── plugins/          # built-in feature plugins (hazards, exporters, importers, rules, ...)
    ├── scripts/          # setup, model download, probes, smoke tests, demo precompute
    ├── config/           # plugin feature flags
    ├── docs/             # architecture, assumptions, user and testing guides, ADRs
    ├── Makefile          # all common tasks (`make help`)
    ├── docker-compose.yml
    └── .env.example      # configuration template
```

## Requirements

| Requirement | Version / notes |
| --- | --- |
| OS | Linux (x86_64) |
| Python | 3.12 (installed for you by `make setup` via uv) |
| Node.js | 20 or 22 LTS (frontend) |
| Docker | with Docker Compose v2; runs the app stack and the simulation sandbox |
| NVIDIA GPU | ~7 GB free VRAM for the local Nemotron Nano 9B v2 model (not needed with `LLM_PROVIDER=nebius`) |
| RAM | 16 GB recommended |
| Optional keys | `NEBIUS_API_KEY` (Token Factory / Sandboxes), `TAVILY_API_KEY` (live web evidence) |

Python packages are listed in [requirements.txt](requirements.txt) (mirrors
[nebius/api/pyproject.toml](nebius/api/pyproject.toml)); simulator packages are pinned in
[nebius/sim/requirements.txt](nebius/sim/requirements.txt) and installed into the sim image.
Frontend packages are in [nebius/web/package.json](nebius/web/package.json).

## Quickstart

```bash
cd nebius
cp .env.example .env
make setup        # uv, Python 3.12, API + web deps, sim image, llama.cpp, Nemotron GGUF, data
make llm-up       # local Nemotron Nano 9B v2 on the GPU
make up           # Docker Compose → http://localhost:5173  (API docs: http://127.0.0.1:8000/api/docs)
```

Three sample projects (an Itaewon-style alley, a two-floor hall and a festival field in a storm)
install automatically with finished red-team sessions, so you can explore right away.

Without Docker for the app: `make dev` runs the API and the Vite dev server natively.

### Plain pip instead of uv

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd nebius
export PYTHONPATH="$PWD"
(cd api && python -c "from api.db.session import migrate; migrate()")
(cd api && uvicorn api.app.main:app --host 127.0.0.1 --port 8000)
```

Simulations still need the sandbox image: `make build-sim` (from `nebius/`).

### Switch to Nebius

Set `LLM_PROVIDER=nebius`, `SANDBOX_PROVIDER=nebius`, `NEBIUS_API_KEY` and the `MODEL_*` ids in
`nebius/.env`, then run `make smoke-nebius`. Details: [nebius/docs/NEBIUS_SWITCH.md](nebius/docs/NEBIUS_SWITCH.md).

## Common tasks

Run from `nebius/`:

| Command | What it does |
| --- | --- |
| `make help` | List all targets |
| `make check` | Lint, typecheck and fast unit tests |
| `make test` | Full Python tests, including simulation tests (needs Docker) |
| `make test-web` | Frontend unit tests |
| `make smoke` | End-to-end smoke test against the running API |
| `make down` / `make llm-down` | Stop the stack / the local model |

## Documentation

[User guide](nebius/docs/USER_GUIDE.md) · [Testing guide](nebius/docs/TESTING_GUIDE.md) ·
[Architecture](nebius/docs/ARCHITECTURE.md) · [Extending](nebius/docs/EXTENDING.md) ·
[Assumptions](nebius/docs/ASSUMPTIONS.md) · [Security](nebius/SECURITY.md) ·
[Contributing](nebius/CONTRIBUTING.md) · [Licences](nebius/docs/LICENSES.md)

## License

Apache-2.0, see [nebius/LICENSE](nebius/LICENSE).
