#!/usr/bin/env bash
# Stop the API and web dev server started by dev_up.sh (matches their command lines).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pkill -f "uvicorn api.app.main:app" && echo "api stopped"
pkill -f "vite --host 127.0.0.1 --port 5173" && echo "web stopped"
rm -f "$ROOT/logs/api.pid" "$ROOT/logs/web.pid"
exit 0
