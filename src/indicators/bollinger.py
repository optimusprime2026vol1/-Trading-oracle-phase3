"""
Bollinger Bands.

Master spec reference: section 6 -- "Bollinger | SMA 20, 2 standard
deviations, population sigma."

Spec 6.1 does not list an explicit warm-up multiplier for Bollinger (only
EMA, RSI, ATR, and EMA200 get one). Unlike those, Bollinger's middle band
is a plain SMA and its bands use the population standard deviation of
exactly the current window -- there is no recursive seeding to "settle"
the way EMA/Wilder-smoothed values do, so the first value computable
(at `period` bars) is already exact, not an approximation. Warm-up here is
therefore just `period` bars, not `3 * period`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.data.contracts import Bar

DEFAULT_PERIOD = 20
DEFAULT_NUM_STD = 2.0


@dataclass(frozen=True)
class BollingerResult:
    middle: list[float | None]
    upper: list[float | None]
    lower: list[float | None]


def bollinger(
    bars: Sequence[Bar], period: int = DEFAULT_PERIOD, num_std: float = DEFAULT_NUM_STD
) -> BollingerResult:
    n = len(bars)
    middle: list[float | None] = [None] * n
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n

    closes = [b.close for b in bars]
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period  # population, not sample
        std = variance**0.5
        middle[i] = mean
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std

    return BollingerResult(middle=middle, upper=upper, lower=lower)
