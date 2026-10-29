#!/usr/bin/env bash
# Download open datasets into data/ (gitignored) and build normalised files.
# Feliciani crowd-accident list 1900–2024, CC BY 4.0, https://doi.org/10.5281/zenodo.19483010
# Jülich bottleneck experiment (Düsseldorf caserne, 2006), CC BY 4.0, https://doi.org/10.34735/ped.2006.2
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# works on a host (curl, unzip, uv) and inside the api image (Python only: make data)
PY="python3"; command -v uv >/dev/null && [ -f "$ROOT/api/pyproject.toml" ] && [ -z "${IN_IMAGE:-}" ] && PY="uv run python"
fetch() {  # fetch <url> <file>
  if command -v curl >/dev/null; then curl -sS --http1.1 -L --retry 3 -o "$2" "$1"
  else python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$1" "$2"; fi
}
DEST="$ROOT/data/incidents"
mkdir -p "$DEST"
BASE="https://zenodo.org/api/records/19483010/files"
for f in accident_data_numeric.csv accident_data_raw.csv number_conversion.csv references.zip; do
  if [ ! -s "$DEST/$f" ]; then
    echo "downloading $f"
    for i in 1 2 3 4 5; do
      fetch "$BASE/$f/content" "$DEST/$f.part" && mv "$DEST/$f.part" "$DEST/$f" && break
      echo "retry $i"; sleep 2
    done
  fi
done
# --- Simulator validation: Jülich "Bottleneck, Caserne" 2006 (scripts/validate_bottleneck.py) ---
VAL="$ROOT/data/validation/bottleneck2006"
VAL_BASE="http://ped.fz-juelich.de/experiments/2006.11.27_Duesseldorf_Casern/data/eg"
mkdir -p "$VAL"
# file name, remote name, sha256 (the files validation.json was computed from)
while read -r f remote sum; do
  if [ -s "$VAL/$f" ] && echo "$sum  $VAL/$f" | sha256sum -c --status; then
    continue
  fi
  echo "downloading $f"
  fetch "$VAL_BASE/$remote" "$VAL/$f.part"
  if ! echo "$sum  $VAL/$f.part" | sha256sum -c --status; then
    echo "checksum mismatch for $f: the archive changed; check it before rerunning make validate" >&2
    rm -f "$VAL/$f.part"
    exit 1
  fi
  mv "$VAL/$f.part" "$VAL/$f"
done <<'LIST'
metadata.json 2006bottleneck2_metadata.json 517a9813d4c420464c2608ed6bd1c2b7648e13f9a018671c784a5f8c8118634f
trajectories_txt.zip 2006bottleneck2_trajectories_txt.zip a66ed94acd83a96b69d16e1d27e9fadfd98a864787f7eaa5af6da44d9d4caef7
LIST
if [ ! -s "$VAL/txt/b250.txt" ]; then
  mkdir -p "$VAL/txt"
  python3 -m zipfile -e "$VAL/trajectories_txt.zip" "$VAL/txt"
fi

cd "$ROOT/api" && $PY ../scripts/build_incidents.py
