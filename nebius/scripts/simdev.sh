#!/usr/bin/env bash
# Dev helper: run the sim on a work folder with the local sim/ code mounted (no rebuild).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(cd "$1" && pwd)"
exec docker run --rm --network=none --memory="${SIM_MEM_LIMIT:-2g}" --cpus="${SIM_CPUS:-4}" \
  --user "$(id -u):$(id -g)" --label com.showtime.project=true \
  -e MPLCONFIGDIR=/tmp -v "$ROOT/sim:/app:ro" -v "$WORK:/work" showtime-sim:latest \
  python /app/run_sim.py /work
