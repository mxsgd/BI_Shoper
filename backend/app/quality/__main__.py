"""python -m app.quality [--database-url URL] [--as-of YYYY-MM-DD]   (exit code 1 if any check fails)"""
import argparse
import asyncio
import sys
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .checks import run_checks

LABEL = {"pass": "PASS", "fail": "FAIL", "skip": "skip", "error": "ERR "}


async def _run(url: str, as_of: date) -> int:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as session:
            results = await run_checks(session, as_of)
    finally:
        await engine.dispose()
    category = ""
    for r in results:
        if r.check.category != category:
            category = r.check.category
            print(f"\n[{category}]")
        print(f"  {LABEL[r.status]}  {r.check.name:<42} {r.detail or r.check.description}")
    counts = {s: sum(r.status == s for r in results) for s in LABEL}
    print(f"\n{counts['pass']} passed, {counts['fail']} failed, {counts['error']} errored, {counts['skip']} skipped")
    return 1 if counts["fail"] or counts["error"] else 0


def main() -> None:
    from app.config import get_settings

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database-url", help="default: DATABASE_URL")
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    a = p.parse_args()
    sys.exit(asyncio.run(_run(a.database_url or get_settings().database_url, a.as_of)))


main()
