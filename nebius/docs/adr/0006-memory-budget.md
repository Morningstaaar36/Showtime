# ADR 0006: Memory budget on a 14 GiB laptop

**Status:** accepted · 2026-10-08

## Context
The development machine crashed twice (OOM) while the LLM, Docker Desktop VM (3.5 GB), API, dev server and simulations ran together.

## Decision
- llama-server runs with `--load-mode dio --cache-ram 512` (RSS 4.4 GB → 0.9 GB; default prompt cache is 8 GB).
- One simulation at a time across processes (file lock `runs/.sim.lock`), sim containers capped at 2 GB.
- `scripts/memguard.sh` logs memory and stops simulations and the dev server below 1.5 GB free.
- The web container serves a static build (77 MB image) instead of a dev server.
