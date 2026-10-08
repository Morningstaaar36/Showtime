# ADR 0005: Provider adapters (local first, Nebius by configuration)

**Status:** accepted · 2026-10-08

## Decision
Only `api/adapters/` knows about providers: `llm.py` (any OpenAI-compatible endpoint: local llama.cpp or Nebius Token Factory), `sandbox.py` (`DockerRunner`, `FakeRunner`, `NebiusRunner`), `search.py` (Tavily), `weather.py` (Open-Meteo). `api/app/state.py` picks implementations from `.env` (`LLM_PROVIDER`, `SANDBOX_PROVIDER`). Model ids per role (`fast`, `long`, `main`, `judge`) come from configuration.

## Consequences
Switching to Nebius is an `.env` change. Tests use fakes and recorded LLM responses.
