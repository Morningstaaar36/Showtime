#!/usr/bin/env bash
# One-time setup. Everything is installed inside this project folder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .tools/bin logs runs cache/tmp state data
if [ ! -x .tools/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh -o .tools/uv-install.sh
  env UV_INSTALL_DIR="$ROOT/.tools/bin" UV_NO_MODIFY_PATH=1 sh .tools/uv-install.sh
fi
. scripts/env.sh
uv python install 3.12
(cd api && uv sync)
(cd web && npm ci --no-audit --no-fund --maxsockets=4)
docker build --platform linux/amd64 -t showtime-sim:latest sim/ > logs/build_sim.log 2>&1 && echo "sim image built"
./scripts/get_llm.sh
./scripts/get_model.sh
./scripts/get_data.sh || echo "dataset download failed: the curated incident list is used instead"
(cd api && uv run python -c "from api.db.session import migrate; migrate()")
echo "Setup done. Next: make llm-up && make up   (or: make llm-up && make dev)"
