#!/usr/bin/env bash
# Download open datasets into data/ (gitignored) and build normalised files.
# Feliciani crowd-accident list 1900–2024, CC BY 4.0, https://doi.org/10.5281/zenodo.19483010
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/incidents"
mkdir -p "$DEST"
BASE="https://zenodo.org/api/records/19483010/files"
for f in accident_data_numeric.csv accident_data_raw.csv number_conversion.csv references.zip; do
  if [ ! -s "$DEST/$f" ]; then
    echo "downloading $f"
    for i in 1 2 3 4 5; do
      curl -sS --http1.1 -L --retry 3 -o "$DEST/$f.part" "$BASE/$f/content" && mv "$DEST/$f.part" "$DEST/$f" && break
      echo "retry $i"; sleep 2
    done
  fi
done
cd "$ROOT/api" && uv run python ../scripts/build_incidents.py
