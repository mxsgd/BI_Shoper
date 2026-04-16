import asyncio
from dotenv import load_dotenv
load_dotenv()
from app.database import async_session
from sqlalchemy import text

async def main():
    async with async_session() as db:
        for t in ["fact_orders", "fact_order_items", "raw_orders", "raw_order_items"]:
            r = (await db.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
            print(f"{t}: {r} rows")

        r = (await db.execute(text(
            "SELECT MIN(order_date), MAX(order_date) FROM fact_orders WHERE store_id = 1"
        ))).one()
        print(f"\nfact_orders store_id=1: {r[0]} .. {r[1]}")

asyncio.run(main())
