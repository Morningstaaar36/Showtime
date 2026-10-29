# Developer-internal README sections (archived 2026-10-29)

Moved out of `nebius/README.md`, unchanged apart from link paths. The `make m1-test-*` targets
and the scene and plan APIs still exist; these notes are for developers, not judges.

## Local M1 test setup (OpenRouter, Docker)

Install Docker Desktop for Apple Silicon and use the host's `python3`:

```bash
cd nebius
make m1-test-init
# Add OPENAI_COMPAT_API_KEY to the generated .env using your editor.
make m1-test-up
make m1-test-smoke
```

Open <http://localhost:5173>. The API and web UI run on ARM; the JuPedSim container runs
with `linux/amd64` emulation. The launcher builds dependencies in Docker, starts Docker
Desktop if needed, and waits for the services. No host Python packages, CUDA server,
model weights, Nebius key, or Tavily key are needed. Existing `.env` settings are preserved.

Templates, saved examples, editing, and local simulations work without an OpenRouter key.
AI conversation and agent features require the key and available model quota.
`make m1-test-smoke` checks the UI, API proxy, and an actual 20-person simulation without AI calls.

Use `make m1-test-status`, `make m1-test-logs`, and `make m1-test-down` for status, logs, and shutdown.
Restart built images with `make m1-test-start`, including after updating `.env`.
Use `make m1-test-up` to rebuild after source or dependency changes.
The profile files and commands are explicitly named for M1 testing. The recorded startup
verification was performed on an M1; this is a local development profile.
See [the M1 test setup guide](M1_TEST_SETUP.md) for configuration and troubleshooting.

### Scene inspection API (P2-01)

`GET /api/v1/projects/{id}/scene` returns the full versioned venue with units and provenance.
`GET /api/v1/projects/{id}/scene-facts` computes areas, connected components, reachable exits,
point clearances, and bounded geometric routes without AI or simulation calls.
See [the interface and prepared test procedure](SCENE_INSPECTION.md).

### Organizer plan API (P2-02)

Save organizer constraints and timed operational actions alongside the venue through
`GET/PUT /api/v1/projects/{id}/plan`. Preview and apply complete bundles with version
checks, locks, approvals, dependency checks, and staff/equipment allocation validation.
Runs use saved actions and expose evidence applicability against the current plan.
See [the backend contract](PLAN_CONSTRAINTS.md) and [M1 tests](P2_02_TESTING.md).

