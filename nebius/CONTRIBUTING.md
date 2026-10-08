# Contributing

1. `make setup`, then `make llm-up` and `make dev` (or `make up`).
2. Work in small, typed modules. Python: type hints everywhere, `ruff` clean, `mypy --strict` for
   `api/core`, `api/adapters`, `api/orchestrator`. TypeScript: `strict`, no `any`.
3. Run `make check` after each change and `make test` before a commit; `make smoke` for flows.
4. New features are **plugins** (`make new-plugin TYPE=<ExtensionPoint> ID=<id>`, see
   `docs/EXTENDING.md`). Core never imports plugins (enforced by import-linter).
5. Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:` ...).
6. Never commit secrets, datasets or model weights. Record each new third-party licence in
   `docs/LICENSES.md`, each new default value in `docs/ASSUMPTIONS.md`.
7. UI copy: sentence case, plain verbs, no apologies in errors, strings in `web/src/i18n/en.json`.
