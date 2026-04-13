"""Verify newly synced reference data."""
import sys, io, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.database import async_session
from sqlalchemy import text


async def check():
    async with async_session() as db:
        # Check categories tree data stored as technical JSON key in translations
        r = await db.execute(text(
            "SELECT COUNT(*) "
            "FROM raw_categories "
            "WHERE translations IS NOT NULL "
            "AND translations::jsonb ? '_parent_id'"
        ))
        with_parent = r.scalar() or 0
        r = await db.execute(text("SELECT COUNT(*) FROM raw_categories"))
        total_categories = r.scalar() or 0
        print(f"raw_categories with _parent_id: {with_parent}/{total_categories}")

        r = await db.execute(text(
            "SELECT category_id, translations->>'_parent_id' AS parent_id "
            "FROM raw_categories "
            "WHERE translations::jsonb ? '_parent_id' "
            "ORDER BY category_id LIMIT 10"
        ))
        print("raw_categories parent links (sample):")
        for row in r.fetchall():
            print(f"  cat_id={row[0]}, parent_id={row[1]}")

        # Check raw taxes
        r = await db.execute(text("SELECT tax_id, value, name, tax_class FROM raw_taxes ORDER BY tax_id"))
        print(f"\nraw_taxes:")
        for row in r.fetchall():
            print(f"  id={row[0]}, value={row[1]}%, name={row[2]}, class={row[3]}")

        # Check currencies
        r = await db.execute(text("SELECT currency_id, name, rate, is_default FROM raw_currencies ORDER BY currency_id"))
        print(f"\nraw_currencies:")
        for row in r.fetchall():
            print(f"  id={row[0]}, name={row[1]}, rate={row[2]}, default={row[3]}")

        # Check user_groups
        r = await db.execute(text("SELECT group_id, name, discount, price_level FROM raw_user_groups ORDER BY group_id"))
        print(f"\nraw_user_groups:")
        for row in r.fetchall():
            print(f"  id={row[0]}, name={row[1]}, discount={row[2]}%, price_level={row[3]}")

        # Check parcels sample
        r = await db.execute(text("SELECT parcel_id, order_id, shipping_code, sent, send_date FROM raw_parcels LIMIT 5"))
        print(f"\nraw_parcels (sample):")
        for row in r.fetchall():
            print(f"  parcel_id={row[0]}, order_id={row[1]}, tracking={row[2]}, sent={row[3]}, send_date={row[4]}")

        # Check brand coverage
        r = await db.execute(text(
            "SELECT "
            "  COUNT(*) as total, "
            "  COUNT(brand) as with_brand, "
            "  ROUND(COUNT(brand) * 100.0 / COUNT(*), 1) as pct "
            "FROM dim_products"
        ))
        row = r.fetchone()
        print(f"\ndim_products brand coverage: {row[1]}/{row[0]} = {row[2]}%")

        # Check net_value correctness sample
        r = await db.execute(text(
            "SELECT order_id, gross_value, net_value, tax_value, margin_value "
            "FROM fact_orders WHERE gross_value > 0 ORDER BY order_id LIMIT 5"
        ))
        print(f"\nfact_orders financials (sample):")
        for row in r.fetchall():
            print(f"  order #{row[0]}: gross={row[1]}, net={row[2]}, tax={row[3]}, margin={row[4]}")


asyncio.run(check())
