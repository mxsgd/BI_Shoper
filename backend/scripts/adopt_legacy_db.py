"""One-off: put a database that was built by the old create_all startup under Alembic.

Before Alembic the app ran Base.metadata.create_all on startup. That only ever creates missing
tables, so a long-lived database drifted from the models: columns the models later gained are
missing, columns they dropped are still there, and a few indexes differ.

This script, in a single transaction:
  1. stamps the database as 0001_baseline (its tables already exist),
  2. runs the migrations after the baseline (`alembic upgrade head`),
  3. fixes whatever still differs from the models,
and commits only with --apply. Without it, it prints the changes and rolls everything back.

Dropping a leftover column deletes its data. The columns it drops are raw Shoper JSON the code no
longer reads (it can be re-synced), but read the dry-run list first.

    python scripts/adopt_legacy_db.py                 # dry run against DATABASE_URL
    python scripts/adopt_legacy_db.py --apply
    python scripts/adopt_legacy_db.py --database-url postgresql://... --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.autogenerate import produce_migrations  # noqa: E402
from alembic.operations import Operations  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import app.models  # noqa: E402,F401 - register every table on Base.metadata
from app.config import get_settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.migrations import alembic_config, head_revision  # noqa: E402


def include_object(obj, name, type_, reflected, compare_to):
    # Leave tables without a model (tracker_events_local) alone, same rule as alembic/env.py.
    return not (type_ == "table" and reflected and compare_to is None)


def flatten(ops):
    for op in ops:
        if hasattr(op, "ops"):  # ModifyTableOps groups column changes per table
            yield from flatten(op.ops)
        else:
            yield op


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database-url", help="default: DATABASE_URL from settings")
    p.add_argument("--apply", action="store_true", help="make the changes (default: only list them)")
    a = p.parse_args()

    cfg = alembic_config(a.database_url or get_settings().database_url)
    engine = create_engine(cfg.attributes["db_url"])

    # Everything runs in one transaction: Postgres DDL is transactional, so a dry run can do the
    # real stamp + upgrade + fixes to list the exact changes, then roll all of it back.
    with engine.connect() as conn, conn.begin() as tx:
        cfg.attributes["connection"] = conn
        current = MigrationContext.configure(conn).get_current_revision()
        if current != head_revision():
            if current not in (None, "0001_baseline"):
                # e.g. the pre-baseline "0001_shoper_app_installations", which no longer exists.
                print(f"Database is stamped {current!r}; re-stamping as 0001_baseline.")
            command.stamp(cfg, "0001_baseline", purge=True)
            command.upgrade(cfg, "head")
            print(f"Upgraded to {head_revision()}.")

        ctx = MigrationContext.configure(conn, opts={"include_object": include_object})
        ops = list(flatten(produce_migrations(ctx, Base.metadata).upgrade_ops.ops))
        for op in ops:
            print(" ", op.to_diff_tuple() if hasattr(op, "to_diff_tuple") else op)
        runner = Operations(ctx)
        for op in ops:
            runner.invoke(op)
        print(f"{len(ops)} drift fix(es)." if ops else "No drift from the models.")

        if not a.apply:
            tx.rollback()
            print("\nDry run: nothing was changed. Re-run with --apply.")
            return
    print("\nApplied.")


if __name__ == "__main__":
    main()
