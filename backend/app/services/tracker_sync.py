"""
Jednokierunkowy sync: tabela `events` na zdalnym Postgresie (Railway tracker)
→ lokalna tabela `tracker_events_local`.

Uruchamiane przy starcie backendu tylko gdy ustawiono TRACKER_REMOTE_DATABASE_URL
i TRACKER_SYNC_ON_STARTUP=1 (domyślnie włączone jeśli URL jest).

W .env (lokalnie):
  TRACKER_REMOTE_DATABASE_URL=postgresql://...   # ten sam co Railway Postgres (skopiuj z Variables)
  TRACKER_REMOTE_SSL_INSECURE=1                  # opcjonalnie: dev — bez TLS (patrz config.py)
  TRACKER_SYNC_ON_STARTUP=1                      # opcjonalnie; jeśli brak URL — sync się pomija
  TRACKER_SYNC_BATCH=5000                        # max wierszy na jeden start
"""
from __future__ import annotations

import json
import logging
import os
import ssl
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..config import get_settings
from ..database import async_session

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 5000


def _sanitize_url(url: str) -> str:
    u = url.strip().strip('"').strip("'")
    return u


def _to_asyncpg_url(url: str) -> str:
    u = _sanitize_url(url)
    if u.startswith("postgresql://"):
        u = u.replace("postgresql://", "postgresql+asyncpg://", 1)
    return u


def _host_hint(url: str) -> str:
    try:
        p = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
        return p.hostname or "(brak hosta)"
    except Exception:
        return "(nieparsowalny URL)"


def _strip_ssl_query_params(url: str) -> str:
    """Usuwa sslmode/ssl* z query — inaczej asyncpg i tak włączy TLS mimo connect_args."""
    p = urlparse(url)
    if not p.query:
        return url
    drop = frozenset(
        {
            "sslmode",
            "ssl",
            "sslcert",
            "sslkey",
            "sslrootcert",
            "sslnegotiation",
            "sslcrl",
            "sslpassword",
            "ssl_min_protocol_version",
            "ssl_max_protocol_version",
        }
    )
    pairs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in drop]
    return urlunparse(p._replace(query=urlencode(pairs)))


def _remote_connect_args(url: str, *, ssl_insecure: bool) -> dict:
    """
    Publiczny proxy Railway (rlwy.net) zwykle wymaga SSL; wewn. host bez SSL.

    Domyślnie włączamy weryfikację certyfikatu. Przy TRACKER_REMOTE_SSL_INSECURE=1 (pola
    Settings) używamy TLS bez weryfikacji łańcucha — typowe dla dev na Windows + Railway proxy.
    """
    u = url.lower()

    # Brak SSL dla wewnętrznych hostów
    if "railway.internal" in u:
        return {}

    if "rlwy.net" in u or "sslmode=require" in u:
        if ssl_insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            logger.warning(
                "tracker sync: TLS bez weryfikacji certyfikatu (TRACKER_REMOTE_SSL_INSECURE=1) "
                "dla hosta %s – tylko do lokalnego dev.",
                _host_hint(u),
            )
            return {"ssl": ctx}
        # domyślny, z weryfikacją certyfikatu
        return {"ssl": True}

    return {}


async def sync_tracker_events_from_remote() -> dict:
    """
    Pobiera nowe wiersze z remote `events` (timestamp > max lokalny) i wstawia do tracker_events_local.
    """
    settings = get_settings()
    ssl_insecure = bool(settings.tracker_remote_ssl_insecure)
    raw = settings.tracker_remote_database_url or ""
    remote_url = _sanitize_url(raw)
    if not remote_url:
        return {"skipped": True, "reason": "TRACKER_REMOTE_DATABASE_URL not set"}

    if os.getenv("TRACKER_SYNC_ON_STARTUP", "1").strip().lower() in ("0", "false", "no"):
        return {"skipped": True, "reason": "TRACKER_SYNC_ON_STARTUP disabled"}

    # Zdalny host *.railway.internal działa tylko w sieci Railway — z lokalnego PC DNS się nie rozwiązuje.
    if "railway.internal" in remote_url.lower():
        logger.warning(
            "tracker sync pominięty: host *.railway.internal nie działa z localhost. "
            "W Postgres → Variables skopiuj pełny DATABASE_URL z publicznym hostem "
            "(np. *.proxy.rlwy.net:PORT z Networking → Public TCP), nie wewnętrzny host."
        )
        return {"skipped": True, "reason": "railway.internal not reachable from localhost"}

    batch = int(os.getenv("TRACKER_SYNC_BATCH", str(_DEFAULT_BATCH)))
    remote_url = _to_asyncpg_url(remote_url)
    if ssl_insecure:
        remote_url = _strip_ssl_query_params(remote_url)

    remote_engine = create_async_engine(
        remote_url,
        echo=False,
        pool_pre_ping=True,
        connect_args=_remote_connect_args(remote_url, ssl_insecure=ssl_insecure),
    )

    try:
        async with async_session() as local_db:
            max_row = await local_db.execute(text(
                "SELECT COALESCE(MAX(timestamp), 0) AS m FROM tracker_events_local"
            ))
            max_ts = int(max_row.scalar() or 0)

        async with remote_engine.connect() as rconn:
            result = await rconn.execute(text("""
                SELECT id, api_key, event_name, user_id, url, timestamp, metadata
                FROM events
                WHERE timestamp > :min_ts
                ORDER BY timestamp ASC
                LIMIT :lim
            """), {"min_ts": max_ts, "lim": batch})
            rows = result.mappings().all()

        if not rows:
            logger.info("tracker sync: brak nowych wierszy (max_ts=%s)", max_ts)
            return {"skipped": False, "inserted": 0, "max_ts_before": max_ts}

        async with async_session() as local_db:
            inserted = 0
            for r in rows:
                res = await local_db.execute(text("""
                    INSERT INTO tracker_events_local
                        (id, api_key, event_name, user_id, url, timestamp, metadata)
                    VALUES
                        (CAST(:id AS uuid), :api_key, :event_name, :user_id, :url, :ts, CAST(:meta AS jsonb))
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": str(r["id"]),
                    "api_key": r["api_key"],
                    "event_name": r["event_name"],
                    "user_id": r["user_id"],
                    "url": r["url"],
                    "ts": int(r["timestamp"]),
                    "meta": json.dumps(r["metadata"] if r["metadata"] is not None else {}),
                })
                inserted += res.rowcount or 0
            await local_db.commit()

        logger.info("tracker sync: wstawiono %s wierszy (poprzedni max_ts=%s)", inserted, max_ts)
        return {"skipped": False, "inserted": inserted, "max_ts_before": max_ts, "batch_limit": batch}

    except OSError as e:
        if getattr(e, "errno", None) == 11001 or "getaddrinfo" in str(e).lower():
            logger.error(
                "tracker sync: nie można rozwiązać hosta (%s). Sprawdź TRACKER_REMOTE_DATABASE_URL — "
                "użyj publicznego adresu Postgresa z Railway (proxy.rlwy.net), nie railway.internal.",
                _host_hint(remote_url),
            )
        else:
            logger.exception("tracker sync failed (sieć)")
        return {"skipped": False, "error": True}
    except Exception:
        logger.exception(
            "tracker sync failed — host=%s; sprawdź URL, hasło i czy Postgres akceptuje połączenia z internetu.",
            _host_hint(remote_url),
        )
        return {"skipped": False, "error": True}
    finally:
        await remote_engine.dispose()
