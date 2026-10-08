"""Database engine, migrations at startup and session helper."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from api.core.settings import get_settings

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    """SQLite engine with WAL and foreign keys on."""
    settings = get_settings()
    url = url or settings.database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


def alembic_config(url: str) -> AlembicConfig:
    """Alembic config pointing at our migrations folder."""
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def migrate(url: str | None = None) -> None:
    """Upgrade the database to the latest schema."""
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(url), "head")


@contextmanager
def db_session(url: str | None = None) -> Iterator[Session]:
    """Short-lived session; commits are explicit."""
    with Session(get_engine(url), expire_on_commit=False) as s:
        yield s
