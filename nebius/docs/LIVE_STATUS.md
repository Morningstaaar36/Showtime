# Live status of the external services

Written by `scripts/verify_live.py nebius-llm` on 2026-10-25T10:57:35+00:00. Each row is the
provider's smallest real call (one chat, one sandbox script plus one refused network call,
one search). SKIPPED means its key is not in .env, so it has **not been run live**.

| Service | Provider | Result | Detail | Ids |
| --- | --- | --- | --- | --- |
| llm | Nebius Token Factory | SKIPPED | SKIPPED: set NEBIUS_API_KEY Fix: docs/WHEN_YOU_GET_THE_KEYS.md |  |
