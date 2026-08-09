from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RFM_SEGMENTS = {
    "Mistrzowie": lambda r, f, _m: r >= 4 and f >= 4,
    "Lojalni": lambda r, f, _m: r >= 3 and f >= 3 and not (r >= 4 and f >= 4),
    "Nowi klienci": lambda r, f, _m: r >= 4 and f <= 2,
    "Zagrożeni": lambda r, f, _m: r <= 2 and f >= 3,
    "Utraceni": lambda r, f, _m: r <= 2 and f <= 2,
    "Inni": lambda _r, _f, _m: True,
}


class RfmService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_rfm(self, store_id: int) -> dict:
        rows = await self._fetch_rfm_rows(store_id)
        return self._serialize(rows)

    async def _fetch_rfm_rows(self, store_id: int):
        sql = text("""
            WITH rfm AS (
                SELECT
                    customer_id,
                    EXTRACT(DAY FROM NOW() - last_order_date)::int AS recency_days,
                    total_orders   AS frequency,
                    total_revenue  AS monetary,
                    NTILE(5) OVER (ORDER BY last_order_date ASC)  AS r,
                    NTILE(5) OVER (ORDER BY total_orders)         AS f,
                    NTILE(5) OVER (ORDER BY total_revenue)        AS m
                FROM dim_customers
                WHERE store_id = :store_id AND total_orders > 0
            )
            SELECT customer_id, recency_days, frequency, monetary, r, f, m
            FROM rfm
        """)
        return (await self.db.execute(sql, {"store_id": store_id})).all()

    @staticmethod
    def _serialize(rows) -> dict:
        if not rows:
            return {"segments": [], "distribution": {}, "summary": {}}

        segments: dict[str, list] = defaultdict(list)
        for row in rows:
            for name, test in RFM_SEGMENTS.items():
                if test(row.r, row.f, row.m):
                    segments[name].append(row)
                    break

        segment_list = []
        for name, members in segments.items():
            if not members:
                continue
            segment_list.append({
                "name": name,
                "count": len(members),
                "avg_revenue": round(sum(float(m.monetary) for m in members) / len(members), 2),
                "avg_orders": round(sum(m.frequency for m in members) / len(members), 1),
                "avg_recency_days": round(sum(m.recency_days for m in members) / len(members)),
            })

        dist: dict[str, int] = defaultdict(int)
        for row in rows:
            dist[f"{row.r}{row.f}{row.m}"] += 1

        total_rev = sum(float(r.monetary) for r in rows)
        return {
            "segments": segment_list,
            "distribution": dict(dist),
            "summary": {
                "total_customers": len(rows),
                "avg_clv": round(total_rev / len(rows), 2),
                "total_revenue": round(total_rev, 2),
            },
        }
