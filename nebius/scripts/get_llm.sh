#!/usr/bin/env bash
# Download the prebuilt llama.cpp CUDA server (release asset, resumable) into .tools/llama/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${LLAMA_TAG:-b11476}"
F="llama-${TAG}-bin-ubuntu-cuda-13.4-x64.tar.gz"
mkdir -p "$ROOT/.tools/dl" "$ROOT/.tools/llama"
if ls "$ROOT"/.tools/llama/llama-*/llama-server >/dev/null 2>&1; then echo "llama-server already installed"; exit 0; fi
for i in $(seq 1 30); do
  curl -sS --http1.1 -L -C - -o "$ROOT/.tools/dl/$F" "https://github.com/ggml-org/llama.cpp/releases/download/$TAG/$F" \
    && gzip -t "$ROOT/.tools/dl/$F" 2>/dev/null && break
  echo "retry $i"; sleep 2
done
tar -xzf "$ROOT/.tools/dl/$F" -C "$ROOT/.tools/llama"
echo "installed: $(ls -d "$ROOT"/.tools/llama/llama-*/llama-server)"
