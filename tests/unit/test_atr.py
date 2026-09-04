"""
Phase 3 exit criterion: ATR against an independently-written reference
(fresh Wilder-smoothing loop, not a call into the module under test).
"""

from __future__ import annotations

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators.atr import WARMUP_MIN_BARS, atr, true_range


def _reference_atr(bars, period: int) -> list[float | None]:
    n = len(bars)
    out: list[float | None] = [None] * n
    if n < period:
        return out

    trs = []
    prev_close = None
    for b in bars:
        if prev_close is None:
            trs.append(b.high - b.low)
        else:
            trs.append(max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close)))
        prev_close = b.close

    raw: list[float | None] = [None] * n
    seed = sum(trs[:period]) / period
    raw[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (prev * (period - 1) + trs[i]) / period
        raw[i] = prev

    for i in range(WARMUP_MIN_BARS - 1, n):
        out[i] = raw[i]
    return out


def test_atr_matches_independent_reference() -> None:
    closes = [100 + (i % 7) - 3 for i in range(120)]
    highs = [c + 1.5 for c in closes]
    lows = [c - 1.0 for c in closes]
    bars = make_bars(closes, highs=highs, lows=lows)
    result = atr(bars, period=14)
    expected = _reference_atr(bars, period=14)
    for got, want in zip(result, expected):
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want, abs=1e-9)


def test_atr_none_before_100_bars() -> None:
    closes = [100.0 + i * 0.1 for i in range(120)]
    bars = make_bars(closes)
    result = atr(bars, period=14)
    assert all(v is None for v in result[:99])
    assert all(v is not None for v in result[99:])


def test_true_range_first_bar_uses_high_minus_low() -> None:
    bars = make_bars([100.0, 101.0])
    tr = true_range(bars[0], prev_close=None)
    assert tr == pytest.approx(bars[0].high - bars[0].low)


def test_atr_of_flat_bars_equals_constant_range() -> None:
    # high-low is always exactly 2.0, close never gaps beyond that range,
    # so true range is constant at 2.0 for every bar -> ATR settles at 2.0.
    closes = [100.0] * 120
    highs = [101.0] * 120
    lows = [99.0] * 120
    bars = make_bars(closes, highs=highs, lows=lows)
    result = atr(bars, period=14)
    assert result[-1] == pytest.approx(2.0, abs=1e-6)
