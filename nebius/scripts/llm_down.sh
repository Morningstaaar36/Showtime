#!/usr/bin/env bash
# Stop the local llama-server started by llm_up.sh.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/logs/llm.pid" ] && kill -0 "$(cat "$ROOT/logs/llm.pid")" 2>/dev/null; then
  kill "$(cat "$ROOT/logs/llm.pid")" && echo "llama-server stopped"
else
  echo "llama-server not running"
fi
rm -f "$ROOT/logs/llm.pid"
if [ -f "$ROOT/logs/llm_bridge.pid" ] && kill -0 "$(cat "$ROOT/logs/llm_bridge.pid")" 2>/dev/null; then
  kill "$(cat "$ROOT/logs/llm_bridge.pid")"
fi
rm -f "$ROOT/logs/llm_bridge.pid"
