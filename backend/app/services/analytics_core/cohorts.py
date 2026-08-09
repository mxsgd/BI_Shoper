from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CohortsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_cohorts(
        self,
        store_id: int,
        months: int,
    ) -> dict:
        since = date.today() - timedelta(days=months * 31)
        rows = await self._fetch_cohorts(store_id, since)
        return self._serialize(rows)

    async def _fetch_cohorts(self, store_id: int, since: date):
        sql = text("""
            WITH cohorts AS (
                SELECT customer_id,
                        date_trunc('month', first_order_date)::date AS cohort_month
                FROM dim_customers
                WHERE store_id = :store_id
                    AND first_order_date IS NOT NULL
                    AND first_order_date::date >= :since
            ),
            cohort_sizes AS (
                SELECT cohort_month, COUNT(*) AS size
                FROM cohorts GROUP BY cohort_month
            ),
            activity AS (
                SELECT DISTINCT fo.customer_id,
                        date_trunc('month', fo.order_date)::date AS activity_month
                FROM fact_orders fo
                WHERE fo.store_id = :store_id AND fo.customer_id IS NOT NULL
            ),
            matrix AS (
                SELECT
                    c.cohort_month,
                    (EXTRACT(YEAR FROM a.activity_month) - EXTRACT(YEAR FROM c.cohort_month)) * 12
                    + EXTRACT(MONTH FROM a.activity_month) - EXTRACT(MONTH FROM c.cohort_month)
                    AS month_offset,
                    COUNT(DISTINCT a.customer_id) AS active
                FROM cohorts c
                JOIN activity a ON a.customer_id = c.customer_id
                                AND a.activity_month >= c.cohort_month
                GROUP BY c.cohort_month, month_offset
            )
            SELECT m.cohort_month, cs.size, m.month_offset, m.active
            FROM matrix m
            JOIN cohort_sizes cs ON cs.cohort_month = m.cohort_month
            ORDER BY m.cohort_month, m.month_offset
        """)
        return (await self.db.execute(sql, {"store_id": store_id, "since": since})).all()

    @staticmethod
    def _serialize(rows) -> dict:
        cohort_map: dict[str, dict] = {}
        for r in rows:
            key = str(r.cohort_month)
            if key not in cohort_map:
                cohort_map[key] = {"cohort_month": key, "size": r.size, "months": []}
            cohort_map[key]["months"].append({
                "month_offset": int(r.month_offset),
                "active": r.active,
                "retention_pct": round(r.active / r.size * 100, 1) if r.size else 0,
            })
        return {"cohorts": list(cohort_map.values())}
