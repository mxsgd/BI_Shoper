"""
Variant Code Generator — groups, products, option detection, code mapping, apply jobs.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import cast, Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session, get_db
from ..models.raw.raw_product_groups import RawProductGroup
from ..models.raw.raw_product_stocks import RawProductStock
from ..models.raw.raw_products import RawProduct
from ..models.store import Store
from ..services.shoper_auth import ensure_store_token
from ..services.shoper_client import ShoperClient, ShoperUnauthorizedError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/variant-codes", tags=["variant-codes"])

RATE_DELAY = 0.12
MAX_STOCKS_PER_REQUEST = 500

# ─── in-memory apply-codes job store ─────────────────────────────────────────
_apply_jobs: dict[str, dict] = {}

# ─── fabric name → code suffix auto-mapping ──────────────────────────────────
_FABRIC_MAP: dict[str, str] = {
    "sena": "AA", "alergik sena": "AA", "alergik": "AA",
    "aloe vera": "AV", "aloe vera lux": "AX",
    "anti-stress": "AS", "antistress": "AS",
    "coral": "CR", "crystal": "CS", "cotton lux": "CX",
    "hamelton": "HM", "impuls": "IM", "italia": "IT", "kaszmir": "KA",
    "len beż": "LNB", "len bez": "LNB",
    "len pomarańczowy": "LNP", "len pomar.": "LNP",
    "print": "PT", "royal": "RO",
    "silver black": "SB", "soya": "SO", "silver lux": "SX",
    "szmaragd": "SZ",
    "sen zdrowie natura": "SZN", "sen zdrowie natrua": "SZN", "sen zdrowie": "SZN",
    "tencel": "TE", "tencel caro": "T2KW",
    "talalay gold": "TGO", "talalay grey": "TGR", "tencel lux": "TX",
    "croko": "CRO", "cotton natural": "CN", "len super": "LNS",
    "nordic": "NO", "nordik": "NO", "midas": "MI",
    "salva": "SAL", "quattro": "QR", "standard": "ST", "ocean": "OC",
    "bawełna": "BW",
}


def _auto_suffix(name: str) -> str:
    """Auto-suggest a code suffix from an option value name."""
    clean = name.strip().replace(" ", "").lower()
    # size pattern: 6 digits
    if re.fullmatch(r"\d{6}", clean):
        return clean
    # size pattern: NNxNN
    m = re.fullmatch(r"(\d+)[x×xx](\d+)", clean, re.IGNORECASE)
    if m:
        return f"{int(m.group(1)):03d}{int(m.group(2)):03d}"
    # fabric map
    fabric = _FABRIC_MAP.get(name.strip().lower())
    if fabric:
        return fabric
    # fallback: initials
    parts = re.split(r"[\s/\-]+", name.strip())
    initials = "".join(p[0].upper() for p in parts if p)
    return initials[:5] or name[:4].upper()


def _is_size(name: str) -> bool:
    clean = name.strip().replace(" ", "")
    return bool(re.fullmatch(r"\d{6}", clean) or re.fullmatch(r"\d+[x×xX]\d+", clean))


# ─── helpers ──────────────────────────────────────────────────────────────────

def _trans_name(translations: dict | None) -> str:
    if not translations:
        return ""
    for lang_data in translations.values():
        if isinstance(lang_data, dict):
            name = (lang_data.get("name") or "").strip()
            if name:
                return name
    return ""


def _product_name(p: RawProduct) -> str:
    name = _trans_name(p.translations)
    return name or p.code or f"product_id={p.product_id}"


def _serialize_product(p: RawProduct) -> dict:
    return {
        "product_id": p.product_id,
        "code": p.code or "",
        "name": _product_name(p),
        "group_id": p.group_id,
    }


def _serialize_stock(s: RawProductStock) -> dict:
    return {
        "stock_id": s.stock_id,
        "code": s.code or "",
        "active": s.active,
        "extended": s.extended,
        "price": float(s.price) if s.price else 0.0,
    }


# ─── endpoints ────────────────────────────────────────────────────────────────

@router.get("/groups")
async def list_product_groups(
    store_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Return all product groups (zestawy wariantów) that have at least one product,
    sorted by product count descending. Used to populate the group picker.
    """
    counts_stmt = (
        select(RawProduct.group_id, func.count(RawProduct.product_id).label("cnt"))
        .where(RawProduct.store_id == store_id, RawProduct.group_id.isnot(None))
        .group_by(RawProduct.group_id)
    )
    count_rows = (await db.execute(counts_stmt)).all()
    count_map: dict[int, int] = {r.group_id: r.cnt for r in count_rows}
    if not count_map:
        return []

    group_ids = list(count_map.keys())
    groups_stmt = (
        select(RawProductGroup)
        .where(RawProductGroup.store_id == store_id, RawProductGroup.group_id.in_(group_ids))
        .order_by(RawProductGroup.group_id)
    )
    groups = (await db.execute(groups_stmt)).scalars().all()

    # Build id→name map from DB; for group IDs not yet synced, use fallback name
    known: dict[int, str] = {}
    for g in groups:
        name = g.name or _trans_name(g.translations) or f"Zestaw {g.group_id}"
        known[g.group_id] = name

    result = []
    for gid, cnt in count_map.items():
        result.append({
            "group_id": gid,
            "name": known.get(gid) or f"Zestaw wariantów {gid}",
            "product_count": cnt,
        })
    result.sort(key=lambda x: (-x["product_count"], x["name"]))
    return result


@router.get("/search-products")
async def search_products(
    store_id: int = Query(...),
    q: str = Query(""),
    group_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    List products optionally filtered by group_id (zestaw wariantów) and/or text query.
    Without any filter returns up to `limit` products sorted by code.
    """
    conditions = [RawProduct.store_id == store_id]
    if group_id is not None:
        conditions.append(RawProduct.group_id == group_id)
    if q.strip():
        ql = f"%{q.strip()}%"
        conditions.append(
            or_(
                RawProduct.code.ilike(ql),
                cast(RawProduct.translations, Text).ilike(ql),
            )
        )

    stmt = (
        select(RawProduct)
        .where(*conditions)
        .order_by(RawProduct.code)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize_product(p) for p in rows]


@router.get("/products/{product_id}/stocks")
async def get_product_stocks(
    product_id: int,
    store_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return all variant stocks (product-stocks) for a product from local DB."""
    stmt = (
        select(RawProductStock)
        .where(
            RawProductStock.store_id == store_id,
            RawProductStock.product_id == product_id,
        )
        .order_by(RawProductStock.code)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize_stock(s) for s in rows]


# ─── detect option groups for a product ──────────────────────────────────────

@router.get("/detect-options")
async def detect_options(
    product_id: int = Query(...),
    store_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch variant stocks for a product from Shoper, collect option group IDs + value IDs,
    resolve value names, and return groups with auto-suggested code suffixes.
    """
    store = (
        await db.execute(select(Store).where(Store.id == store_id, Store.is_active.is_(True)))
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(404, "Sklep nie znaleziony lub nieaktywny")

    try:
        token = await ensure_store_token(db, store)
    except Exception as exc:
        raise HTTPException(503, f"Błąd autoryzacji: {exc}") from exc

    client = ShoperClient(store.api_url, token)
    try:
        stocks: list[dict] = await client.get_filtered("/product-stocks", {"product_id": product_id})
    finally:
        await client.close()

    # Collect unique group_id → set of value_ids
    group_vids: dict[str, set[str]] = {}
    for s in stocks:
        opts = s.get("options") or {}
        if isinstance(opts, dict):
            for gid, vid in opts.items():
                group_vids.setdefault(str(gid), set()).add(str(vid))

    if not group_vids:
        return {"groups": [], "total_stocks": len(stocks)}

    # Resolve value names via /option-values/{id}
    all_vids = sorted({v for vs in group_vids.values() for v in vs}, key=int)
    val_names: dict[str, str] = {}
    client2 = ShoperClient(store.api_url, token)
    try:
        for vid in all_vids:
            try:
                d = await client2.get(f"/option-values/{vid}")
                if d:
                    n = (d.get("translations") or {}).get("pl_PL", {})
                    val_names[vid] = (n.get("value") or n.get("name") or "").strip()
            except Exception:
                pass
            await asyncio.sleep(0.05)
    finally:
        await client2.close()

    # Build result groups
    result: list[dict] = []
    for gid in sorted(group_vids.keys(), key=int):
        vids = group_vids[gid]
        values = []
        for vid in sorted(vids, key=lambda v: val_names.get(v, v).lower()):
            name = val_names.get(vid) or f"value_{vid}"
            values.append({
                "value_id": vid,
                "value_name": name,
                "suggested_suffix": _auto_suffix(name),
            })
        size_count = sum(1 for v in values if _is_size(v["value_name"]))
        role = "size" if size_count > len(values) / 2 else "fabric"
        result.append({"group_id": gid, "role": role, "values": values})

    return {"groups": result, "total_stocks": len(stocks)}


# ─── apply codes (background job) ────────────────────────────────────────────

class OptionValueMapping(BaseModel):
    value_id: str
    suffix: str


class OptionGroupConfig(BaseModel):
    group_id: str
    role: str = "other"
    values: list[OptionValueMapping]


class ApplyCodesRequest(BaseModel):
    store_id: int
    product_ids: list[int]
    option_groups: list[OptionGroupConfig]  # ordered: suffix order in code
    prices: dict[str, float] = {}           # variant_code -> price (from CSV)
    create_missing: bool = True             # POST if stock doesn't exist yet


@router.post("/apply-codes/start")
async def apply_codes_start(
    body: ApplyCodesRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.product_ids:
        raise HTTPException(400, "Brak wybranych produktów")
    if not body.option_groups:
        raise HTTPException(400, "Brak zdefiniowanych grup opcji")

    store = (
        await db.execute(select(Store).where(Store.id == body.store_id, Store.is_active.is_(True)))
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(404, "Sklep nie znaleziony lub nieaktywny")

    try:
        token = await ensure_store_token(db, store)
    except Exception as exc:
        raise HTTPException(503, f"Błąd autoryzacji: {exc}") from exc

    job_id = uuid.uuid4().hex[:10]
    _apply_jobs[job_id] = {
        "status": "running",
        "total": 0,
        "done": 0,
        "ok": 0,
        "skip": 0,
        "err": 0,
        "log": [],
    }

    asyncio.create_task(_run_apply_job(job_id, body, store.api_url, token))
    return {"job_id": job_id}


@router.get("/apply-codes/jobs/{job_id}")
async def get_apply_job(job_id: str):
    job = _apply_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job nie istnieje")
    return job


async def _run_apply_job(
    job_id: str,
    body: ApplyCodesRequest,
    api_url: str,
    token: str,
) -> None:
    job = _apply_jobs[job_id]

    # Build suffix lookup: value_id -> suffix
    suffix_map: dict[str, str] = {}
    for og in body.option_groups:
        for v in og.values:
            suffix_map[v.value_id] = v.suffix

    # Prices lookup: upper(code) -> price
    prices_upper: dict[str, float] = {k.upper(): v for k, v in body.prices.items()}

    client = ShoperClient(api_url, token)
    try:
        # Fetch product codes from DB  (needed to build variant codes)
        async with async_session() as db:
            prods = (
                await db.execute(
                    select(RawProduct.product_id, RawProduct.code)
                    .where(RawProduct.product_id.in_(body.product_ids))
                )
            ).all()
        prod_code_map: dict[int, str] = {r.product_id: (r.code or "") for r in prods}

        # Estimate total: products × combos per product (not exact, updated live)
        combos_per = 1
        for og in body.option_groups:
            combos_per *= max(len(og.values), 1)
        job["total"] = len(body.product_ids) * combos_per

        for pid in body.product_ids:
            base_code = prod_code_map.get(pid, f"product_{pid}")

            # Fetch current stocks from Shoper
            try:
                stocks: list[dict] = await client.get_filtered(
                    "/product-stocks", {"product_id": pid}
                )
            except Exception as exc:
                job["log"].append(f"ERR [{base_code}] fetch stocks: {exc}")
                job["err"] += combos_per
                job["done"] += combos_per
                continue

            # Build existing stock map: options_key -> stock (for PUT)
            # and existing_codes set (for dedup)
            existing_by_options: dict[str, dict] = {}
            existing_codes: set[str] = set()
            has_variants = False
            for s in stocks:
                opts = s.get("options")
                code = (s.get("code") or "").strip()
                if opts and isinstance(opts, dict):
                    has_variants = True
                    key = _options_key(opts, body.option_groups)
                    existing_by_options[key] = s
                if code:
                    existing_codes.add(code.upper())

            # Generate all combinations
            group_value_lists: list[list[OptionValueMapping]] = [og.values for og in body.option_groups]
            for combo in itertools.product(*group_value_lists):
                # Build options dict {group_id: value_id}
                options_dict: dict[str, str] = {og.group_id: v.value_id for og, v in zip(body.option_groups, combo)}
                key = _options_key(options_dict, body.option_groups)

                # Build code
                suffixes = [v.suffix for v in combo]
                variant_code = "-".join([base_code] + [s for s in suffixes if s])
                price = prices_upper.get(variant_code.upper(), 0.0)

                existing = existing_by_options.get(key)

                if existing:
                    existing_code = (existing.get("code") or "").strip()
                    if existing_code and existing_code.upper() == variant_code.upper():
                        job["log"].append(f"SKIP [{variant_code}] kod już ustawiony")
                        job["skip"] += 1
                    else:
                        payload: dict[str, Any] = {"code": variant_code}
                        if price > 0:
                            payload["price"] = price
                        try:
                            await asyncio.sleep(RATE_DELAY)
                            await client.put(f"/product-stocks/{existing['stock_id']}", payload)
                            job["log"].append(f"PUT [{variant_code}] OK (stock_id={existing['stock_id']})")
                            job["ok"] += 1
                        except Exception as exc:
                            job["log"].append(f"ERR PUT [{variant_code}]: {exc}")
                            job["err"] += 1
                elif body.create_missing:
                    payload = {
                        "product_id": pid,
                        "code": variant_code,
                        "price": price,
                        "stock": 0,
                        "active": True,
                        "extended": 1,
                        "options": {og.group_id: v.value_id for og, v in zip(body.option_groups, combo)},
                    }
                    try:
                        await asyncio.sleep(RATE_DELAY)
                        result = await client.post("/product-stocks", payload)
                        job["log"].append(f"POST [{variant_code}] OK (new stock_id={result})")
                        job["ok"] += 1
                    except Exception as exc:
                        job["log"].append(f"ERR POST [{variant_code}]: {exc}")
                        job["err"] += 1
                else:
                    job["log"].append(f"SKIP [{variant_code}] brak stocku, create_missing=false")
                    job["skip"] += 1

                job["done"] += 1

    except Exception as exc:
        job["log"].append(f"FATAL: {exc}")
        logger.exception("apply_codes job %s failed", job_id)
    finally:
        await client.close()
        job["status"] = "done"
        # Keep only last 500 log lines
        if len(job["log"]) > 500:
            job["log"] = job["log"][-500:]


def _options_key(options: dict, ordered_groups: list[OptionGroupConfig]) -> str:
    """Stable key for an options dict based on group order."""
    parts = []
    for og in ordered_groups:
        vid = str(options.get(og.group_id) or options.get(str(og.group_id)) or "")
        parts.append(f"{og.group_id}:{vid}")
    return "|".join(parts)


# ─── create stocks ────────────────────────────────────────────────────────────

class SegmentGroup(BaseModel):
    name: str
    values: list[str]


class ProductEntry(BaseModel):
    product_id: int
    code: str


class CreateStocksRequest(BaseModel):
    store_id: int
    products: list[ProductEntry]
    segments: list[SegmentGroup]
    default_price: float = 0.0
    skip_existing: bool = True


@router.post("/create-stocks")
async def create_stocks(
    body: CreateStocksRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate all code combinations from base product codes × segment groups
    and create missing product-stocks in Shoper.
    """
    if not body.products:
        raise HTTPException(400, "Brak wybranych produktów")
    for seg in body.segments:
        if not seg.values:
            raise HTTPException(400, f"Segment '{seg.name}' nie ma żadnych wartości")

    # Check total combinations first
    total = len(body.products) * _combo_count(body.segments)
    if total > MAX_STOCKS_PER_REQUEST:
        raise HTTPException(
            400,
            f"Za dużo kombinacji: {total}. Maksimum to {MAX_STOCKS_PER_REQUEST} na jedno wywołanie.",
        )

    # Get store
    store = (
        await db.execute(select(Store).where(Store.id == body.store_id, Store.is_active.is_(True)))
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(404, "Sklep nie znaleziony lub nieaktywny")

    try:
        token = await ensure_store_token(db, store)
    except Exception as exc:
        raise HTTPException(503, f"Błąd autoryzacji Shoper: {exc}") from exc

    # Load existing codes for dedup
    existing_codes: set[str] = set()
    if body.skip_existing:
        product_ids = [p.product_id for p in body.products]
        stmt = select(RawProductStock.code).where(
            RawProductStock.store_id == body.store_id,
            RawProductStock.product_id.in_(product_ids),
        )
        rows = (await db.execute(stmt)).scalars().all()
        existing_codes = {(c or "").strip().upper() for c in rows if c}

    combos = list(itertools.product(*[s.values for s in body.segments]))
    client = ShoperClient(store.api_url, token)

    results: list[dict] = []

    try:
        for prod in body.products:
            base_code = prod.code
            for combo in combos:
                code = "-".join([base_code] + list(combo))

                if body.skip_existing and code.strip().upper() in existing_codes:
                    results.append({"code": code, "status": "skipped", "message": "kod już istnieje"})
                    continue

                payload: dict = {
                    "product_id": prod.product_id,
                    "code": code,
                    "price": body.default_price,
                    "stock": 0,
                    "extended": True,
                    "active": True,
                }

                try:
                    await asyncio.sleep(RATE_DELAY)
                    resp = await client.post("/product-stocks", payload)
                    if resp is not None:
                        results.append({"code": code, "status": "created", "stock_id": resp})
                    else:
                        results.append({"code": code, "status": "error", "message": "Brak odpowiedzi API"})
                except ShoperUnauthorizedError as exc:
                    raise HTTPException(401, str(exc)) from exc
                except Exception as exc:
                    results.append({"code": code, "status": "error", "message": str(exc)})

    finally:
        await client.close()

    created = sum(1 for r in results if r["status"] == "created")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")

    return {
        "results": results,
        "summary": {"created": created, "skipped": skipped, "errors": errors, "total": len(results)},
    }


def _combo_count(segments: list[SegmentGroup]) -> int:
    count = 1
    for s in segments:
        count *= max(len(s.values), 1)
    return count
