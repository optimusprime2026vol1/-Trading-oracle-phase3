"""
Average True Range (ATR).

Master spec reference: section 6 -- "ATR | Wilder true range, period 14"
-- and section 6.1 warm-up: "RSI(14) / ATR(14): minimum 100 bars".
"""

from __future__ import annotations

from typing import Sequence

from src.data.contracts import Bar

DEFAULT_ATR_PERIOD = 14
WARMUP_MIN_BARS = 100  # spec 6.1, applies to both RSI(14) and ATR(14)


def true_range(bar: Bar, prev_close: float | None) -> float:
    """TR = max(high-low, |high-prev_close|, |low-prev_close|). For the
    very first bar in a series (no previous close), TR is simply high-low."""
    if prev_close is None:
        return bar.high - bar.low
    return max(
        bar.high - bar.low,
        abs(bar.high - prev_close),
        abs(bar.low - prev_close),
    )


def atr(bars: Sequence[Bar], period: int = DEFAULT_ATR_PERIOD) -> list[float | None]:
    """Returns ATR(period) aligned index-for-index with `bars`.

    Wilder smoothing: seeded with the SMA of the first `period` true
    ranges, then ATR[i] = (ATR[i-1]*(period-1) + TR[i]) / period.

    Every index before `WARMUP_MIN_BARS` (100, spec 6.1) is None, even
    though a numeric ATR value is mathematically available much sooner --
    "Insufficient history triggers gate 3, not a degraded estimate."
    """
    n = len(bars)
    result: list[float | None] = [None] * n
    if n < period:
        return result

    trs: list[float] = []
    prev_close: float | None = None
    for bar in bars:
        trs.append(true_range(bar, prev_close))
        prev_close = bar.close

    atr_values: list[float | None] = [None] * n
    seed = sum(trs[:period]) / period
    atr_values[period - 1] = seed
    prev_atr = seed
    for i in range(period, n):
        prev_atr = (prev_atr * (period - 1) + trs[i]) / period
        atr_values[i] = prev_atr

    for i in range(WARMUP_MIN_BARS - 1, n):
        result[i] = atr_values[i]
    return result
