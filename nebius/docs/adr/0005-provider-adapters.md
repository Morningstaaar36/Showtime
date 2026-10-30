# ADR 0005: Provider adapters (local first, cloud by configuration)

**Status:** accepted · 2026-10-08

## Decision
Only `api/adapters/` knows about providers: `llm.py` (any OpenAI-compatible endpoint: local llama.cpp or a hosted API such as OpenRouter), `sandbox.py` (`DockerRunner`, `FakeRunner`), `search.py` (Tavily), `weather.py` (Open-Meteo). Each provider is one module in `api/adapters/providers/` that registers itself; `.env` picks one by name (`LLM_PROVIDER`, `SANDBOX_PROVIDER`, `SEARCH_PROVIDER`). Model ids per role (`fast`, `long`, `main`, `judge`) come from configuration, with presets in `api/data/llm_presets.json`.

## Consequences
Switching provider is an `.env` change. A new provider is one new module ([ADDING_A_PROVIDER.md](../ADDING_A_PROVIDER.md)). Tests use fakes and recorded LLM responses.
