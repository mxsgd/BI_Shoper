import csv
import io
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..services.price_update import price_update_jobs

router = APIRouter(prefix="/api/price-update", tags=["price-update"])


def _job_stats(job) -> dict:
    processed = max(job.processed, 0)
    success_rate = round((job.success / processed) * 100, 2) if processed else 0.0
    failure_rate = round((job.failed / processed) * 100, 2) if processed else 0.0
    coverage_rate = round((processed / job.total) * 100, 2) if job.total else 0.0
    return {
        "total": job.total,
        "processed": job.processed,
        "success": job.success,
        "failed": job.failed,
        "skipped": job.skipped,
        "warning": job.warning,
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "coverage_rate": coverage_rate,
    }


@router.post("/jobs")
async def create_price_update_job(
    file: UploadFile = File(...),
    store_id: int = Query(...),
    duplicate_mode: Literal["error", "last_wins"] = Query("error"),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    content = await file.read()
    try:
        job = await price_update_jobs.create_job(
            store_id=store_id,
            file_name=file.filename,
            csv_bytes=content,
            duplicate_mode=duplicate_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "job_id": job.job_id,
        "status": job.status,
        "file_name": job.file_name,
        "created_at": job.created_at,
        "validation": {
            "valid_rows": job.total,
            "invalid_rows": len(job.validation_errors),
            "errors": [e.__dict__ for e in job.validation_errors],
        },
        "stats": _job_stats(job),
        "fatal_error": job.fatal_error,
    }


@router.get("/jobs/{job_id}")
async def get_price_update_job(job_id: str):
    job = await price_update_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "store_id": job.store_id,
        "file_name": job.file_name,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "fatal_error": job.fatal_error,
        "validation": {
            "valid_rows": job.total,
            "invalid_rows": len(job.validation_errors),
            "errors": [e.__dict__ for e in job.validation_errors],
        },
        "stats": _job_stats(job),
    }


@router.get("/jobs/{job_id}/logs")
async def get_price_update_logs(
    job_id: str,
    status: Literal["ALL", "SUCCESS", "ERROR", "WARNING", "SKIPPED"] = Query("ALL"),
    query: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
):
    job = await price_update_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    logs = job.logs
    if status != "ALL":
        logs = [l for l in logs if l.status == status]
    if query:
        q = query.strip().lower()
        logs = [l for l in logs if q in l.code.lower()]

    total = len(logs)
    start = (page - 1) * per_page
    end = start + per_page
    items = logs[start:end]
    return {
        "items": [i.__dict__ for i in items],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
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
