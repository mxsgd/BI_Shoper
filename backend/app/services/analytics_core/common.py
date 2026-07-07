from datetime import date, timedelta


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
