"""Freeze the demo store's API responses into static JSON for a backend-less demo (GitHub Pages).

    python -m app.demo.snapshot --out ../analytics-embed/public/demo-data

Runs the real FastAPI app in-process (no server) against the seeded demo database and saves one
file per request the UI can make. The file name is derived from path + params exactly like
`snapshotName()` in analytics-embed/src/staticDemo.ts - keep the two in sync.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PERIODS = (7, 30, 90, 365)
LONG_PERIODS = (30, 90, 180, 365)  # Products / Customers selectors
TRACKER_PERIODS = (1, 7, 30, 90)
PRODUCT_LIMITS = (20, 40, 60, 80, 100)
GROUPS = ("day", "week", "month")
STORE_ID = 1


def snapshot_name(path: str, params: dict[str, object]) -> str:
    """analytics/overview + {period:30, focus_date:'2026-09-01'} -> analytics_overview__focus_date-2026-09-01__period-30"""
    base = path.strip("/").replace("/", "_")
    parts = [f"__{k}-{v}" for k, v in sorted(params.items()) if v is not None and k != "store_id"]
    return base + "".join(parts)


def enumerate_requests(today: date) -> list[tuple[str, dict[str, object]]]:
    reqs: list[tuple[str, dict[str, object]]] = []
    for p in PERIODS:
        reqs.append(("/analytics/overview", {"period": p}))
        reqs.append(("/analytics/traffic", {"period": p}))
        reqs.append(("/analytics/cart", {"period": p}))
        for g in GROUPS:
            reqs.append(("/analytics/revenue", {"period": p, "group_by": g}))
        # clicking a day on a chart focuses every KPI/table on that day
        for offset in range(p):
            fd = (today - timedelta(days=offset)).isoformat()
            reqs.append(("/analytics/overview", {"period": p, "focus_date": fd}))
            reqs.append(("/analytics/revenue", {"period": p, "group_by": "day", "focus_date": fd}))
            reqs.append(("/analytics/traffic", {"period": p, "focus_date": fd}))
    for p in TRACKER_PERIODS:
        reqs.append(("/analytics/tracker", {"period": p}))
    for p in LONG_PERIODS:
        reqs.append(("/analytics/customers", {"period": p}))
        for limit in PRODUCT_LIMITS:
            reqs.append(("/analytics/top-products", {"period": p, "limit": limit}))
    reqs += [("/analytics/trends", {"period": 365}), ("/analytics/cohorts", {"months": 12}), ("/analytics/rfm", {})]
    return reqs


async def build(out: Path, database_url: str, concurrency: int = 4) -> dict:
    os.environ["DATABASE_URL"] = database_url  # must be set before app.database builds its engine
    from app.config import get_settings

    get_settings.cache_clear()
    import httpx
    from app.main import app
    from app.database import engine
    from app.routers.access import current_session

    # In-process calls carry no Shoper session cookie; act as the seeded demo store.
    app.dependency_overrides[current_session] = lambda: {"store_id": STORE_ID, "shop": None}

    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request is ~1,500 lines of noise
    today = date.today()
    reqs = enumerate_requests(today)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    sem = asyncio.Semaphore(concurrency)
    failures: list[str] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo", timeout=60) as client:
        async def one(path: str, params: dict[str, object]) -> None:
            name = snapshot_name(path, params)
            if name in seen:
                return
            seen.add(name)
            async with sem:
                r = await client.get(f"/api{path}", params={"store_id": STORE_ID, **params})
            if r.status_code != 200:
                failures.append(f"{name}: HTTP {r.status_code} {r.text[:120]}")
                return
            (out / f"{name}.json").write_text(r.text, encoding="utf-8")

        await asyncio.gather(*(one(p, q) for p, q in reqs))
    await engine.dispose()

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": today.isoformat(),
        "files": len(seen) - len(failures),
    }
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if failures:
        raise SystemExit("Snapshot failed for:\n  " + "\n  ".join(failures[:15]) + f"\n({len(failures)} total)")
    return manifest


def main() -> None:
    from app.config import get_settings
    from .seed import demo_url_from

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("../analytics-embed/public/demo-data"))
    p.add_argument("--database-url", help="seeded demo database (default: DATABASE_URL + _demo)")
    a = p.parse_args()
    manifest = asyncio.run(build(a.out, a.database_url or demo_url_from(get_settings().database_url)))
    size = sum(f.stat().st_size for f in a.out.iterdir()) / 1_048_576
    print(f"Wrote {manifest['files']} snapshots ({size:.1f} MB) to {a.out}  [as of {manifest['as_of']}]")


if __name__ == "__main__":
    main()
