from datetime import date, timedelta
from typing import List, Tuple


def get_next_thursday(today: date | None = None) -> date:
    if today is None:
        today = date.today()
    days_ahead = (3 - today.weekday()) % 7   # Thursday = weekday 3
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def get_period_for_pub_date(pub_date: date) -> Tuple[date, date, List[date]]:
    """
    7-calendar-day window ending the Wednesday before publication Thursday.
    Returns (period_start, period_end, trading_days_list).

    Verified against CV 3392 kỳ 14/5/2026:
      pub=14/5 → period 7/5–13/5, trading days [7,8,11,12,13]/5 (5 days).
    """
    period_end   = pub_date - timedelta(days=1)       # Wednesday
    period_start = period_end - timedelta(days=6)     # Thursday 7 days earlier

    trading_days: List[date] = []
    d = period_start
    while d <= period_end:
        if d.weekday() < 5:   # Mon–Fri
            trading_days.append(d)
        d += timedelta(days=1)

    return period_start, period_end, trading_days


def current_pub_date() -> date:
    return get_next_thursday()


def previous_pub_date(pub: date) -> date:
    return pub - timedelta(weeks=1)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5
