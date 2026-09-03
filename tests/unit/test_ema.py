"""
Phase 3 exit criterion: "Unit tests match reference values exactly."

`_reference_ema` is written independently from src/indicators/ema.py --
a fresh recursive loop, not a call into the module under test -- so a bug
introduced in the implementation has a real chance of being caught rather
than the test just re-deriving the same formula from the same code.
"""

from __future__ import annotations

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators.ema import ema


def _reference_ema(closes: list[float], period: int) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    alpha = 2.0 / (period + 1)
    seed = sum(closes[:period]) / period
    prev = seed
    raw = [None] * n
    raw[period - 1] = seed
    for i in range(period, n):
        prev = closes[i] * alpha + prev * (1 - alpha)
        raw[i] = prev
    warmup = 3 * period - 1
    for i in range(warmup, n):
        out[i] = raw[i]
    return out


def test_ema_matches_independent_reference() -> None:
    closes = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105, 100, 101, 99, 102, 98]
    bars = make_bars(closes)
    period = 3
    result = ema(bars, period)
    expected = _reference_ema(closes, period)
    assert len(result) == len(expected)
    for got, want in zip(result, expected):
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want, abs=1e-9)


def test_ema_none_before_warmup() -> None:
    closes = [100.0] * 20
    bars = make_bars(closes)
    period = 5
    result = ema(bars, period)
    warmup = 3 * period - 1  # = 14
    assert all(v is None for v in result[:warmup])
    assert all(v is not None for v in result[warmup:])


def test_ema_of_constant_series_equals_the_constant() -> None:
    closes = [50.0] * 30
    bars = make_bars(closes)
    result = ema(bars, 5)
    for v in result[14:]:
        assert v == 50.0


def test_ema_too_short_series_returns_all_none() -> None:
    closes = [100.0, 101.0]
    bars = make_bars(closes)
    result = ema(bars, 5)
    assert all(v is None for v in result)
