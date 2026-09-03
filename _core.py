"""
Internal shared math -- not part of the public indicator API.

Both ema.py and macd.py need the same recursive, SMA-seeded EMA
computation over a plain float series (macd.py runs it once on closes and
again on its own MACD-line series). Keeping one implementation here means
a formula fix only has to happen in one place.
"""

from __future__ import annotations

from typing import Sequence


def seeded_ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """Continuous EMA, alpha = 2/(period+1), seeded with the SMA of the
    first `period` values (spec section 6: EMA definition).

    Returns one value per input, `None` for indices before the seed point
    (index `period - 1`) since no EMA value exists yet there at all. This
    function does NOT apply the "trust" warm-up gate (spec 6.1's 3x
    multiplier) -- callers that need that distinction apply it themselves,
    because MACD's internal EMAs and the public `ema()` indicator gate
    warm-up differently (see macd.py and ema.py docstrings).
    """
    if period <= 0:
        raise ValueError("period must be positive")

    n = len(values)
    result: list[float | None] = [None] * n
    if n < period:
        return result

    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed

    prev = seed
    for i in range(period, n):
        prev = values[i] * alpha + prev * (1 - alpha)
        result[i] = prev
    return result
