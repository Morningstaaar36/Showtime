#!/usr/bin/env bash
# Start the API (native, port 8000) and the web dev server (port 5173) in the background.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
. scripts/env.sh
mkdir -p logs
pgrep -f memguard.sh >/dev/null || (setsid nohup "$ROOT/scripts/memguard.sh" > /dev/null 2>&1 < /dev/null &)
if ! curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
  (cd api && setsid nohup uv run uvicorn api.app.main:app --host 127.0.0.1 --port 8000 > "$ROOT/logs/api.stdout.log" 2>&1 < /dev/null & echo $! > "$ROOT/logs/api.pid")
fi
if ! curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then
  (cd web && NODE_OPTIONS=--max-old-space-size=1536 setsid nohup npx vite --host 127.0.0.1 --port 5173 > "$ROOT/logs/web.log" 2>&1 < /dev/null & echo $! > "$ROOT/logs/web.pid")
fi
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && curl -sf http://127.0.0.1:5173/ >/dev/null 2>&1; then
    echo "Showtime is running: http://localhost:5173  (API docs: http://127.0.0.1:8000/api/docs)"; exit 0
  fi
  sleep 1
done
echo "Did not start in 60 s; see logs/api.stdout.log and logs/web.log" >&2; exit 1
