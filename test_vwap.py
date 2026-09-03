"""
Phase 3 exit criterion: VWAP session-reset behaviour and the exact
cumulative Sum(TP*Vol)/Sum(Vol) formula from spec section 6.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators.vwap import WARMUP_MIN_SESSION_BARS, vwap

IST = timezone(timedelta(hours=5, minutes=30))


def test_vwap_none_before_5_bars_in_session() -> None:
    bars = make_bars([100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0])
    result = vwap(bars)
    assert all(v is None for v in result[: WARMUP_MIN_SESSION_BARS - 1])
    assert all(v is not None for v in result[WARMUP_MIN_SESSION_BARS - 1 :])


def test_vwap_matches_manual_calculation() -> None:
    closes = [100.0, 101.0, 99.0, 102.0, 98.0, 103.0]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    volumes = [1000, 1200, 900, 1500, 800, 1100]
    bars = make_bars(closes, highs=highs, lows=lows, volumes=volumes)

    result = vwap(bars)

    cum_tp_vol = 0.0
    cum_vol = 0.0
    for i in range(6):
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_tp_vol += tp * volumes[i]
        cum_vol += volumes[i]
    expected_last = cum_tp_vol / cum_vol
    assert result[-1] == pytest.approx(expected_last, abs=1e-9)


def test_vwap_resets_at_new_session() -> None:
    day1_start = datetime(2026, 8, 18, 9, 15, tzinfo=IST)
    day2_start = datetime(2026, 8, 19, 9, 15, tzinfo=IST)

    day1_bars = make_bars([100.0, 101.0, 99.0, 102.0, 98.0, 103.0], start=day1_start)
    day2_bars = make_bars([200.0, 201.0, 199.0, 202.0, 198.0, 203.0], start=day2_start)
    combined = day1_bars + day2_bars

    result = vwap(combined)
    result_day2_alone = vwap(day2_bars)

    # VWAP on day 2's 6th bar, computed within the combined series, must
    # equal VWAP computed on day 2 in isolation -- day 1's volume must not
    # leak across the session boundary.
    assert result[-1] == pytest.approx(result_day2_alone[-1], abs=1e-9)


def test_vwap_uses_typical_price_hlc_over_3() -> None:
    # Single bar type check via the formula on a session's first trusted bar.
    closes = [100.0] * 5
    highs = [110.0] * 5
    lows = [90.0] * 5
    volumes = [1000] * 5
    bars = make_bars(closes, highs=highs, lows=lows, volumes=volumes)
    result = vwap(bars)
    # typical price = (110+90+100)/3 = 100, constant volume -> VWAP = 100
    assert result[-1] == pytest.approx(100.0, abs=1e-9)
