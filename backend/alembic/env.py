from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import as_sync_url, get_settings
from app.database import Base
import app.models  # noqa: F401 - register all models on Base.metadata

config = context.config

# Skipped when Alembic runs inside the app or the test suite (app/migrations.py): fileConfig
# would otherwise replace their logging setup and silence every existing logger.
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

# Database URL, first match wins: passed in by code (app/migrations.py), `-x db_url=...` on the
# command line, then the app settings (.env). Kept out of config.set_main_option because that goes
# through configparser, which chokes on a "%" in the password.
x_args = context.get_x_argument(as_dictionary=True)
db_url = as_sync_url(config.attributes.get("db_url") or x_args.get("db_url") or get_settings().sync_db_url)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Tables that exist in the database but have no model (tracker_events_local, which the demo
    # seeder creates for the tracker) are not Alembic's to drop.
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A caller can hand over its own connection so several commands share one transaction
    # (scripts/adopt_legacy_db.py rolls the whole thing back on a dry run).
    shared = config.attributes.get("connection")
    if shared is not None:
        _run(shared)
        return
    with create_engine(db_url, poolclass=pool.NullPool).connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
