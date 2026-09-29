"""Alembic from code: bring a database to the latest schema, or check that it already is.

The schema is owned by the migrations in backend/alembic/versions. Deploys run
`alembic upgrade head` before the app starts; the app itself only checks and refuses to start on
an outdated schema, so a missed migration fails loudly instead of as a missing-column error later.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from .config import as_sync_url

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logging"] = False
    if database_url:
        cfg.attributes["db_url"] = as_sync_url(database_url)
    return cfg


def upgrade_to_head(database_url: str | None = None) -> None:
    """Blocking; call through asyncio.to_thread from async code."""
    command.upgrade(alembic_config(database_url), "head")


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(sync_conn: Connection) -> str | None:
    """For AsyncConnection.run_sync."""
    return MigrationContext.configure(sync_conn).get_current_revision()


class SchemaOutdatedError(RuntimeError):
    pass


def ensure_schema_current(current: str | None) -> None:
    head = head_revision()
    if current != head:
        raise SchemaOutdatedError(
            f"Database schema is at {current or 'no revision'}, code expects {head}. "
            "Run `alembic upgrade head` in backend/. A database created before Alembic needs "
            "`python scripts/adopt_legacy_db.py --apply` once instead."
        )
