#!/usr/bin/env bash
# Restart only the API (native uvicorn on :8000) and wait until it is healthy.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
. scripts/env.sh
pkill -f "uvicorn api.app.main:app" 2>/dev/null
sleep 1
mkdir -p logs
(cd api && setsid nohup uv run uvicorn api.app.main:app --host 127.0.0.1 --port 8000 \
  > "$ROOT/logs/api.stdout.log" 2>&1 < /dev/null &)
for _ in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then echo "API ready"; exit 0; fi
  sleep 1
done
echo "API did not start; see logs/api.stdout.log" >&2
exit 1
