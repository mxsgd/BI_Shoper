"""Persist price update jobs and logs to PostgreSQL."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..database import async_session
from ..models.price_update_job import PriceUpdateJobRecord, PriceUpdateLogRecord

if TYPE_CHECKING:
    from .price_update import PriceUpdateJob, PriceUpdateLogEntry, ValidationError

LogStatus = Literal["ALL", "SUCCESS", "ERROR", "WARNING", "SKIPPED"]


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _record_to_job(row: PriceUpdateJobRecord) -> PriceUpdateJob:
    from .price_update import PriceUpdateJob, ValidationError

    validation: list[ValidationError] = []
    for item in row.validation_errors or []:
        validation.append(
            ValidationError(
                row_number=int(item.get("row_number", 0)),
                code=str(item.get("code", "")),
                error_message=str(item.get("error_message", "")),
            )
        )
    started_ts = None
    if row.started_at:
        started_ts = row.started_at.timestamp()
    return PriceUpdateJob(
        job_id=row.job_id,
        store_id=row.store_id,
        file_name=row.file_name,
        created_at=_dt_to_iso(row.created_at) or "",
        target_mode=row.target_mode,  # type: ignore[arg-type]
        csv_delimiter=row.csv_delimiter,  # type: ignore[arg-type]
        disable_extra_variants=row.disable_extra_variants,
        status=row.status,  # type: ignore[arg-type]
        started_at=_dt_to_iso(row.started_at),
        finished_at=_dt_to_iso(row.finished_at),
        total=row.total,
        processed=row.processed,
        success=row.success,
        failed=row.failed,
        skipped=row.skipped,
        warning=row.warning,
        deactivated_variants=row.deactivated_variants,
        validation_errors=validation,
        fatal_error=row.fatal_error,
        log_seq=row.log_seq,
        logs_dropped=row.logs_dropped,
        started_at_ts=started_ts,
        current_row_number=row.current_row_number,
        current_code=row.current_code,
        current_phase=row.current_phase,
    )


def _log_record_to_entry(row: PriceUpdateLogRecord) -> PriceUpdateLogEntry:
    from .price_update import PriceUpdateLogEntry

    return PriceUpdateLogEntry(
        timestamp=_dt_to_iso(row.timestamp) or "",
        job_id=row.job_id,
        row_number=row.row_number,
        code=row.code,
        old_price=row.old_price,
        new_price=row.new_price,
        status=row.status,  # type: ignore[arg-type]
        message=row.message,
        http_status=row.http_status,
        request_id=row.request_id,
        comment=row.comment,
        product_id=row.product_id,
        stock_id=row.stock_id,
    )


async def save_job(
    job: PriceUpdateJob,
    *,
    duplicate_mode: str = "error",
) -> None:
    validation_payload = [e.__dict__ for e in job.validation_errors]
    values = {
        "job_id": job.job_id,
        "store_id": job.store_id,
        "file_name": job.file_name,
        "status": job.status,
        "target_mode": job.target_mode,
        "csv_delimiter": job.csv_delimiter,
        "disable_extra_variants": job.disable_extra_variants,
        "duplicate_mode": duplicate_mode,
        "created_at": _parse_iso(job.created_at) or datetime.now(timezone.utc),
        "started_at": _parse_iso(job.started_at),
        "finished_at": _parse_iso(job.finished_at),
        "total": job.total,
        "processed": job.processed,
        "success": job.success,
        "failed": job.failed,
        "skipped": job.skipped,
        "warning": job.warning,
        "deactivated_variants": job.deactivated_variants,
        "log_seq": job.log_seq,
        "logs_dropped": job.logs_dropped,
        "current_row_number": job.current_row_number,
        "current_code": job.current_code,
        "current_phase": job.current_phase,
        "fatal_error": job.fatal_error,
        "validation_errors": validation_payload or None,
    }
    stmt = pg_insert(PriceUpdateJobRecord).values(**values)
    update_cols = {k: v for k, v in values.items() if k not in ("job_id", "store_id", "created_at")}
    stmt = stmt.on_conflict_do_update(index_elements=["job_id"], set_=update_cols)
    async with async_session() as db:
        await db.execute(stmt)
        await db.commit()


async def save_log(entry: PriceUpdateLogEntry, *, seq: int) -> None:
    async with async_session() as db:
        db.add(
            PriceUpdateLogRecord(
                job_id=entry.job_id,
                seq=seq,
                timestamp=_parse_iso(entry.timestamp) or datetime.now(timezone.utc),
                row_number=entry.row_number,
                code=entry.code,
                old_price=entry.old_price,
                new_price=entry.new_price,
                status=entry.status,
                message=entry.message,
                http_status=entry.http_status,
                request_id=entry.request_id,
                comment=entry.comment,
                product_id=entry.product_id,
                stock_id=entry.stock_id,
            )
        )
        await db.commit()


async def load_job(job_id: str) -> PriceUpdateJob | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(PriceUpdateJobRecord).where(PriceUpdateJobRecord.job_id == job_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _record_to_job(row)


async def load_active_job(store_id: int) -> PriceUpdateJob | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(PriceUpdateJobRecord)
                .where(
                    PriceUpdateJobRecord.store_id == store_id,
                    PriceUpdateJobRecord.status.in_(("PENDING", "RUNNING")),
                )
                .order_by(PriceUpdateJobRecord.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _record_to_job(row)


async def load_latest_job(store_id: int) -> PriceUpdateJob | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(PriceUpdateJobRecord)
                .where(PriceUpdateJobRecord.store_id == store_id)
                .order_by(PriceUpdateJobRecord.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _record_to_job(row)


async def load_logs(
    job_id: str,
    *,
    status: LogStatus = "ALL",
    query: str | None = None,
    page: int = 1,
    per_page: int = 100,
    tail: int | None = None,
) -> tuple[list[PriceUpdateLogEntry], int, int]:
    """Returns (items, total_count, logs_dropped from job record)."""
    async with async_session() as db:
        job_row = (
            await db.execute(
                select(PriceUpdateJobRecord).where(PriceUpdateJobRecord.job_id == job_id)
            )
        ).scalar_one_or_none()
        if job_row is None:
            return [], 0, 0

        base = select(PriceUpdateLogRecord).where(PriceUpdateLogRecord.job_id == job_id)
        if status != "ALL":
            base = base.where(PriceUpdateLogRecord.status == status)
        if query:
            q = f"%{query.strip().lower()}%"
            base = base.where(func.lower(PriceUpdateLogRecord.code).like(q))

        total = (
            await db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        if tail is not None:
            rows = (
                await db.execute(
                    base.order_by(PriceUpdateLogRecord.seq.desc()).limit(tail)
                )
            ).scalars().all()
            rows = list(reversed(rows))
            total = int(job_row.log_seq or total)
        else:
            offset = (page - 1) * per_page
            rows = (
                await db.execute(
                    base.order_by(PriceUpdateLogRecord.seq.asc())
                    .offset(offset)
                    .limit(per_page)
                )
            ).scalars().all()

        return (
            [_log_record_to_entry(r) for r in rows],
            int(total),
            int(job_row.logs_dropped or 0),
        )


async def iter_all_logs(job_id: str):
    """Stream all log rows for CSV export."""
    async with async_session() as db:
        result = await db.stream(
            select(PriceUpdateLogRecord)
            .where(PriceUpdateLogRecord.job_id == job_id)
            .order_by(PriceUpdateLogRecord.seq.asc())
        )
        async for row in result.scalars():
            yield _log_record_to_entry(row)
