"""
Exponential Moving Average (EMA).

Master spec reference: section 6 -- "EMA | Standard exponential, alpha =
2/(n+1), seeded with SMA of first n bars" -- and section 6.1 warm-up:
"EMA(n): minimum 3n bars before the value is trusted" plus, for the
specific case used elsewhere in the system, "EMA200 on 5-minute: minimum
600 bars of same-timeframe history" (600 = 3 x 200, so it's the same rule
applied to n=200).
"""

from __future__ import annotations

from typing import Callable, Sequence

from src.data.contracts import Bar
from src.indicators._core import seeded_ema_series


def ema(
    bars: Sequence[Bar],
    period: int,
    *,
    price_fn: Callable[[Bar], float] = lambda b: b.close,
) -> list[float | None]:
    """Returns EMA(period) aligned index-for-index with `bars`.

    `bars` must already be ascending, completed candles only (spec 3.3,
    closed-bar rule -- enforced by the caller, not here). Every index
    before `3*period - 1` is None regardless of whether a numeric EMA
    value could be computed earlier -- spec 6.1 requires 3n bars before a
    value is *trusted*, and spec 6.2 forbids returning "a partial value"
    in the meantime.
    """
    closes = [price_fn(b) for b in bars]
    raw = seeded_ema_series(closes, period)

    warmup_index = 3 * period - 1  # spec 6.1
    result: list[float | None] = [None] * len(bars)
    for i in range(warmup_index, len(bars)):
        result[i] = raw[i]
    return result
