"""
Relative Strength Index (RSI).

Master spec reference: section 6 -- "RSI | Wilder smoothing, period 14"
-- and section 6.1 warm-up: "RSI(14) / ATR(14): minimum 100 bars".
"""

from __future__ import annotations

from typing import Sequence

from src.data.contracts import Bar

DEFAULT_RSI_PERIOD = 14
WARMUP_MIN_BARS = 100  # spec 6.1


def rsi(bars: Sequence[Bar], period: int = DEFAULT_RSI_PERIOD) -> list[float | None]:
    """Returns RSI(period) aligned index-for-index with `bars`.

    Wilder smoothing on gains/losses: the first average gain/loss is a
    simple mean of the first `period` deltas; every value after that is
    smoothed as avg[i] = (avg[i-1]*(period-1) + value[i]) / period.

    Every index before `WARMUP_MIN_BARS` (100, spec 6.1) is None, even
    though a numeric value is mathematically available after `period + 1`
    bars -- same "don't trust an early estimate" rule as ATR.

    Edge case: if avg_loss is exactly 0 (an unbroken uptrend over the
    smoothing window), RSI is defined as 100, not a division by zero.
    """
    n = len(bars)
    result: list[float | None] = [None] * n
    if n < period + 1:
        return result

    closes = [b.close for b in bars]
    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]  # length n-1, deltas[0] is closes[1]-closes[0]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # deltas[i] corresponds to bar index i+1 (first bar has no delta).
    rsi_values: list[float | None] = [None] * n

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi_values[i + 1] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(WARMUP_MIN_BARS - 1, n):
        result[i] = rsi_values[i]
    return result


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
