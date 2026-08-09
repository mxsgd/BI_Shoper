import csv
import io
import re
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..services.price_update import price_update_jobs

router = APIRouter(prefix="/api/price-update", tags=["price-update"])

_ALLOWED_UPLOAD_SUFFIXES = (".csv", ".txt", ".text", ".xlsx", ".sql")


def _is_allowed_price_file(filename: str | None) -> bool:
    if not filename:
        return False
    return filename.lower().endswith(_ALLOWED_UPLOAD_SUFFIXES)


def _split_sql_values(raw: str) -> list[str]:
    """Rozbija VALUES clause na pojedyncze wartości z obsługą cytatów."""
    vals: list[str] = []
    current: list[str] = []
    in_quote = False
    for ch in raw:
        if ch == "'" and not in_quote:
            in_quote = True
        elif ch == "'" and in_quote:
            in_quote = False
        elif ch == "," and not in_quote:
            vals.append("".join(current).strip())
            current = []
            continue
        else:
            current.append(ch)
    if current:
        vals.append("".join(current).strip())
    return vals


def _looks_like_sql(text: str) -> bool:
    sample = text[:4096].lower().lstrip()
    markers = ("insert into", "create table", "-- phpmyadmin", "-- mysql dump", "-- mariadb dump", "set names", "set sql_mode")
    return any(sample.startswith(m) or f"\n{m}" in sample for m in markers)


def _sql_to_csv_bytes(sql_text: str, csv_delimiter: str = ";") -> bytes:
    """Konwertuje MySQL/MariaDB INSERT dump na CSV (code, price).

    Obsługuje:
    - INSERT INTO `table` VALUES (v0, v1, v2, ...)  → code=v[0], price=v[2]
    - INSERT INTO `table` (`col1`,`col2`,...) VALUES (...)  → szuka kolumn code/price po nazwie
    """
    # Szukamy opcjonalnej listy kolumn z pierwszego INSERT
    named_re = re.compile(
        r"INSERT\s+INTO\s+`?\w+`?\s*\(([^)]+)\)\s+VALUES", re.IGNORECASE
    )
    m = named_re.search(sql_text)
    col_names: list[str] = []
    if m:
        col_names = [c.strip().strip("`'\"").lower() for c in m.group(1).split(",")]

    code_idx = 0
    price_idx = 2
    if col_names:
        for i, name in enumerate(col_names):
            if name in ("code", "kod", "symbol", "sku"):
                code_idx = i
            if name in ("price", "cena", "price_base", "wartosc", "wartość"):
                price_idx = i

    # Wyciągamy wszystkie bloki VALUES (...)
    values_block_re = re.compile(r"VALUES\s*\(([^)]+)\)", re.IGNORECASE)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=csv_delimiter)
    writer.writerow(["code", "price"])

    for vm in values_block_re.finditer(sql_text):
        vals = _split_sql_values(vm.group(1))
        if len(vals) <= max(code_idx, price_idx):
            continue
        code = vals[code_idx].strip()
        price = vals[price_idx].strip()
        # pomijamy puste kody i placeholder '---'/'NULL'
        if not code or code.upper() in ("---", "NULL", ""):
            continue
        writer.writerow([code, price])

    return output.getvalue().encode("utf-8")


_REQUIRED_XLSX_COLS = {"code", "price"}


def _xlsx_to_csv_bytes(raw: bytes, csv_delimiter: str = ";") -> bytes:
    """Konwertuje XLSX na CSV.

    Przetwarza TYLKO arkusze, których nagłówek (wiersz 1) zawiera kolumny 'code' i 'price'.
    Arkusze pomocnicze / dokumentacyjne bez tych kolumn są pomijane.
    Cross-sheet: ostatni arkusz wygrywa (last_wins) dla tego samego kodu.
    """
    try:
        import openpyxl  # type: ignore
    except ImportError as exc:
        raise ValueError("Brak pakietu openpyxl — zainstaluj: pip install openpyxl") from exc

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)

    def _cell(c) -> str:
        if c is None:
            return ""
        if isinstance(c, float) and c == int(c):
            return str(int(c))
        return str(c).strip()

    canonical_header: list[str] = []
    canonical_code_idx = 0
    rows_by_code: dict[str, list[str]] = {}

    for sheet in wb.worksheets:
        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            continue
        sheet_header = [_cell(c).lower() for c in raw_rows[0]]
        # Pomijaj arkusze bez wymaganych kolumn
        if not _REQUIRED_XLSX_COLS.issubset(set(sheet_header)):
            continue
        # Pierwsza prawidłowa karta ustala nagłówek kanoniki
        if not canonical_header:
            canonical_header = sheet_header
            canonical_code_idx = sheet_header.index("code")
        for raw_row in raw_rows[1:]:
            row = [_cell(c) for c in raw_row]
            while len(row) < len(canonical_header):
                row.append("")
            code_val = row[canonical_code_idx].strip() if canonical_code_idx < len(row) else ""
            if not code_val:
                rows_by_code[f"__empty_{len(rows_by_code)}"] = row
            else:
                rows_by_code[code_val] = row

    wb.close()

    if not canonical_header:
        raise ValueError(
            "Żaden arkusz w pliku XLSX nie zawiera wymaganych kolumn 'code' i 'price' w wierszu 1."
        )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=csv_delimiter)
    writer.writerow(canonical_header)
    for row in rows_by_code.values():
        writer.writerow(row)

    return output.getvalue().encode("utf-8")


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
        "disable_extra_variants": job.disable_extra_variants,
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
    disable_extra_variants: bool = Query(True),
):
    if not _is_allowed_price_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Supported file types: .csv, .txt, .xlsx, .sql",
        )
    content = await file.read()
    fname = file.filename or ""
    delim_char = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}.get(csv_delimiter, ";")
    if fname.lower().endswith(".xlsx"):
        try:
            content = _xlsx_to_csv_bytes(content, csv_delimiter=delim_char)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        # Auto-detect SQL dump (po rozszerzeniu lub treści)
        text_preview = content[:4096].decode("utf-8-sig", errors="replace")
        if fname.lower().endswith(".sql") or _looks_like_sql(text_preview):
            full_text = content.decode("utf-8-sig", errors="replace")
            content = _sql_to_csv_bytes(full_text, csv_delimiter=delim_char)
    try:
        job = await price_update_jobs.create_job(
            store_id=store_id,
            file_name=file.filename,
            csv_bytes=content,
            duplicate_mode=duplicate_mode,
            target_mode=target_mode,
            csv_delimiter=csv_delimiter,
            disable_extra_variants=disable_extra_variants,
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


@router.get("/jobs/latest")
async def get_latest_price_update_job(store_id: int = Query(...)):
    """Ostatni job sklepu (dowolny status) — przywracanie po restarcie backendu."""
    job = await price_update_jobs.get_latest_job(store_id)
    if job is None:
        return {"job": None}
    return {"job": _job_response(job)}


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


@router.post("/jobs/{job_id}/cancel")
async def cancel_price_update_job(job_id: str):
    job = await price_update_jobs.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job.job_id, "status": job.status, "cancel_requested": job.cancel_requested}


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

    items, total, pages, logs_dropped = await price_update_jobs.get_logs(
        job_id,
        status=status,
        query=query,
        page=page,
        per_page=per_page,
        tail=tail,
    )

    return {
        "items": [i.__dict__ for i in items],
        "page": page if tail is None else 1,
        "per_page": per_page if tail is None else max(len(items), 1),
        "total": total,
        "pages": pages,
        "logs_dropped": logs_dropped,
        "logs_in_memory": len(job.logs) if hasattr(job, "logs") else 0,
    }


@router.get("/jobs/{job_id}/logs/export.csv")
async def export_price_update_logs(job_id: str):
    job = await price_update_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    from ..services import price_update_persistence as persist

    async def generate():
        header = io.StringIO()
        writer = csv.writer(header)
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
        yield header.getvalue().encode("utf-8")

        db_has_logs = False
        async for entry in persist.iter_all_logs(job_id):
            db_has_logs = True
            row_buf = io.StringIO()
            writer = csv.writer(row_buf)
            writer.writerow(
                [
                    entry.timestamp,
                    entry.job_id,
                    entry.row_number,
                    entry.code,
                    "" if entry.old_price is None else f"{entry.old_price:.2f}",
                    "" if entry.new_price is None else f"{entry.new_price:.2f}",
                    entry.status,
                    entry.message,
                    entry.http_status or "",
                    entry.request_id or "",
                    entry.comment or "",
                ]
            )
            yield row_buf.getvalue().encode("utf-8")

        if not db_has_logs:
            for l in job.logs:
                row_buf = io.StringIO()
                writer = csv.writer(row_buf)
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
                yield row_buf.getvalue().encode("utf-8")

    headers = {"Content-Disposition": f'attachment; filename="{job_id}_logs.csv"'}
    return StreamingResponse(generate(), media_type="text/csv; charset=utf-8", headers=headers)
