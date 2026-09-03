"""
Volume-Weighted Average Price (VWAP).

Master spec reference: section 6 -- "VWAP | Session-anchored, resets at
09:15, typical price = (H+L+C)/3, cumulative Sum(TP*Vol)/Sum(Vol)" -- and
section 6.1 warm-up: "VWAP: minimum 5 completed bars in the current
session."
"""

from __future__ import annotations

from typing import Sequence

from src.data.contracts import Bar

WARMUP_MIN_SESSION_BARS = 5  # spec 6.1


def vwap(bars: Sequence[Bar]) -> list[float | None]:
    """Returns session-anchored VWAP aligned index-for-index with `bars`.

    A new session is detected whenever `bar_open_time_ist.date()` changes
    from the previous bar -- this matches "resets at 09:15" since a fresh
    trading day's first bar opens at (or after) that time. `bars` may
    therefore span multiple sessions; VWAP resets its cumulative sums at
    each session boundary rather than requiring the caller to pre-split
    by day.
    """
    n = len(bars)
    result: list[float | None] = [None] * n

    cum_tp_vol = 0.0
    cum_vol = 0.0
    session_bar_count = 0
    prev_date = None

    for i, bar in enumerate(bars):
        bar_date = bar.bar_open_time_ist.date()
        if bar_date != prev_date:
            cum_tp_vol = 0.0
            cum_vol = 0.0
            session_bar_count = 0
            prev_date = bar_date

        typical_price = (bar.high + bar.low + bar.close) / 3.0
        cum_tp_vol += typical_price * bar.volume
        cum_vol += bar.volume
        session_bar_count += 1

        if session_bar_count >= WARMUP_MIN_SESSION_BARS and cum_vol > 0:
            result[i] = cum_tp_vol / cum_vol

    return result
