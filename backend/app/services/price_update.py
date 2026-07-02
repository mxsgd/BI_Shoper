from __future__ import annotations

import asyncio
import csv
import io
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models.raw.raw_product_stocks import RawProductStock
from ..models.store import Store
from .shoper_auth import ShoperAuthError, ensure_store_token
from .shoper_client import ShoperClient, ShoperUnauthorizedError

JobStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED", "CANCELLED"]
LogStatus = Literal["SUCCESS", "ERROR", "SKIPPED", "WARNING"]
TargetMode = Literal["product", "variant"]
CsvDelimiter = Literal["comma", "semicolon", "tab", "pipe"]

_DELIMITER_CHARS: dict[CsvDelimiter, str] = {
    "comma": ",",
    "semicolon": ";",
    "tab": "\t",
    "pipe": "|",
}

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 500_000
MAX_LOGS_IN_MEMORY = 5_000
MAX_JOBS_IN_MEMORY = 3
BULK_JOB_ROW_THRESHOLD = 500  # powyżej: bez logu per wiersz SKIPPED (cena bez zmian)
DEFAULT_LOCALE = os.getenv("SHOPER_DEFAULT_LOCALE", "pl_PL")
PRICE_UPDATE_CONCURRENCY = int(os.getenv("PRICE_UPDATE_CONCURRENCY", "8"))


@dataclass
class PriceUpdateLogEntry:
    timestamp: str
    job_id: str
    row_number: int
    code: str
    old_price: float | None
    new_price: float | None
    status: LogStatus
    message: str
    http_status: int | None = None
    request_id: str | None = None
    comment: str | None = None
    product_id: int | None = None
    stock_id: int | None = None


@dataclass
class PriceUpdateRow:
    row_number: int
    code: str
    price: float
    currency: str | None = None
    price_type: str | None = None
    comment: str | None = None


@dataclass
class ValidationError:
    row_number: int
    code: str
    error_message: str


@dataclass
class PriceUpdateJob:
    job_id: str
    store_id: int
    file_name: str
    created_at: str
    target_mode: TargetMode = "product"
    csv_delimiter: CsvDelimiter = "semicolon"
    status: JobStatus = "PENDING"
    started_at: str | None = None
    finished_at: str | None = None
    total: int = 0
    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    warning: int = 0
    deactivated_variants: int = 0
    rows: list[PriceUpdateRow] = field(default_factory=list)
    logs: list[PriceUpdateLogEntry] = field(default_factory=list)
    validation_errors: list[ValidationError] = field(default_factory=list)
    fatal_error: str | None = None
    disable_extra_variants: bool = True
    codes_in_file: set[str] = field(default_factory=set)
    product_ids_in_file: set[int] = field(default_factory=set)
    log_seq: int = 0
    logs_dropped: int = 0
    started_at_ts: float | None = None  # unix timestamp do ETA
    current_row_number: int | None = None
    current_code: str | None = None
    current_phase: str | None = None  # row | post_process
    duplicate_mode: str = "error"
    _last_persist_ts: float | None = field(default=None, repr=False, compare=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_price(raw: str) -> float:
    normalized = (raw or "").strip().replace(",", ".")
    if not normalized:
        raise ValueError("Price is empty")
    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("Price is not a number") from exc
    if value <= 0:
        raise ValueError("Price must be positive")
    return float(value)


def _parse_csv_rows(
    csv_text: str,
    *,
    duplicate_mode: Literal["error", "last_wins"],
    csv_delimiter: CsvDelimiter = "semicolon",
) -> tuple[list[PriceUpdateRow], list[ValidationError]]:
    reader = csv.DictReader(
        io.StringIO(csv_text),
        delimiter=_DELIMITER_CHARS[csv_delimiter],
    )
    headers = [h.strip() for h in (reader.fieldnames or []) if h]
    required = {"code", "price"}
    if not required.issubset(set(headers)):
        missing = ", ".join(sorted(required - set(headers)))
        return [], [ValidationError(row_number=1, code="", error_message=f"Missing required columns: {missing}")]

    rows: list[PriceUpdateRow] = []
    errors: list[ValidationError] = []
    first_seen: dict[str, int] = {}
    by_code: dict[str, PriceUpdateRow] = {}

    for idx, rec in enumerate(reader, start=2):
        code = (rec.get("code") or "").strip()
        raw_price = (rec.get("price") or "").strip()
        currency = (rec.get("currency") or "").strip() or None
        price_type = (rec.get("price_type") or "").strip() or None
        comment = (rec.get("comment") or "").strip() or None

        if not code:
            # Puste wiersze (np. końcowe wiersze arkusza Excel) — pomijaj cicho
            continue
        try:
            price = _parse_price(raw_price)
        except ValueError as exc:
            errors.append(ValidationError(row_number=idx, code=code, error_message=str(exc)))
            continue

        row = PriceUpdateRow(
            row_number=idx,
            code=code,
            price=price,
            currency=currency,
            price_type=price_type,
            comment=comment,
        )

        if code in first_seen and duplicate_mode == "error":
            errors.append(
                ValidationError(
                    row_number=idx,
                    code=code,
                    error_message=f"Duplicate code (first seen in row {first_seen[code]})",
                )
            )
            continue
        if code not in first_seen:
            first_seen[code] = idx

        if duplicate_mode == "last_wins":
            by_code[code] = row
        else:
            rows.append(row)

    if duplicate_mode == "last_wins":
        rows = sorted(by_code.values(), key=lambda r: r.row_number)
    return rows, errors


def _product_active_payload(active: bool, *, include_top_level: bool = False) -> dict:
    """Top-level ``active`` on product może w Shoper aktywować wszystkie warianty — domyślnie tylko translations."""
    payload: dict = {"translations": {DEFAULT_LOCALE: {"active": active}}}
    if include_top_level:
        payload["active"] = active
    return payload


def _stock_active_payload(active: bool, *, default: bool | None = None) -> dict:
    payload: dict = {"active": active}
    if default is not None:
        payload["default"] = default
    return payload


def _shoper_bool(value) -> bool:
    if value is True or value == 1 or value == "1":
        return True
    if value is False or value == 0 or value == "0":
        return False
    return bool(value)


def _shoper_price(data: dict) -> float:
    try:
        return float(data.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def _shoper_stock_id(data: dict) -> int:
    return int(data.get("stock_id") or data.get("id") or 0)


def _shoper_product_id(data: dict) -> int:
    return int(data.get("product_id") or data.get("id") or 0)


def _is_base_stock(live: dict) -> bool:
    """Stock bazowy (nie extended) — Shoper nie pozwala wyłączyć go przez PUT /product-stocks.
    
    Shoper zwraca extended jako int (1/0) lub bool — używamy _shoper_bool, nie 'is True'.
    """
    return not _shoper_bool(live.get("extended"))


def _response_request_id(response: object) -> str:
    """Bezpieczne wyciąganie request_id z odpowiedzi Shoper PUT — może być int, dict lub None."""
    if not isinstance(response, dict):
        return ""
    return str(response.get("request_id") or response.get("trace_id") or "")


def _is_base_stock_api_error(api_err: str | None) -> bool:
    if not api_err:
        return False
    low = api_err.lower()
    return "stocka bazowego" in low or "stock bazowy" in low


class PriceUpdateJobManager:
    def __init__(self):
        self._jobs: dict[str, PriceUpdateJob] = {}
        self._lock = asyncio.Lock()
        self._persist_lock = asyncio.Lock()

    async def _persist_job(self, job: PriceUpdateJob, *, force: bool = False) -> None:
        from . import price_update_persistence as persist

        now = datetime.now(timezone.utc).timestamp()
        if not force and job._last_persist_ts and now - job._last_persist_ts < 2.0:
            return
        async with self._persist_lock:
            await persist.save_job(job, duplicate_mode=job.duplicate_mode)
        job._last_persist_ts = now

    async def _persist_log(self, job: PriceUpdateJob, entry: PriceUpdateLogEntry) -> None:
        from . import price_update_persistence as persist

        try:
            await persist.save_log(entry, seq=job.log_seq)
        except Exception:
            pass  # nie przerywaj joba przy błędzie zapisu logu

    async def create_job(
        self,
        *,
        store_id: int,
        file_name: str,
        csv_bytes: bytes,
        duplicate_mode: Literal["error", "last_wins"] = "error",
        target_mode: TargetMode = "product",
        csv_delimiter: CsvDelimiter = "semicolon",
        disable_extra_variants: bool = True,
    ) -> PriceUpdateJob:
        if len(csv_bytes) > MAX_FILE_BYTES:
            raise ValueError(f"File too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB)")
        text = csv_bytes.decode("utf-8-sig", errors="replace")
        rows, validation_errors = _parse_csv_rows(
            text,
            duplicate_mode=duplicate_mode,
            csv_delimiter=csv_delimiter,
        )
        if len(rows) > MAX_ROWS:
            raise ValueError(f"Too many rows (max {MAX_ROWS})")
        job = PriceUpdateJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            store_id=store_id,
            file_name=file_name or "upload.csv",
            created_at=_now_iso(),
            target_mode=target_mode,
            csv_delimiter=csv_delimiter,
            disable_extra_variants=disable_extra_variants,
            duplicate_mode=duplicate_mode,
            rows=rows,
            total=len(rows),
            validation_errors=validation_errors,
            codes_in_file={r.code for r in rows},
        )
        async with self._lock:
            self._jobs[job.job_id] = job
            self._prune_old_jobs()

        if validation_errors:
            job.status = "FAILED"
            job.fatal_error = "Validation failed"
            job.finished_at = _now_iso()
            await self._persist_job(job, force=True)
            return job

        await self._persist_job(job, force=True)
        asyncio.create_task(self._run_job(job.job_id))
        return job

    async def get_job(self, job_id: str) -> PriceUpdateJob | None:
        async with self._lock:
            mem = self._jobs.get(job_id)
            if mem is not None:
                return mem
        from . import price_update_persistence as persist

        return await persist.load_job(job_id)

    async def get_active_job(self, store_id: int) -> PriceUpdateJob | None:
        async with self._lock:
            active = [
                j
                for j in self._jobs.values()
                if j.store_id == store_id and j.status in ("PENDING", "RUNNING")
            ]
            if active:
                active.sort(key=lambda j: j.started_at or j.created_at, reverse=True)
                return active[0]
        from . import price_update_persistence as persist

        return await persist.load_active_job(store_id)

    async def get_latest_job(self, store_id: int) -> PriceUpdateJob | None:
        async with self._lock:
            all_jobs = [j for j in self._jobs.values() if j.store_id == store_id]
            if all_jobs:
                all_jobs.sort(key=lambda j: j.created_at, reverse=True)
                return all_jobs[0]
        from . import price_update_persistence as persist

        return await persist.load_latest_job(store_id)

    async def get_logs(
        self,
        job_id: str,
        *,
        status: Literal["ALL", "SUCCESS", "ERROR", "WARNING", "SKIPPED"] = "ALL",
        query: str | None = None,
        page: int = 1,
        per_page: int = 100,
        tail: int | None = None,
    ) -> tuple[list[PriceUpdateLogEntry], int, int, int]:
        """Zwraca (items, total, pages_or_1, logs_dropped)."""
        job = await self.get_job(job_id)
        if job is None:
            return [], 0, 1, 0

        use_memory = False
        mem_job: PriceUpdateJob | None = None
        mem: PriceUpdateJob | None = None
        async with self._lock:
            mem = self._jobs.get(job_id)
            if mem is not None and mem.status in ("PENDING", "RUNNING"):
                use_memory = True
                mem_job = mem
        if use_memory and mem_job is not None:
            logs = mem_job.logs[-tail:] if tail is not None else list(mem_job.logs)
            if status != "ALL":
                logs = [l for l in logs if l.status == status]
            if query:
                q = query.strip().lower()
                logs = [l for l in logs if q in l.code.lower()]
            total = mem_job.log_seq if tail is not None else len(logs)
            if tail is None:
                start = (page - 1) * per_page
                items = logs[start : start + per_page]
                pages = (len(logs) + per_page - 1) // per_page if logs else 1
            else:
                items = logs
                pages = 1
            return items, total, pages, mem_job.logs_dropped

        from . import price_update_persistence as persist

        items, total, dropped = await persist.load_logs(
            job_id,
            status=status,
            query=query,
            page=page,
            per_page=per_page,
            tail=tail,
        )
        if not items and mem is not None and mem.logs:
            logs = mem.logs[-tail:] if tail is not None else list(mem.logs)
            if status != "ALL":
                logs = [l for l in logs if l.status == status]
            if query:
                q = query.strip().lower()
                logs = [l for l in logs if q in l.code.lower()]
            total = mem.log_seq if tail is not None else len(logs)
            if tail is None:
                start = (page - 1) * per_page
                items = logs[start : start + per_page]
                pages = (len(logs) + per_page - 1) // per_page if logs else 1
            else:
                items = logs
                pages = 1
            dropped = mem.logs_dropped
            return items, total, pages, dropped
        if tail is not None:
            pages = 1
        else:
            pages = (total + per_page - 1) // per_page if total else 1
        return items, total, pages, dropped

    def _set_progress(
        self,
        job: PriceUpdateJob,
        *,
        phase: str,
        code: str | None = None,
        row_number: int | None = None,
    ) -> None:
        job.current_phase = phase
        job.current_code = code
        job.current_row_number = row_number
        asyncio.create_task(self._persist_job(job))

    def _clear_progress(self, job: PriceUpdateJob) -> None:
        job.current_phase = None
        job.current_code = None
        job.current_row_number = None

    def _prune_old_jobs(self) -> None:
        """Usuń tylko zakończone joby — RUNNING/PENDING nigdy nie kasujemy."""
        terminal = ("DONE", "FAILED", "CANCELLED")
        finished = [
            (jid, j)
            for jid, j in self._jobs.items()
            if j.status in terminal
        ]
        # Zachowaj wszystkie aktywne + max N ostatnich zakończonych
        active_count = sum(1 for j in self._jobs.values() if j.status not in terminal)
        max_finished = max(0, MAX_JOBS_IN_MEMORY - active_count)
        if len(finished) <= max_finished:
            return
        finished.sort(key=lambda x: x[1].finished_at or x[1].created_at)
        while len(finished) > max_finished:
            jid, _ = finished.pop(0)
            if jid in self._jobs and self._jobs[jid].status in terminal:
                del self._jobs[jid]

    async def _fetch_live_stock(self, client: ShoperClient, stock_id: int) -> dict | None:
        raw = await client.get_raw(f"/product-stocks/{stock_id}")
        if isinstance(raw, dict) and _shoper_stock_id(raw):
            return raw
        return None

    async def _fetch_live_product(self, client: ShoperClient, product_id: int) -> dict | None:
        raw = await client.get_raw(f"/products/{product_id}")
        if isinstance(raw, dict):
            pid = _shoper_product_id(raw)
            if pid or raw.get("code") is not None:
                return raw
        return None

    async def _build_stock_cache(
        self,
        db: AsyncSession,
        store_id: int,
        codes: set[str],
    ) -> dict[str, dict]:
        """Bulk-fetch stock data from local DB for all codes in file.

        Ładuje WSZYSTKIE stocki sklepu (nie filtruje po kodzie — unika limitu 32767
        parametrów asyncpg przy dużych plikach). Filtruje do żądanych kodów w Pythonie.
        Falls back to API for codes missing from local DB.
        """
        if not codes:
            return {}
        result = await db.execute(
            select(
                RawProductStock.stock_id,
                RawProductStock.product_id,
                RawProductStock.code,
                RawProductStock.price,
                RawProductStock.extended,
                RawProductStock.active,
                RawProductStock.default,
            ).where(RawProductStock.store_id == store_id)
        )
        cache: dict[str, dict] = {}
        for row in result:
            code = row.code
            if not code or code not in codes:
                continue
            cache[code] = {
                "stock_id": row.stock_id,
                "id": row.stock_id,
                "product_id": row.product_id,
                "code": code,
                "price": float(row.price or 0),
                "extended": row.extended,
                "active": row.active,
                "default": row.default,
            }
        return cache

    async def _resolve_stock_live(
        self,
        client: ShoperClient,
        db: AsyncSession,
        store_id: int,
        code: str,
    ) -> dict | None:
        """Kod → stan w Shoper (API). Lokalna DB tylko jako indeks stock_id, jeśli filtr API zawiedzie."""
        items = await client.get_filtered("/product-stocks", {"code": code})
        for item in items:
            if (item.get("code") or "").strip() == code:
                return item
        if items:
            return items[0]

        row = await self._get_stock_by_code(db, store_id, code)
        if row is None:
            return None
        return await self._fetch_live_stock(client, int(row.stock_id))

    async def _resolve_product_live(
        self,
        client: ShoperClient,
        db: AsyncSession,
        store_id: int,
        code: str,
    ) -> tuple[dict | None, dict | None]:
        """Zwraca (produkt, opcjonalny stock bazowy) — dane wyłącznie z API Shoper."""
        items = await client.get_filtered("/products", {"code": code})
        for item in items:
            if (item.get("code") or "").strip() == code:
                product_id = _shoper_product_id(item)
                if product_id:
                    live = await self._fetch_live_product(client, product_id)
                    return live or item, None

        base_row = await self._get_base_stock(db, store_id, code)
        if base_row is None:
            return None, None
        stock_live = await self._fetch_live_stock(client, int(base_row.stock_id))
        if stock_live is None:
            return None, None
        product_id = _shoper_product_id(stock_live)
        if not product_id:
            return None, stock_live
        product_live = await self._fetch_live_product(client, product_id)
        return product_live, stock_live

    async def _list_live_stocks_for_product(
        self, client: ShoperClient, product_id: int
    ) -> list[dict]:
        items = await client.get_filtered("/product-stocks", {"product_id": product_id})
        return [i for i in items if isinstance(i, dict)]

    async def _run_job(self, job_id: str) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return

        job.status = "RUNNING"
        job.started_at = _now_iso()
        job.started_at_ts = datetime.now(timezone.utc).timestamp()
        await self._persist_job(job, force=True)

        async with async_session() as db:
            store = (
                await db.execute(
                    select(Store).where(Store.id == job.store_id, Store.is_active.is_(True))
                )
            ).scalar_one_or_none()
            if not store:
                job.status = "FAILED"
                job.finished_at = _now_iso()
                job.fatal_error = "Store not found or inactive"
                return

            async def _refresh_token() -> str:
                # Osobna sesja DB — commit przy /auth nie psuje zapytań w trakcie joba.
                async with async_session() as refresh_db:
                    store_row = (
                        await refresh_db.execute(
                            select(Store).where(
                                Store.id == job.store_id, Store.is_active.is_(True)
                            )
                        )
                    ).scalar_one_or_none()
                    if store_row is None:
                        raise ShoperAuthError("Store not found during token refresh")
                    token = await ensure_store_token(
                        refresh_db, store_row, force_refresh=True
                    )
                store.api_token = token
                client.set_token(token)
                return token

            client = ShoperClient(store.api_url, store.api_token, on_unauthorized=_refresh_token)
            product_min_in_file: dict[int, tuple[str, float]] = {}
            try:
                if job.target_mode == "variant":
                    post_processed: set[int] = set()

                    # Wczytaj cache kodów z lokalnej DB (eliminuje GET /product-stocks?code=X per wiersz)
                    cache = await self._build_stock_cache(db, job.store_id, job.codes_in_file)

                    # Równoległe przetwarzanie wierszy z ograniczeniem do PRICE_UPDATE_CONCURRENCY
                    sem = asyncio.Semaphore(PRICE_UPDATE_CONCURRENCY)
                    _auth_exc: list[Exception] = []

                    async def _process_one(row: PriceUpdateRow) -> int | None:
                        async with sem:
                            if _auth_exc:
                                return None
                            self._set_progress(
                                job, phase="row", code=row.code, row_number=row.row_number
                            )
                            try:
                                return await self._process_variant_row(
                                    db, client, job, row, product_min_in_file, cache=cache
                                )
                            except (ShoperUnauthorizedError, ShoperAuthError) as exc:
                                _auth_exc.append(exc)
                                return None
                            except Exception as exc:
                                await self._log_row_crash(job, row, exc)
                                return None

                    await asyncio.gather(*[_process_one(row) for row in job.rows])

                    if _auth_exc:
                        raise _auth_exc[0]

                    # Post-process wszystkich produktów (po zakończeniu fazy równoległej)
                    for product_id in job.product_ids_in_file:
                        if product_id not in post_processed:
                            code = product_min_in_file.get(product_id, ("", 0))[0] or f"id={product_id}"
                            self._set_progress(job, phase="post_process", code=code)
                            try:
                                await self._post_process_single_product(
                                    client, job, product_id, product_min_in_file
                                )
                            except (ShoperUnauthorizedError, ShoperAuthError):
                                raise
                            except Exception as exc:
                                await self._log_post_process_crash(
                                    job, exc, label=f"post-process produkt {product_id}"
                                )
                            post_processed.add(product_id)

                else:
                    for row in job.rows:
                        self._set_progress(
                            job, phase="row", code=row.code, row_number=row.row_number
                        )
                        try:
                            await self._process_product_row(db, client, job, row)
                        except (ShoperUnauthorizedError, ShoperAuthError):
                            raise
                        except Exception as exc:
                            await self._log_row_crash(job, row, exc)

                job.status = "DONE"
            except (ShoperUnauthorizedError, ShoperAuthError) as exc:
                job.status = "FAILED"
                job.fatal_error = f"Autoryzacja Shoper: {exc}"
                await self._add_log(
                    job,
                    row=PriceUpdateRow(row_number=0, code="", price=0),
                    old_price=None,
                    status="ERROR",
                    message=str(exc),
                )
            except Exception as exc:
                job.status = "FAILED"
                job.fatal_error = str(exc)
                await self._add_log(
                    job,
                    row=PriceUpdateRow(row_number=0, code="", price=0),
                    old_price=None,
                    status="ERROR",
                    message=f"Krytyczny błąd joba: {exc}",
                )
            finally:
                job.finished_at = _now_iso()
                self._clear_progress(job)
                job.rows = []
                job.codes_in_file = set()
                await client.close()
                await self._persist_job(job, force=True)

    async def _log_row_crash(
        self, job: PriceUpdateJob, row: PriceUpdateRow, exc: Exception
    ) -> None:
        await self._add_log(
            job,
            row=row,
            old_price=None,
            status="ERROR",
            message=f"Nieobsłużony błąd wiersza: {exc}",
        )
        job.processed += 1
        job.failed += 1

    async def _log_post_process_crash(
        self, job: PriceUpdateJob, exc: Exception, *, label: str = "operacje po wierszach"
    ) -> None:
        await self._add_log(
            job,
            row=PriceUpdateRow(row_number=0, code="", price=0),
            old_price=None,
            status="ERROR",
            message=f"Błąd ({label}): {exc}",
        )
        job.warning += 1

    async def _ensure_product_active(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_id: int,
        *,
        log_code: str,
    ) -> bool:
        live = await self._fetch_live_product(client, product_id)
        if live is not None and _shoper_bool(live.get("active")):
            return False

        response, api_err = await client.put_with_error(
            f"/products/{product_id}",
            _product_active_payload(True),
        )
        if response is None:
            await self._add_log(
                job,
                row=PriceUpdateRow(row_number=0, code=log_code, price=0),
                old_price=None,
                status="ERROR",
                message=f"Nie udało się aktywować produktu (product_id={product_id}): {api_err or 'unknown'}",
                product_id=product_id,
            )
            job.warning += 1
            return False

        await self._add_log(
            job,
            row=PriceUpdateRow(row_number=0, code=log_code, price=0),
            old_price=None,
            status="SUCCESS",
            message=f"Produkt aktywowany w Shoper (product_id={product_id})",
            http_status=200,
            product_id=product_id,
        )
        return True

    async def _ensure_stock_active(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        live: dict,
        row: PriceUpdateRow,
    ) -> bool:
        if _shoper_bool(live.get("active")):
            return False

        stock_id = _shoper_stock_id(live)
        product_id = _shoper_product_id(live)
        old_price = _shoper_price(live)
        response, api_err = await client.put_with_error(
            f"/product-stocks/{stock_id}",
            _stock_active_payload(True),
        )
        if response is None:
            await self._add_log(
                job,
                row=row,
                old_price=old_price,
                status="ERROR",
                message=f"Nie udało się aktywować wariantu: {api_err or 'unknown'}",
                product_id=product_id,
                stock_id=stock_id,
            )
            job.warning += 1
            return False

        await self._add_log(
            job,
            row=row,
            old_price=old_price,
            status="SUCCESS",
            message="Wariant aktywowany w Shoper",
            http_status=200,
            product_id=product_id,
            stock_id=stock_id,
        )
        return True

    async def _process_product_row(
        self, db: AsyncSession, client: ShoperClient, job: PriceUpdateJob, row: PriceUpdateRow
    ) -> None:
        product_live, stock_live = await self._resolve_product_live(
            client, db, job.store_id, row.code
        )
        if product_live is None:
            await self._add_log(
                job,
                row=row,
                old_price=None,
                status="SKIPPED",
                message="Product code not found in Shoper",
                http_status=404,
            )
            job.processed += 1
            job.skipped += 1
            return

        product_id = _shoper_product_id(product_live)
        stock_id = _shoper_stock_id(stock_live) if stock_live else None
        old_price = _shoper_price(product_live)

        job.product_ids_in_file.add(product_id)
        await self._ensure_product_active(client, job, product_id, log_code=row.code)

        if abs(old_price - row.price) < 0.000001:
            if self._should_log_skipped_row(job, "Price unchanged (Shoper)"):
                await self._add_log(
                    job,
                    row=row,
                    old_price=old_price,
                    status="SKIPPED",
                    message="Price unchanged (Shoper)",
                    http_status=200,
                    product_id=product_id,
                    stock_id=stock_id,
                )
            job.processed += 1
            job.skipped += 1
            return

        response, api_err = await client.put_with_error(
            f"/products/{product_id}",
            {**_product_active_payload(True), "price": row.price},
        )
        if response is None:
            await self._add_log(
                job,
                row=row,
                old_price=old_price,
                status="ERROR",
                message=f"Shoper API product update failed: {api_err or 'unknown'}",
                product_id=product_id,
                stock_id=stock_id,
            )
            job.processed += 1
            job.failed += 1
            return

        await self._add_log(
            job,
            row=row,
            old_price=old_price,
            status="SUCCESS",
            message="Product price updated in Shoper",
            http_status=200,
            request_id=_response_request_id(response),
            product_id=product_id,
            stock_id=stock_id,
        )
        job.processed += 1
        job.success += 1

    async def _process_variant_row(
        self,
        db: AsyncSession,
        client: ShoperClient,
        job: PriceUpdateJob,
        row: PriceUpdateRow,
        product_min_in_file: dict[int, tuple[str, float]],
        *,
        cache: dict[str, dict] | None = None,
    ) -> int | None:
        """Zwraca product_id jeśli wiersz zostal przetworzony, None jeśli nie znaleziono."""
        # DB-first lookup: eliminuje GET /product-stocks?code=X dla znanych kodów
        if cache is not None and row.code in cache:
            live = cache[row.code]
        else:
            live = await self._resolve_stock_live(client, db, job.store_id, row.code)
        if live is None:
            await self._add_log(
                job,
                row=row,
                old_price=None,
                status="SKIPPED",
                message="Variant code not found in Shoper",
                http_status=404,
            )
            job.processed += 1
            job.skipped += 1
            return None

        product_id = _shoper_product_id(live)
        stock_id = _shoper_stock_id(live)
        job.product_ids_in_file.add(product_id)
        old_price = _shoper_price(live)

        await self._ensure_stock_active(client, job, live, row)

        if abs(old_price - row.price) < 0.000001:
            if self._should_log_skipped_row(job, "Price unchanged (Shoper)"):
                await self._add_log(
                    job,
                    row=row,
                    old_price=old_price,
                    status="SKIPPED",
                    message="Price unchanged (Shoper)",
                    http_status=200,
                    product_id=product_id,
                    stock_id=stock_id,
                )
            job.processed += 1
            job.skipped += 1
        else:
            response, api_err = await client.put_with_error(
                f"/product-stocks/{stock_id}",
                {**_stock_active_payload(True), "price": row.price},
            )
            if response is None:
                await self._add_log(
                    job,
                    row=row,
                    old_price=old_price,
                    status="ERROR",
                    message=f"Shoper API variant update failed: {api_err or 'unknown'}",
                    product_id=product_id,
                    stock_id=stock_id,
                )
                job.processed += 1
                job.failed += 1
            else:
                await self._add_log(
                    job,
                    row=row,
                    old_price=old_price,
                    status="SUCCESS",
                    message="Variant price updated in Shoper",
                    http_status=200,
                    request_id=_response_request_id(response),
                    product_id=product_id,
                    stock_id=stock_id,
                )
                job.processed += 1
                job.success += 1

        current = product_min_in_file.get(product_id)
        if current is None or row.price < current[1]:
            product_min_in_file[product_id] = (row.code, row.price)

        return product_id

    async def _post_process_single_product(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_id: int,
        product_min_in_file: dict[int, tuple[str, float]],
    ) -> None:
        """Post-process: ceny, domyślny wariant, aktywacja produktu, wyłączenie wariantów spoza pliku (tylko extended)."""
        cheapest_code = product_min_in_file.get(product_id, (None, 0))[0] or ""
        try:
            await self._apply_single_product_price(client, job, product_id, product_min_in_file)
        except (ShoperUnauthorizedError, ShoperAuthError):
            raise
        except Exception as exc:
            await self._log_post_process_crash(job, exc, label=f"cena produktu {product_id}")
        try:
            await self._promote_default_to_file_variant(client, job, product_id, product_min_in_file)
        except (ShoperUnauthorizedError, ShoperAuthError):
            raise
        except Exception as exc:
            await self._log_post_process_crash(job, exc, label=f"default wariant {product_id}")
        try:
            await self._ensure_product_active(client, job, product_id, log_code=cheapest_code)
        except (ShoperUnauthorizedError, ShoperAuthError):
            raise
        except Exception as exc:
            await self._log_post_process_crash(job, exc, label=f"aktywacja {product_id}")
        if job.disable_extra_variants:
            try:
                await self._deactivate_variants_not_in_file_for_product(
                    client, job, product_id, product_min_in_file, reason="po aktywacji"
                )
            except (ShoperUnauthorizedError, ShoperAuthError):
                raise
            except Exception as exc:
                await self._log_post_process_crash(job, exc, label=f"dezaktywacja wariantów {product_id}")

    async def _apply_single_product_price(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_id: int,
        product_min_in_file: dict[int, tuple[str, float]],
    ) -> None:
        """Ustaw cenę stocku bazowego i produktu na min. cenę wariantów z pliku."""
        entry = product_min_in_file.get(product_id)
        if entry is None:
            return
        cheapest_code, min_price = entry
        await self._apply_product_prices_from_variants(
            client, job, {product_id: (cheapest_code, min_price)}
        )

    async def _apply_product_prices_from_variants(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_min_in_file: dict[int, tuple[str, float]],
    ) -> None:
        """Ustaw cenę produktu i stocku bazowego na min. cenę wariantów z pliku.

        Shoper dla produktów z wariantami wyświetla min(ceny aktywnych stocków) — samo ustawienie
        products.price nie zmienia widocznej ceny. Musimy też zaktualizować stock bazowy (extended=false).
        """
        for product_id, (cheapest_code, min_price) in product_min_in_file.items():
            # --- stock bazowy (extended=false) → jego cena jest wyświetlana na stronie ---
            stocks = await self._list_live_stocks_for_product(client, product_id)
            base_stock = next(
                (s for s in stocks if isinstance(s, dict) and not _shoper_bool(s.get("extended"))),
                None,
            )
            if base_stock is not None:
                base_id = _shoper_stock_id(base_stock)
                base_old_price = _shoper_price(base_stock)
                if base_id and abs(base_old_price - min_price) > 0.000001:
                    resp, err = await client.put_with_error(
                        f"/product-stocks/{base_id}",
                        {"price": min_price},
                    )
                    if resp is None:
                        await self._add_log(
                            job,
                            row=PriceUpdateRow(row_number=0, code=cheapest_code, price=min_price),
                            old_price=base_old_price,
                            status="WARNING",
                            message=(
                                f"Nie udało się ustawić ceny stocku bazowego product_id={product_id} "
                                f"na {min_price:.2f}: {err or 'unknown'}"
                            ),
                            product_id=product_id,
                            stock_id=base_id,
                        )
                        job.warning += 1
                    else:
                        await self._add_log(
                            job,
                            row=PriceUpdateRow(row_number=0, code=cheapest_code, price=min_price),
                            old_price=base_old_price,
                            status="SUCCESS",
                            message=(
                                f"Cena stocku bazowego = {min_price:.2f} "
                                f"(najniższa z pliku, wariant {cheapest_code})"
                            ),
                            http_status=200,
                            product_id=product_id,
                            stock_id=base_id,
                        )

            # --- products.price — aktualizujemy dla spójności (listingi, API) ---
            live = await self._fetch_live_product(client, product_id)
            old_price = _shoper_price(live) if live else None
            if live is not None and abs(old_price - min_price) < 0.000001:
                continue
            response, api_err = await client.put_with_error(
                f"/products/{product_id}",
                {"price": min_price},
            )
            if response is None:
                await self._add_log(
                    job,
                    row=PriceUpdateRow(row_number=0, code=cheapest_code, price=min_price),
                    old_price=old_price,
                    status="WARNING",
                    message=(
                        f"Nie udało się ustawić ceny produktu product_id={product_id} "
                        f"na {min_price:.2f}: {api_err or 'unknown'}"
                    ),
                    product_id=product_id,
                )
                job.warning += 1
                continue
            await self._add_log(
                job,
                row=PriceUpdateRow(row_number=0, code=cheapest_code, price=min_price),
                old_price=old_price,
                status="SUCCESS",
                message=(
                    f"Cena produktu w Shoper = {min_price:.2f} "
                    f"— najniższa z pliku (wariant {cheapest_code})"
                ),
                http_status=200,
                product_id=product_id,
            )

    async def _promote_default_to_file_variant(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_id: int,
        product_min_in_file: dict[int, tuple[str, float]],
    ) -> None:
        """Ustaw domyślny wariant na ten z pliku, gdy bazowy stock nie jest w CSV."""
        preferred = product_min_in_file.get(product_id, (None, 0))[0]
        if not preferred:
            return
        stocks = await self._list_live_stocks_for_product(client, product_id)
        has_base_off_file = any(
            _is_base_stock(s)
            and (s.get("code") or "").strip()
            and (s.get("code") or "").strip() not in job.codes_in_file
            for s in stocks
            if isinstance(s, dict)
        )
        if not has_base_off_file:
            return
        replacement = await self._find_replacement_default_stock(
            client, job, product_id, preferred
        )
        if replacement is None:
            return
        rep_code = (replacement.get("code") or "").strip()
        rep_id = _shoper_stock_id(replacement)
        _, err = await client.put_with_error(
            f"/product-stocks/{rep_id}",
            _stock_active_payload(True, default=True),
        )
        if err:
            await self._add_log(
                job,
                row=PriceUpdateRow(row_number=0, code=rep_code, price=0),
                old_price=_shoper_price(replacement),
                status="WARNING",
                message=f"Nie udało się ustawić domyślnego wariantu na {rep_code}: {err}",
                product_id=product_id,
                stock_id=rep_id,
            )
            job.warning += 1
            return
        await self._add_log(
            job,
            row=PriceUpdateRow(row_number=0, code=rep_code, price=0),
            old_price=_shoper_price(replacement),
            status="SUCCESS",
            message=(
                f"Domyślny wariant ustawiony na {rep_code} (produkt ma stock bazowy spoza pliku)"
            ),
            product_id=product_id,
            stock_id=rep_id,
        )

    async def _deactivate_stock_variant(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        live: dict,
        product_min_in_file: dict[int, tuple[str, float]],
        *,
        log_label: str,
        skip_refetch: bool = False,
    ) -> None:
        """Wyłącz pojedynczy wariant rozszerzony (extended). Nie dotyka stocku bazowego ani produktów spoza pliku."""
        code = (live.get("code") or "").strip()
        if not code or code in job.codes_in_file:
            return

        product_id = _shoper_product_id(live)
        stock_id = _shoper_stock_id(live)
        if not skip_refetch:
            fresh = await self._fetch_live_stock(client, stock_id)
            if fresh is not None:
                live = fresh
        old_price = _shoper_price(live)

        if _is_base_stock(live):
            return

        if _shoper_bool(live.get("default")):
            preferred = product_min_in_file.get(product_id, (None, 0))[0]
            replacement = await self._find_replacement_default_stock(
                client, job, product_id, preferred
            )
            if replacement is None:
                await self._add_log(
                    job,
                    row=PriceUpdateRow(row_number=0, code=code, price=0),
                    old_price=old_price,
                    status="ERROR",
                    message=(
                        f"Nie można wyłączyć domyślnego wariantu '{code}' — "
                        "brak wariantu z pliku do ustawienia jako domyślny"
                    ),
                    product_id=product_id,
                    stock_id=stock_id,
                )
                job.warning += 1
                return
            rep_id = _shoper_stock_id(replacement)
            _, rep_err = await client.put_with_error(
                f"/product-stocks/{rep_id}",
                _stock_active_payload(True, default=True),
            )
            if rep_err:
                await self._add_log(
                    job,
                    row=PriceUpdateRow(row_number=0, code=code, price=0),
                    old_price=old_price,
                    status="ERROR",
                    message=f"Nie udało się zmienić domyślnego wariantu przed wyłączeniem '{code}': {rep_err}",
                    product_id=product_id,
                    stock_id=stock_id,
                )
                job.warning += 1
                return

        response, api_err = await client.put_with_error(
            f"/product-stocks/{stock_id}",
            _stock_active_payload(False, default=False),
        )
        if response is None:
            await self._add_log(
                job,
                row=PriceUpdateRow(row_number=0, code=code, price=0),
                old_price=old_price,
                status="WARNING",
                message=f"Nie udało się wyłączyć wariantu ({log_label}): {api_err or 'unknown'}",
                product_id=product_id,
                stock_id=stock_id,
            )
            job.warning += 1
            return

        await self._add_log(
            job,
            row=PriceUpdateRow(row_number=0, code=code, price=0),
            old_price=old_price,
            status="SUCCESS",
            message=f"Wariant rozszerzony wyłączony w Shoper ({log_label})",
            http_status=200,
            product_id=product_id,
            stock_id=stock_id,
        )
        job.deactivated_variants += 1

    async def _deactivate_variants_not_in_file_for_product(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_id: int,
        product_min_in_file: dict[int, tuple[str, float]],
        *,
        reason: str,
    ) -> None:
        """Wyłącz warianty extended spoza pliku — tylko u produktu obecnego w CSV. Stock bazowy pomijamy."""
        all_stocks = await self._list_live_stocks_for_product(client, product_id)
        extended = [s for s in all_stocks if isinstance(s, dict) and _shoper_bool(s.get("extended"))]
        off_file = [
            (s.get("code") or "").strip()
            for s in extended
            if (s.get("code") or "").strip() and (s.get("code") or "").strip() not in job.codes_in_file
        ]

        if not off_file and not extended:
            return

        await self._add_log(
            job,
            row=PriceUpdateRow(row_number=0, code=off_file[0] if off_file else "", price=0),
            old_price=None,
            status="SUCCESS",
            message=(
                f"[{reason}] product_id={product_id}: "
                f"{len(extended)} wariantów rozszerzonych, "
                f"do wyłączenia (spoza pliku): {len(off_file)}"
                + (f" ({', '.join(off_file[:8])}{'…' if len(off_file) > 8 else ''})" if off_file else "")
            ),
            product_id=product_id,
        )

        for live in extended:
            c = (live.get("code") or "").strip()
            if not c or c in job.codes_in_file:
                continue
            await self._deactivate_stock_variant(
                client,
                job,
                live,
                product_min_in_file,
                log_label=f"brak w pliku — {reason}",
                skip_refetch=True,
            )

    async def _find_replacement_default_stock(
        self,
        client: ShoperClient,
        job: PriceUpdateJob,
        product_id: int,
        preferred_code: str | None,
    ) -> dict | None:
        if preferred_code:
            items = await client.get_filtered(
                "/product-stocks",
                {"product_id": product_id, "code": preferred_code},
            )
            for item in items:
                if (item.get("code") or "").strip() == preferred_code:
                    return item

        for code in sorted(job.codes_in_file):
            items = await client.get_filtered(
                "/product-stocks",
                {"product_id": product_id, "code": code},
            )
            for item in items:
                if (item.get("code") or "").strip() == code:
                    return item
        return None

    async def _get_base_stock(
        self, db: AsyncSession, store_id: int, code: str
    ) -> RawProductStock | None:
        return (
            await db.execute(
                select(RawProductStock).where(
                    RawProductStock.store_id == store_id,
                    RawProductStock.code == code,
                    or_(RawProductStock.extended.is_(False), RawProductStock.extended.is_(None)),
                ).limit(1)
            )
        ).scalars().first()

    async def _get_stock_by_code(
        self, db: AsyncSession, store_id: int, code: str
    ) -> RawProductStock | None:
        return (
            await db.execute(
                select(RawProductStock).where(
                    RawProductStock.store_id == store_id,
                    RawProductStock.code == code,
                ).limit(1)
            )
        ).scalars().first()

    async def _add_log(
        self,
        job: PriceUpdateJob,
        *,
        row: PriceUpdateRow,
        old_price: float | None,
        status: LogStatus,
        message: str,
        http_status: int | None = None,
        request_id: str | None = None,
        product_id: int | None = None,
        stock_id: int | None = None,
    ) -> None:
        entry = PriceUpdateLogEntry(
            timestamp=_now_iso(),
            job_id=job.job_id,
            row_number=row.row_number,
            code=row.code,
            old_price=old_price,
            new_price=row.price if row.price > 0 else None,
            status=status,
            message=message,
            http_status=http_status,
            request_id=request_id or None,
            comment=row.comment,
            product_id=product_id,
            stock_id=stock_id,
        )
        job.logs.append(entry)
        job.log_seq += 1
        overflow = len(job.logs) - MAX_LOGS_IN_MEMORY
        if overflow > 0:
            del job.logs[:overflow]
            job.logs_dropped += overflow
        asyncio.create_task(self._persist_log(job, entry))
        asyncio.create_task(self._persist_job(job))

    def _should_log_skipped_row(self, job: PriceUpdateJob, message: str) -> bool:
        """Duże pliki: nie zapisuj tysięcy identycznych SKIPPED w pamięci."""
        if job.total < BULK_JOB_ROW_THRESHOLD:
            return True
        return "Price unchanged" not in message


price_update_jobs = PriceUpdateJobManager()
