from datetime import date, timedelta
from typing import Literal


class FocusDateOutOfPeriodError(ValueError):
    pass


def period_bounds(period_days: int) -> tuple[date, date, date, date]:
    """Return (cur_start, cur_end, prev_start, prev_end) for current + previous period."""
    today = date.today()
    cur_end = today
    cur_start = today - timedelta(days=period_days - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)
    return cur_start, cur_end, prev_start, prev_end


def delta_pct(cur_val, prev_val) -> float | None:
    if not prev_val:
        return None
    return round((float(cur_val) - float(prev_val)) / float(prev_val) * 100, 1)


def date_bucket_series_sql(group_by: Literal["day", "week", "month"]) -> str:
    """SQL fragment: FROM ... AS b(bucket) producing one row per bucket in the period.

    Use CAST(:x AS type), not :x::type — SQLAlchemy treats ':' as bind syntax and breaks on '::'.
    """
    if group_by == "day":
        return (
            "generate_series(CAST(:since AS date), CAST(:today AS date), interval '1 day') "
            "AS b(bucket)"
        )
    if group_by == "week":
        return (
            "generate_series("
            "date_trunc('week', CAST(:since AS timestamp))::date, "
            "date_trunc('week', CAST(:today AS timestamp))::date, "
            "interval '1 week'"
            ") AS b(bucket)"
        )
    return (
        "generate_series("
        "date_trunc('month', CAST(:since AS date))::date, "
        "date_trunc('month', CAST(:today AS date))::date, "
        "interval '1 month'"
        ") AS b(bucket)"
    )
