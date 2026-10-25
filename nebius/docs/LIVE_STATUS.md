# Live status of the external services

Written by `scripts/verify_live.py` (`make verify-live`, `make verify-<service>`): the latest
result of each provider's smallest real call (one chat; one sandbox script plus one network
call that must be stopped; one search). SKIPPED means its key is not in .env, so it has
**not been run live**.

| Service | Provider | Result | Detail | Ids | Checked |
| --- | --- | --- | --- | --- | --- |
| llm | Nebius Token Factory | SKIPPED | SKIPPED: set NEBIUS_API_KEY Fix: docs/WHEN_YOU_GET_THE_KEYS.md |  | 2026-10-25T10:58:12+00:00 |
| llm | OpenAI-compatible API | PASS | OPENROUTER: nvidia/nemotron-3-ultra-550b-a55b:free; nvidia/nemotron-3.5-lightning:free answered 'ready' | OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1; models: nvidia/nemotron-3-ultra-550b-a55b:free, nvidia/nemotron-3.5-lightning:free | 2026-10-25T10:58:12+00:00 |
| sandbox | Local Docker | PASS | ran a script in 0.31 s; a network call was stopped: OSError: [Errno 101] Network is unreachable | SIM_IMAGE=showtime-sim:latest | 2026-10-25T10:58:12+00:00 |
| sandbox | Nebius Sandboxes | SKIPPED | SKIPPED: set NEBIUS_API_KEY Fix: docs/WHEN_YOU_GET_THE_KEYS.md |  | 2026-10-25T10:58:12+00:00 |
| search | Tavily web search | SKIPPED | SKIPPED: set TAVILY_API_KEY Fix: docs/WHEN_YOU_GET_THE_KEYS.md |  | 2026-10-25T10:58:12+00:00 |
