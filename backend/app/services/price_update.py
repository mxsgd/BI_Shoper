from __future__ import annotations

import asyncio
import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import select

from ..database import async_session
from ..models.product import Product
from ..models.store import Store
from .shoper_client import ShoperClient

JobStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED", "CANCELLED"]
LogStatus = Literal["SUCCESS", "ERROR", "SKIPPED", "WARNING"]

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000


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
    status: JobStatus = "PENDING"
    started_at: str | None = None
    finished_at: str | None = None
    total: int = 0
    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    warning: int = 0
    rows: list[PriceUpdateRow] = field(default_factory=list)
    logs: list[PriceUpdateLogEntry] = field(default_factory=list)
    validation_errors: list[ValidationError] = field(default_factory=list)
    fatal_error: str | None = None


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
) -> tuple[list[PriceUpdateRow], list[ValidationError]]:
    reader = csv.DictReader(io.StringIO(csv_text))
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
            errors.append(ValidationError(row_number=idx, code="", error_message="Code is required"))
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


class PriceUpdateJobManager:
    def __init__(self):
        self._jobs: dict[str, PriceUpdateJob] = {}
        self._lock = asyncio.Lock()

    async def create_job(
        self,
        *,
        store_id: int,
        file_name: str,
        csv_bytes: bytes,
        duplicate_mode: Literal["error", "last_wins"] = "error",
    ) -> PriceUpdateJob:
        if len(csv_bytes) > MAX_FILE_BYTES:
            raise ValueError(f"File too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB)")
        text = csv_bytes.decode("utf-8-sig", errors="replace")
        rows, validation_errors = _parse_csv_rows(text, duplicate_mode=duplicate_mode)
        if len(rows) > MAX_ROWS:
            raise ValueError(f"Too many rows (max {MAX_ROWS})")

        job = PriceUpdateJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            store_id=store_id,
            file_name=file_name or "upload.csv",
            created_at=_now_iso(),
            rows=rows,
            total=len(rows),
            validation_errors=validation_errors,
        )
        async with self._lock:
            self._jobs[job.job_id] = job

        if validation_errors:
            job.status = "FAILED"
            job.fatal_error = "Validation failed"
            return job

        asyncio.create_task(self._run_job(job.job_id))
        return job

    async def get_job(self, job_id: str) -> PriceUpdateJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def _run_job(self, job_id: str) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return

        job.status = "RUNNING"
        job.started_at = _now_iso()

        async with async_session() as db:
            store = (await db.execute(select(Store).where(Store.id == job.store_id, Store.is_active.is_(True)))).scalar_one_or_none()
            if not store:
                job.status = "FAILED"
                job.finished_at = _now_iso()
                job.fatal_error = "Store not found or inactive"
                return
            client = ShoperClient(store.api_url, store.api_token)
            try:
                for row in job.rows:
                    await self._process_row(db, client, job, row)
                await db.commit()
                job.status = "DONE"
            except Exception as exc:
                job.status = "FAILED"
                job.fatal_error = str(exc)
            finally:
                job.finished_at = _now_iso()
                await client.close()

    async def _process_row(self, db, client: ShoperClient, job: PriceUpdateJob, row: PriceUpdateRow) -> None:
        product = (
            await db.execute(
                select(Product).where(
                    Product.store_id == job.store_id,
                    Product.code == row.code,
                ).limit(1)
            )
        ).scalars().first()

        if not product:
            await self._add_log(
                job,
                row=row,
                old_price=None,
                status="SKIPPED",
                message="Product code not found",
                http_status=404,
            )
            job.processed += 1
            job.skipped += 1
            return

        old_price = float(product.price or 0)
        if abs(old_price - row.price) < 0.000001:
            await self._add_log(
                job,
                row=row,
                old_price=old_price,
                status="SKIPPED",
                message="Price unchanged",
                http_status=200,
            )
            job.processed += 1
            job.skipped += 1
            return

        payload = {"price": row.price}
        response = await client.put(f"/products/{product.shoper_product_id}", payload)
        if response is None:
            await self._add_log(
                job,
                row=row,
                old_price=old_price,
                status="ERROR",
                message="Shoper API update failed",
            )
            job.processed += 1
            job.failed += 1
            return

        product.price = row.price
        await self._add_log(
            job,
            row=row,
            old_price=old_price,
            status="SUCCESS",
            message="Price updated",
            http_status=200,
            request_id=str(response.get("request_id") or response.get("trace_id") or ""),
        )
        job.processed += 1
        job.success += 1

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
    ) -> None:
        entry = PriceUpdateLogEntry(
            timestamp=_now_iso(),
            job_id=job.job_id,
            row_number=row.row_number,
            code=row.code,
            old_price=old_price,
            new_price=row.price,
            status=status,
            message=message,
            http_status=http_status,
            request_id=request_id or None,
            comment=row.comment,
        )
        job.logs.append(entry)


price_update_jobs = PriceUpdateJobManager()
