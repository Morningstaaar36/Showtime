#!/usr/bin/env bash
# Start the local Nemotron llama-server in the background (logs/llm.log).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ -f .env ] && set -a && . ./.env && set +a
BIN="${LLAMA_SERVER_BIN:-$(ls -d "$ROOT"/.tools/llama/llama-*/llama-server 2>/dev/null | head -n1)}"
MODELS_DIR="${MODELS_DIR:-$ROOT/models}"
MODEL_FILE="${LOCAL_LLM_FILE:-nemotron-nano-9b-v2-q4_k_m.gguf}"
CTX="${LLM_CONTEXT:-16384}"
PORT="${LLM_PORT:-8080}"
if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
  echo "llama-server not found. Run: make get-llm" >&2; exit 1
fi
if [ ! -f "$MODELS_DIR/$MODEL_FILE" ]; then
  echo "Model not found at $MODELS_DIR/$MODEL_FILE. Run: make get-model" >&2; exit 1
fi
# The containers of `make up` reach the host on the Docker bridge (host.docker.internal);
# forward that address only (not the LAN) to the server on 127.0.0.1.
bridge() {
  local ip
  ip="$(ip -4 -o addr show docker0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
  [ -n "$ip" ] || return 0
  [ -f logs/llm_bridge.pid ] && kill -0 "$(cat logs/llm_bridge.pid)" 2>/dev/null && return 0
  nohup python3 -I scripts/llm_bridge.py "$ip" "$PORT" > logs/llm_bridge.log 2>&1 &
  echo $! > logs/llm_bridge.pid
  echo "Containers reach it at http://host.docker.internal:$PORT (bridge $ip)"
}
if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "llama-server already running on :$PORT"; bridge; exit 0
fi
mkdir -p logs
export LD_LIBRARY_PATH="$(dirname "$BIN"):/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
nohup "$BIN" -m "$MODELS_DIR/$MODEL_FILE" --alias "${LOCAL_LLM_MODEL:-nemotron-nano-9b-v2-q4_k_m}" \
  -ngl 99 -c "$CTX" --parallel 1 --load-mode "${LLM_LOAD_MODE:-dio}" --cache-ram "${LLM_CACHE_RAM_MB:-512}" --host 127.0.0.1 --port "$PORT" --jinja \
  --log-file logs/llm.log > logs/llm.stdout.log 2>&1 &
echo $! > logs/llm.pid
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "llama-server ready on http://127.0.0.1:$PORT (pid $(cat logs/llm.pid))"; bridge; exit 0
  fi
  if ! kill -0 "$(cat logs/llm.pid)" 2>/dev/null; then
    echo "llama-server exited; see logs/llm.stdout.log" >&2; tail -n 20 logs/llm.stdout.log >&2; exit 1
  fi
  sleep 1
done
echo "llama-server did not become healthy in 90 s; see logs/llm.stdout.log" >&2; exit 1
