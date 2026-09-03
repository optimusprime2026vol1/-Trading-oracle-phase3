"""
Phase 3 exit criterion: MACD histogram = macd_line - signal_line
everywhere both are present, and internal EMAs verified against
src/indicators/_core.py's seeded_ema_series directly (a different code
path than macd()'s own internal calls, since the test constructs its own
raw_fast/raw_slow and compares).
"""

from __future__ import annotations

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators._core import seeded_ema_series
from src.indicators.macd import macd


def test_histogram_equals_macd_minus_signal_everywhere_present() -> None:
    closes = [100 + ((i * 13) % 9) - 4 for i in range(150)]
    bars = make_bars([float(c) for c in closes])
    result = macd(bars)
    for m, s, h in zip(result.macd_line, result.signal_line, result.histogram):
        if m is not None and s is not None:
            assert h == pytest.approx(m - s, abs=1e-9)
        else:
            assert h is None


def test_macd_line_matches_difference_of_seeded_emas() -> None:
    closes = [100 + ((i * 7) % 5) for i in range(150)]
    bars = make_bars([float(c) for c in closes])
    result = macd(bars, fast=12, slow=26, signal=9)

    raw_fast = seeded_ema_series(closes, 12)
    raw_slow = seeded_ema_series(closes, 26)
    for i, m in enumerate(result.macd_line):
        if m is not None:
            assert raw_fast[i] is not None and raw_slow[i] is not None
            assert m == pytest.approx(raw_fast[i] - raw_slow[i], abs=1e-9)


def test_macd_rejects_fast_greater_than_or_equal_slow() -> None:
    bars = make_bars([100.0] * 10)
    with pytest.raises(ValueError):
        macd(bars, fast=26, slow=12)


def test_macd_all_none_for_short_series() -> None:
    bars = make_bars([100.0] * 10)
    result = macd(bars)
    assert all(v is None for v in result.macd_line)
    assert all(v is None for v in result.signal_line)
    assert all(v is None for v in result.histogram)
