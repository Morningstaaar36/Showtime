# ADR 0001: Modular monolith with plugins

**Status:** accepted · 2026-10-08

## Context
Showtime must grow (new hazards, engines, exporters, importers) without editing core code.

## Decision
One process, one repo, with a small core that defines 12 extension points as Python `Protocol`s (`api/core/extensions`). Every feature, including the built-in ones, registers through a plugin: folder plugins (`plugins/<id>/plugin.toml`) and installed packages (entry-point group `showtime.plugins`). Lifecycle hooks use **pluggy**. Feature flags live in `config/features.yaml` with `FEATURE_<ID>` overrides. A failing plugin is isolated and reported in `/api/v1/health`. Import boundaries are enforced with **import-linter** (`.importlinter`).

## Consequences
Adding a hazard, exporter or event is a new folder (`make new-plugin`). Core stays small. Plugins are trusted local code (no sandboxing of plugin code itself).
