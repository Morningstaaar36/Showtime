# ADR 0004: SQLite with Alembic migrations

**Status:** accepted · 2026-10-08

## Decision
SQLite (WAL) via SQLModel; schema changes only through Alembic (`api/db/migrations`), applied at startup. Venue versions are full JSON snapshots plus the patch that produced them and a `base_version` link (undo/redo/restore never lose history). Simulation artifacts live on disk under `runs/<run_id>/`, referenced by id. Run ids are content hashes, so the same request returns the same run.
