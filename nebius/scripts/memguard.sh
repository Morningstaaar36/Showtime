#!/usr/bin/env bash
# Memory watchdog: logs free RAM + top processes every 5 s to logs/mem.log.
# If available RAM drops below MEMGUARD_MIN_MB (default 1500), it stops the running
# simulation containers and the web dev server so the desktop (and VS Code) stays alive.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIN="${MEMGUARD_MIN_MB:-1500}"
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/mem.log"
echo "$(date +%T) memguard started (min ${MIN} MB)" >> "$LOG"
while true; do
  avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  top=$(ps -eo rss=,comm= --sort=-rss | head -4 | awk '{printf "%s:%dMB ", $2, $1/1024}')
  echo "$(date +%T) avail=${avail}MB $top" >> "$LOG"
  if [ "$avail" -lt "$MIN" ]; then
    echo "$(date +%T) LOW MEMORY: stopping sims and web dev server" >> "$LOG"
    for c in $(docker ps --filter label=com.showtime.project=true -q 2>/dev/null); do docker kill "$c" >/dev/null 2>&1; done
    pkill -f "vite --host" >/dev/null 2>&1
  fi
  # keep the log small
  if [ "$(wc -l < "$LOG")" -gt 5000 ]; then tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
  sleep 5
done
