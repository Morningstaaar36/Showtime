#!/usr/bin/env bash
# Download Nemotron Nano 9B v2 (Q4_K_M GGUF, ~6.5 GB) into ./models and verify its checksum.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/env.sh"
REPO="dominguesm/NVIDIA-Nemotron-Nano-9B-v2-GGUF"
FILE="nemotron-nano-9b-v2-q4_k_m.gguf"
mkdir -p "$ROOT/models"
if [ -f "$ROOT/models/$FILE" ]; then echo "model already present"; exit 0; fi
command -v hf >/dev/null || uv tool install "huggingface_hub[cli]"
hf download "$REPO" "$FILE" --local-dir "$ROOT/models"
rm -rf "$ROOT/models/.cache"
EXP=$(curl -s "https://huggingface.co/api/models/$REPO/tree/main" | python3 -c "import json,sys;[print(f['lfs']['oid']) for f in json.load(sys.stdin) if f['path']=='$FILE']")
GOT=$(sha256sum "$ROOT/models/$FILE" | cut -d' ' -f1)
[ "$EXP" = "$GOT" ] && echo "checksum ok" || { echo "checksum mismatch" >&2; exit 1; }
