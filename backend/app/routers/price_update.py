import csv
import io
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..services.price_update import price_update_jobs

router = APIRouter(prefix="/api/price-update", tags=["price-update"])

_ALLOWED_UPLOAD_SUFFIXES = (".csv", ".txt", ".text")


def _is_allowed_price_file(filename: str | None) -> bool:
    if not filename:
        return False
    return filename.lower().endswith(_ALLOWED_UPLOAD_SUFFIXES)


def _job_stats(job) -> dict:
    processed = max(job.processed, 0)
    # success / failed / skipped = wyłącznie wiersze z pliku (cena)
    success_rate = round((job.success / processed) * 100, 2) if processed else 0.0
    failure_rate = round((job.failed / processed) * 100, 2) if processed else 0.0
    coverage_rate = round((processed / job.total) * 100, 2) if job.total else 0.0

    # ETA
    eta_seconds = None
    if job.started_at_ts and processed > 0 and job.total > processed:
        import time
        elapsed = time.time() - job.started_at_ts
        rate = processed / elapsed if elapsed > 0 else None
        if rate:
            eta_seconds = int((job.total - processed) / rate)

    return {
        "total": job.total,
        "processed": job.processed,
        "success": job.success,
        "failed": job.failed,
        "skipped": job.skipped,
        "warning": job.warning,
        "deactivated_variants": job.deactivated_variants,
        "logs_total": job.log_seq,
        "logs_in_memory": len(job.logs),
        "logs_dropped": job.logs_dropped,
        "log_seq": job.log_seq,
        "eta_seconds": eta_seconds,
        "current_row_number": job.current_row_number,
        "current_code": job.current_code,
        "current_phase": job.current_phase,
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "coverage_rate": coverage_rate,
    }


def _job_meta(job) -> dict:
    return {
        "target_mode": job.target_mode,
        "csv_delimiter": job.csv_delimiter,
    }


def _job_response(job) -> dict:
    return {
        "job_id": job.job_id,
        "store_id": job.store_id,
        "file_name": job.file_name,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "fatal_error": job.fatal_error,
        **_job_meta(job),
        "validation": {
            "valid_rows": job.total,
            "invalid_rows": len(job.validation_errors),
            "errors": [e.__dict__ for e in job.validation_errors],
        },
        "stats": _job_stats(job),
    }


@router.post("/jobs")
async def create_price_update_job(
    file: UploadFile = File(...),
    store_id: int = Query(...),
    duplicate_mode: Literal["error", "last_wins"] = Query("error"),
    target_mode: Literal["product", "variant"] = Query("product"),
    csv_delimiter: Literal["comma", "semicolon", "tab", "pipe"] = Query("semicolon"),
):
    if not _is_allowed_price_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Supported file types: .csv, .txt (comma/semicolon/tab separated)",
        )
    content = await file.read()
    try:
        job = await price_update_jobs.create_job(
            store_id=store_id,
            file_name=file.filename,
            csv_bytes=content,
            duplicate_mode=duplicate_mode,
            target_mode=target_mode,
            csv_delimiter=csv_delimiter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "job_id": job.job_id,
        "status": job.status,
        "file_name": job.file_name,
        "created_at": job.created_at,
        **_job_meta(job),
        "validation": {
            "valid_rows": job.total,
            "invalid_rows": len(job.validation_errors),
            "errors": [e.__dict__ for e in job.validation_errors],
        },
        "stats": _job_stats(job),
        "fatal_error": job.fatal_error,
    }


@router.get("/jobs/active")
async def get_active_price_update_job(store_id: int = Query(...)):
    """Bieżący RUNNING/PENDING job dla sklepu — fallback gdy UI straci localStorage."""
    job = await price_update_jobs.get_active_job(store_id)
    if job is None:
        return {"job": None}
    return {"job": _job_response(job)}


@router.get("/jobs/{job_id}")
async def get_price_update_job(job_id: str):
    job = await price_update_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@router.get("/jobs/{job_id}/logs")
async def get_price_update_logs(
    job_id: str,
    status: Literal["ALL", "SUCCESS", "ERROR", "WARNING", "SKIPPED"] = Query("ALL"),
    query: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    tail: int | None = Query(None, ge=1, le=500),
):
    """Logi joba. ``tail=N`` — tylko ostatnie N wpisów (lekki polling podczas RUNNING)."""
    job = await price_update_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    logs = job.logs[-tail:] if tail is not None else list(job.logs)

    if status != "ALL":
        logs = [l for l in logs if l.status == status]
    if query:
        q = query.strip().lower()
        logs = [l for l in logs if q in l.code.lower()]

    total = job.log_seq if tail is not None else len(logs)
    if tail is None:
        start = (page - 1) * per_page
        items = logs[start : start + per_page]
        pages = (len(logs) + per_page - 1) // per_page if logs else 1
    else:
        items = logs
        page = 1
        per_page = max(len(items), 1)
        pages = 1

    return {
        "items": [i.__dict__ for i in items],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "logs_dropped": job.logs_dropped,
        "logs_in_memory": len(job.logs),
    }


@router.get("/jobs/{job_id}/logs/export.csv")
async def export_price_update_logs(job_id: str):
    job = await price_update_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "timestamp",
            "job_id",
            "row_number",
            "code",
            "old_price",
            "new_price",
            "status",
            "message",
            "http_status",
            "request_id",
            "comment",
        ]
    )
    for l in job.logs:
        writer.writerow(
            [
                l.timestamp,
                l.job_id,
                l.row_number,
                l.code,
                "" if l.old_price is None else f"{l.old_price:.2f}",
                "" if l.new_price is None else f"{l.new_price:.2f}",
                l.status,
                l.message,
                l.http_status or "",
                l.request_id or "",
                l.comment or "",
            ]
        )
    data = output.getvalue().encode("utf-8")
    headers = {"Content-Disposition": f'attachment; filename="{job_id}_logs.csv"'}
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8", headers=headers)
