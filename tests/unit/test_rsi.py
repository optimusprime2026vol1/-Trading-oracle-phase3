"""
Phase 3 exit criterion: RSI against an independently-written reference,
plus known boundary cases (all-up moves -> RSI=100, all-down -> RSI=0).
"""

from __future__ import annotations

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators.rsi import WARMUP_MIN_BARS, rsi


def _reference_rsi(bars, period: int) -> list[float | None]:
    n = len(bars)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out

    closes = [b.close for b in bars]
    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    raw: list[float | None] = [None] * n
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi(g, l):
        if l == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    raw[period] = _rsi(avg_gain, avg_loss)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        raw[i + 1] = _rsi(avg_gain, avg_loss)

    for i in range(WARMUP_MIN_BARS - 1, n):
        out[i] = raw[i]
    return out


def test_rsi_matches_independent_reference() -> None:
    closes = [100 + ((i * 37) % 11) - 5 for i in range(130)]
    bars = make_bars([float(c) for c in closes])
    result = rsi(bars, period=14)
    expected = _reference_rsi(bars, period=14)
    for got, want in zip(result, expected):
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want, abs=1e-9)


def test_rsi_none_before_100_bars() -> None:
    closes = [100.0 + (i % 3) for i in range(130)]
    bars = make_bars(closes)
    result = rsi(bars, period=14)
    assert all(v is None for v in result[:99])
    assert all(v is not None for v in result[99:])


def test_rsi_is_100_for_unbroken_uptrend() -> None:
    closes = [100.0 + i for i in range(120)]  # strictly increasing every bar
    bars = make_bars(closes)
    result = rsi(bars, period=14)
    assert result[-1] == pytest.approx(100.0)


def test_rsi_is_0_for_unbroken_downtrend() -> None:
    closes = [200.0 - i for i in range(120)]  # strictly decreasing every bar
    bars = make_bars(closes)
    result = rsi(bars, period=14)
    assert result[-1] == pytest.approx(0.0)
