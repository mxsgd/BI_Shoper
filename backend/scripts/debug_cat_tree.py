"""Debug: see what /categories-tree returns from the Shoper API."""
import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from app.database import async_session
from app.models.store import Store
from app.services.shoper_client import ShoperClient
from sqlalchemy import select


async def main():
    async with async_session() as db:
        store = (await db.execute(select(Store).where(Store.is_active.is_(True)).limit(1))).scalar_one()
        client = ShoperClient(store.api_url, store.api_token)

        # Try the raw list endpoint
        try:
            resp = await client.client.get(
                f"{client.base_url}/categories-tree",
                headers=client._auth_headers(),
            )
            data = resp.json()
            print(f"Raw /categories-tree response type: {type(data)}")
            print(f"Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            print(f"First 2000 chars: {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}")
        except Exception as e:
            print(f"Error: {e}")

        await client.close()


asyncio.run(main())
