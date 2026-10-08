# Security

Showtime is a **local-first** tool. Defaults:

- The API binds to `127.0.0.1` (Compose publishes ports on `127.0.0.1` only); CORS allows only the web origin.
- API keys (Nebius, Tavily) stay in `.env` on the server side and are never sent to the browser (`/api/v1/settings` returns a safe subset).
- Uploads are limited to 5 MB and to `.showtime.zip`, `.json` and `.dxf`.
- Simulations run in short-lived containers with `--network=none`, a non-root user, `--security-opt=no-new-privileges`, `--pids-limit=256`, and memory/CPU caps.
- Agents never execute code; they produce JSON that is validated with Pydantic and applied through the same validated edit operations as the UI.

## The Docker socket trade-off
In `make up` mode the API container mounts `/var/run/docker.sock` so it can start simulation
containers. Anything with access to that socket controls Docker on the host. This is acceptable
for a local, single-user tool and **not** for a shared deployment. For hosted deployments use
`SANDBOX_PROVIDER=nebius` (no socket needed) or run the API natively (`make dev`).

## Reporting
Please report vulnerabilities privately to the maintainers rather than in a public issue.
