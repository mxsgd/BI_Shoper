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
from ..services.sync_service import SyncService

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

def _trans_name(translations: dict | None, field: str = "name") -> str:
    if not translations:
        return ""
    for lang in ("pl_PL", "en_GB", "pl", "en"):
        lang_data = translations.get(lang)
        if isinstance(lang_data, dict):
            val = (lang_data.get(field) or "").strip()
            if val:
                return val
    for lang_data in translations.values():
        if isinstance(lang_data, dict):
            val = (lang_data.get(field) or "").strip()
            if val:
                return val
    return ""


def _group_display_name(g: RawProductGroup | None, group_id: int) -> str:
    if g is not None:
        if g.name and g.name.strip():
            return g.name.strip()
        from_trans = _trans_name(g.translations, "name")
        if from_trans:
            return from_trans
    return f"Zestaw wariantów {group_id}"


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

def _serialize_group_row(
    group_id: int,
    product_count: int,
    known: dict[int, RawProductGroup],
) -> dict:
    g = known.get(group_id)
    return {
        "group_id": group_id,
        "name": _group_display_name(g, group_id),
        "product_count": product_count,
    }


async def _group_counts(db: AsyncSession, store_id: int) -> dict[int, int]:
    count_rows = (
        await db.execute(
            select(RawProduct.group_id, func.count(RawProduct.product_id).label("cnt"))
            .where(RawProduct.store_id == store_id, RawProduct.group_id.isnot(None))
            .group_by(RawProduct.group_id)
        )
    ).all()
    return {r.group_id: r.cnt for r in count_rows}


async def _groups_by_id(db: AsyncSession, store_id: int, group_ids: list[int] | None = None) -> dict[int, RawProductGroup]:
    stmt = select(RawProductGroup).where(RawProductGroup.store_id == store_id)
    if group_ids is not None:
        if not group_ids:
            return {}
        stmt = stmt.where(RawProductGroup.group_id.in_(group_ids))
    groups = (await db.execute(stmt.order_by(RawProductGroup.group_id))).scalars().all()
    return {g.group_id: g for g in groups}


@router.get("/groups")
async def list_product_groups(
    store_id: int = Query(...),
    refresh: bool = Query(False, description="Pobierz nazwy zestawów z Shopera przed listowaniem"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return product groups (zestawy wariantów) with human-readable names.
    Sorted by product count descending.
    """
    if refresh:
        store = (
            await db.execute(select(Store).where(Store.id == store_id, Store.is_active.is_(True)))
        ).scalar_one_or_none()
        if store is None:
            raise HTTPException(404, "Sklep nie znaleziony lub nieaktywny")
        svc = SyncService(db, store)
        try:
            await ensure_store_token(db, store)
            await svc.sync_product_groups()
        except Exception as exc:
            raise HTTPException(503, f"Błąd synchronizacji zestawów: {exc}") from exc
        finally:
            await svc.close()

    count_map = await _group_counts(db, store_id)
    known = await _groups_by_id(db, store_id)

    all_ids = sorted(set(count_map.keys()) | set(known.keys()))
    if not all_ids:
        return []

    result = [
        _serialize_group_row(gid, count_map.get(gid, 0), known)
        for gid in all_ids
    ]
    result.sort(key=lambda x: (-x["product_count"], x["name"].lower()))
    return result


@router.post("/groups/{group_id}/sync")
async def sync_variant_group(
    group_id: int,
    store_id: int = Query(...),
    include_stocks: bool = Query(False, description="Sync stocks too (slow for large groups)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync one zestaw wariantów from Shoper: group metadata + products.
    Stocks are skipped by default — use include_stocks=true only when needed.
    """
    store = (
        await db.execute(select(Store).where(Store.id == store_id, Store.is_active.is_(True)))
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(404, "Sklep nie znaleziony lub nieaktywny")

    try:
        await ensure_store_token(db, store)
    except Exception as exc:
        raise HTTPException(503, f"Błąd autoryzacji: {exc}") from exc

    svc = SyncService(db, store)
    try:
        summary = await svc.sync_variant_group(group_id, include_stocks=include_stocks)
    except ShoperUnauthorizedError as exc:
        raise HTTPException(401, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Błąd synchronizacji zestawu: {exc}") from exc
    finally:
        await svc.close()

    count_map = await _group_counts(db, store_id)
    known = await _groups_by_id(db, store_id, [group_id])
    group = _serialize_group_row(
        group_id, count_map.get(group_id, 0), known
    )
    return {"group": group, **summary}


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

async def _fetch_option_value_pool(client: ShoperClient, gid: str) -> dict[str, str]:
    """Fetch ALL values defined in Shoper for one option group. Returns {value_id: value_name}."""
    try:
        # Shoper filters option-values by "option_id" (the group id), and each
        # item's own id is "ovalue_id" — not "option_group_id" / "id".
        raw_items: list[dict] = await client.get_filtered(
            "/option-values", {"option_id": int(gid)}
        )
    except Exception:
        raw_items = []

    pool: dict[str, str] = {}
    for item in raw_items:
        vid = str(item.get("ovalue_id") or "")
        if not vid:
            continue
        n = (item.get("translations") or {}).get("pl_PL", {})
        name = (n.get("value") or "").strip()
        pool[vid] = name or f"value_{vid}"
    return pool


def _build_value_entries(vids: set[str], pool: dict[str, str]) -> list[dict]:
    values = []
    for vid in sorted(vids, key=lambda v: pool.get(v, v).lower()):
        name = pool.get(vid) or f"value_{vid}"
        values.append({
            "value_id": vid,
            "value_name": name,
            "suggested_suffix": _auto_suffix(name),
        })
    return values


def _determine_role(values: list[dict]) -> str:
    if not values:
        return "fabric"
    size_count = sum(1 for v in values if _is_size(v["value_name"]))
    return "size" if size_count > len(values) / 2 else "fabric"


@router.get("/detect-options-multi")
async def detect_options_multi(
    product_ids: str = Query(..., description="Comma-separated product IDs"),
    store_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Detect option groups for multiple products.
    - Groups: intersection of groups present in ALL products (via existing stocks).
    - Values: intersection of value_ids actually used across ALL products' stocks
      (only values every product already has).
    - available_values: the full pool of values defined in Shoper for that group,
      for manually adding values not (yet) present in every product.
    """
    pids = [int(x) for x in product_ids.split(",") if x.strip().isdigit()]
    if not pids:
        raise HTTPException(400, "Brak product_ids")

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
    per_product: list[dict[str, set[str]]] = []
    total_stocks = 0

    try:
        for pid in pids:
            try:
                stocks: list[dict] = await client.get_filtered("/product-stocks", {"product_id": pid})
            except Exception:
                stocks = []
            total_stocks += len(stocks)
            group_vids: dict[str, set[str]] = {}
            for s in stocks:
                opts = s.get("options") or {}
                if isinstance(opts, dict):
                    for gid, vid in opts.items():
                        group_vids.setdefault(str(gid), set()).add(str(vid))
            if group_vids:
                per_product.append(group_vids)
            await asyncio.sleep(0.1)

        if not per_product:
            return {"groups": [], "total_stocks": total_stocks}

        # Intersection of group IDs across all products
        common_gids = set(per_product[0].keys())
        for gvids in per_product[1:]:
            common_gids &= set(gvids.keys())

        if not common_gids:
            return {"groups": [], "total_stocks": total_stocks}

        result: list[dict] = []
        for gid in sorted(common_gids, key=int):
            # Intersection of value_ids actually used, across all products, for this group
            common_vids = set(per_product[0].get(gid, set()))
            for gvids in per_product[1:]:
                common_vids &= gvids.get(gid, set())

            pool = await _fetch_option_value_pool(client, gid)
            # Names for the intersection may include values not in the pool (edge case) —
            # fall back to the id itself so nothing silently disappears.
            values = _build_value_entries(common_vids, pool)
            available_values = _build_value_entries(set(pool.keys()), pool)

            role = _determine_role(values or available_values)
            result.append({
                "group_id": gid,
                "role": role,
                "values": values,
                "available_values": available_values,
            })
            await asyncio.sleep(0.05)

    finally:
        await client.close()

    return {"groups": result, "total_stocks": total_stocks}


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

        # Collect unique group_id → set of value_ids
        group_vids: dict[str, set[str]] = {}
        for s in stocks:
            opts = s.get("options") or {}
            if isinstance(opts, dict):
                for gid, vid in opts.items():
                    group_vids.setdefault(str(gid), set()).add(str(vid))

        if not group_vids:
            return {"groups": [], "total_stocks": len(stocks)}

        result: list[dict] = []
        for gid in sorted(group_vids.keys(), key=int):
            pool = await _fetch_option_value_pool(client, gid)
            values = _build_value_entries(group_vids[gid], pool)
            available_values = _build_value_entries(set(pool.keys()), pool)
            role = _determine_role(values or available_values)
            result.append({
                "group_id": gid,
                "role": role,
                "values": values,
                "available_values": available_values,
            })
            await asyncio.sleep(0.05)
    finally:
        await client.close()

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
    supplement_mode: bool = False           # fix ALL existing stocks (incl. extra-group ones)


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
    prices_upper: dict[str, float] = {k.upper(): v for k, v in body.prices.items()}

    client = ShoperClient(api_url, token)
    try:
        async with async_session() as db:
            prods = (
                await db.execute(
                    select(RawProduct.product_id, RawProduct.code)
                    .where(RawProduct.product_id.in_(body.product_ids))
                )
            ).all()
        prod_code_map: dict[int, str] = {r.product_id: (r.code or "") for r in prods}

        if body.supplement_mode:
            await _run_supplement(job, body, client, prod_code_map, prices_upper)
        else:
            await _run_standard(job, body, client, prod_code_map, prices_upper)

    except Exception as exc:
        job["log"].append(f"FATAL: {exc}")
        logger.exception("apply_codes job %s failed", job_id)
    finally:
        await client.close()
        job["status"] = "done"
        if len(job["log"]) > 500:
            job["log"] = job["log"][-500:]


async def _run_standard(
    job: dict,
    body: ApplyCodesRequest,
    client: "ShoperClient",
    prod_code_map: dict[int, str],
    prices_upper: dict[str, float],
) -> None:
    """Standard mode: iterate panel combos, PUT existing stocks, POST missing ones."""
    combos_per = 1
    for og in body.option_groups:
        combos_per *= max(len(og.values), 1)
    job["total"] = len(body.product_ids) * combos_per

    for pid in body.product_ids:
        base_code = prod_code_map.get(pid, f"product_{pid}")

        try:
            stocks: list[dict] = await client.get_filtered("/product-stocks", {"product_id": pid})
        except Exception as exc:
            job["log"].append(f"ERR [{base_code}] fetch stocks: {exc}")
            job["err"] += combos_per
            job["done"] += combos_per
            continue

        existing_by_options: dict[str, dict] = {}
        for s in stocks:
            opts = s.get("options")
            if opts and isinstance(opts, dict):
                key = _options_key(opts, body.option_groups)
                existing_by_options[key] = s

        group_value_lists: list[list[OptionValueMapping]] = [og.values for og in body.option_groups]
        for combo in itertools.product(*group_value_lists):
            options_dict: dict[str, str] = {og.group_id: v.value_id for og, v in zip(body.option_groups, combo)}
            key = _options_key(options_dict, body.option_groups)
            suffixes = [v.suffix for v in combo]
            variant_code = "-".join([base_code] + [sf for sf in suffixes if sf])
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
                    "options": options_dict,
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


async def _run_supplement(
    job: dict,
    body: ApplyCodesRequest,
    client: "ShoperClient",
    prod_code_map: dict[int, str],
    prices_upper: dict[str, float],
) -> None:
    """Supplement mode: fix codes on ALL existing stocks (including extra-group ones).
    For panel combos with no existing stock: POST new stock.
    For stocks that have extra groups (groups not in panel): fix code using
    panel suffixes + auto-suggested suffixes for extra group values, never POST new.
    """
    panel_gids = {og.group_id for og in body.option_groups}
    panel_suffix_map: dict[str, dict[str, str]] = {
        og.group_id: {v.value_id: v.suffix for v in og.values}
        for og in body.option_groups
    }
    val_names_cache: dict[str, str] = {}

    async def _resolve_value_name(vid: str) -> str:
        if vid in val_names_cache:
            return val_names_cache[vid]
        try:
            d = await client.get(f"/option-values/{vid}")
            if d:
                n = (d.get("translations") or {}).get("pl_PL", {})
                name = (n.get("value") or n.get("name") or "").strip()
                val_names_cache[vid] = name
                return name
        except Exception:
            pass
        val_names_cache[vid] = ""
        return ""

    for pid in body.product_ids:
        base_code = prod_code_map.get(pid, f"product_{pid}")

        try:
            stocks: list[dict] = await client.get_filtered("/product-stocks", {"product_id": pid})
        except Exception as exc:
            job["log"].append(f"ERR [{base_code}] fetch stocks: {exc}")
            job["err"] += 1
            job["done"] += 1
            continue

        job["total"] += len(stocks)

        # Track which panel combos already have a stock (for POST missing logic)
        seen_panel_keys: set[str] = set()

        for stock in stocks:
            opts = stock.get("options") or {}
            if not isinstance(opts, dict):
                job["done"] += 1
                continue

            str_opts = {str(gid): str(vid) for gid, vid in opts.items()}
            panel_opts = {gid: vid for gid, vid in str_opts.items() if gid in panel_gids}
            extra_opts = {gid: vid for gid, vid in str_opts.items() if gid not in panel_gids}

            panel_key = _options_key(panel_opts, body.option_groups)
            seen_panel_keys.add(panel_key)

            # Build expected code: panel suffixes in configured order, then extra auto-suffixes
            code_parts = [base_code]
            for og in body.option_groups:
                vid = panel_opts.get(og.group_id, "")
                suffix = panel_suffix_map[og.group_id].get(vid, "")
                if suffix:
                    code_parts.append(suffix)

            for _gid, vid in sorted(extra_opts.items()):
                await asyncio.sleep(0.05)
                name = await _resolve_value_name(vid)
                suffix = _auto_suffix(name) if name else vid[:4].upper()
                if suffix:
                    code_parts.append(suffix)

            expected_code = "-".join(code_parts)
            existing_code = (stock.get("code") or "").strip()
            price = prices_upper.get(expected_code.upper(), 0.0)

            if existing_code and existing_code.upper() == expected_code.upper():
                job["log"].append(f"SKIP [{expected_code}] kod już ustawiony")
                job["skip"] += 1
            else:
                payload: dict[str, Any] = {"code": expected_code}
                if price > 0:
                    payload["price"] = price
                try:
                    await asyncio.sleep(RATE_DELAY)
                    await client.put(f"/product-stocks/{stock['stock_id']}", payload)
                    job["log"].append(f"PUT [{expected_code}] OK (stock_id={stock['stock_id']})")
                    job["ok"] += 1
                except Exception as exc:
                    job["log"].append(f"ERR PUT [{expected_code}]: {exc}")
                    job["err"] += 1

            job["done"] += 1

        # POST missing panel combos (only stocks with NO extra groups)
        if body.create_missing:
            group_value_lists: list[list[OptionValueMapping]] = [og.values for og in body.option_groups]
            for combo in itertools.product(*group_value_lists):
                options_dict: dict[str, str] = {og.group_id: v.value_id for og, v in zip(body.option_groups, combo)}
                panel_key = _options_key(options_dict, body.option_groups)
                if panel_key in seen_panel_keys:
                    continue
                suffixes = [v.suffix for v in combo]
                variant_code = "-".join([base_code] + [sf for sf in suffixes if sf])
                price = prices_upper.get(variant_code.upper(), 0.0)
                payload = {
                    "product_id": pid,
                    "code": variant_code,
                    "price": price,
                    "stock": 0,
                    "active": True,
                    "extended": 1,
                    "options": options_dict,
                }
                try:
                    await asyncio.sleep(RATE_DELAY)
                    result = await client.post("/product-stocks", payload)
                    job["log"].append(f"POST [{variant_code}] OK (nowy)")
                    job["ok"] += 1
                except Exception as exc:
                    job["log"].append(f"ERR POST [{variant_code}]: {exc}")
                    job["err"] += 1
                job["done"] += 1
                job["total"] += 1


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
