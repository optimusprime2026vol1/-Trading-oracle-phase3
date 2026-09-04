"""
Phase 3 exit criterion: RVOL's insufficient-history withholding (spec
6.2) and the same-clock-time median comparison (spec section 6).
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators.rvol import rvol

IST = timezone(timedelta(hours=5, minutes=30))


def _session(day_offset: int, volumes: list[int]) -> list:
    start = datetime(2026, 8, 1, 9, 15, tzinfo=IST) + timedelta(days=day_offset)
    closes = [100.0] * len(volumes)
    return make_bars(closes, volumes=volumes, start=start)


def test_rvol_none_when_fewer_than_lookback_sessions() -> None:
    current = _session(30, [1000, 1000, 1000])
    historical = [_session(d, [900, 900, 900]) for d in range(1, 11)]  # only 10, need 20
    result = rvol(current, historical, lookback_sessions=20)
    assert all(v is None for v in result)


def test_rvol_matches_manual_median_calculation() -> None:
    current = _session(30, [1000, 1500, 800])
    historical = [_session(d, [500 + d * 10, 400, 300]) for d in range(1, 21)]  # 20 sessions

    result = rvol(current, historical, lookback_sessions=20)

    # At the 2nd bar, cumulative current volume = 1000+1500 = 2500.
    # Historical cumulative at same clock time (first 2 bars of each session).
    cutoff_time = current[1].bar_open_time_ist.time()
    hist_cums = [
        sum(b.volume for b in session if b.bar_open_time_ist.time() <= cutoff_time)
        for session in historical
    ]
    expected_median = statistics.median(hist_cums)
    expected_rvol = 2500 / expected_median
    assert result[1] == pytest.approx(expected_rvol, abs=1e-9)


def test_rvol_uses_only_most_recent_lookback_sessions() -> None:
    current = _session(50, [1000])
    old_sessions = [_session(d, [100]) for d in range(1, 6)]  # 5 very old, low-volume
    recent_sessions = [_session(d, [1000]) for d in range(10, 30)]  # 20 recent
    historical = old_sessions + recent_sessions

    result = rvol(current, historical, lookback_sessions=20)
    # Median should be based on the 20 recent (volume=1000) sessions only,
    # so RVOL should be ~1.0, not skewed by the 5 old low-volume sessions.
    assert result[0] == pytest.approx(1.0, abs=1e-9)
