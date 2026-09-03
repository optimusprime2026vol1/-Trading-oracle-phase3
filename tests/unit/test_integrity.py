"""
Phase 2 exit criterion: every check in spec section 3.5 must demonstrably
catch the condition it names, and freshness (3.2) must correctly classify
fresh vs stale data against configured per-timeframe thresholds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.data.contracts import AdjustmentStatus, Bar, Exchange, Timeframe
from src.data.integrity import (
    DataIntegrityFail,
    check_freshness,
    check_no_duplicate_timestamps,
    check_no_missing_bars,
    check_ohlc_consistency,
    check_price_jump_within_circuit,
    check_zero_volume_during_session,
    run_structural_checks,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _bar(open_time: datetime, *, high=101.0, low=99.0, close=100.0, open_=100.0, volume=1000) -> Bar:
    return Bar(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        timeframe=Timeframe.FIVE_MIN,
        bar_open_time_ist=open_time,
        bar_close_time_ist=open_time + timedelta(minutes=5),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source_id="test_provider",
        fetched_at_ist=open_time + timedelta(minutes=5),
        adjustment_status=AdjustmentStatus.ADJUSTED,
    )


# --- freshness (spec 3.2) ---------------------------------------------------


def test_fresh_bar_within_threshold() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST))
    now = bar.bar_close_time_ist + timedelta(seconds=60)
    result = check_freshness(bar, now, {"5min": 300})
    assert result.is_fresh
    assert result.data_age_seconds == 60


def test_stale_bar_beyond_threshold() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST))
    now = bar.bar_close_time_ist + timedelta(seconds=600)
    result = check_freshness(bar, now, {"5min": 300})
    assert not result.is_fresh


def test_freshness_unknown_timeframe_raises() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST))
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_freshness(bar, bar.bar_close_time_ist, {})
    assert exc_info.value.check_name == "UNKNOWN_TIMEFRAME_THRESHOLD"


# --- structural checks (spec 3.5) -------------------------------------------


def test_duplicate_timestamps_raise() -> None:
    t = datetime(2026, 8, 18, 10, 0, tzinfo=IST)
    bars = [_bar(t), _bar(t)]
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_no_duplicate_timestamps(bars)
    assert exc_info.value.check_name == "DUPLICATE_TIMESTAMP"


def test_high_less_than_low_raises() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST), high=98.0, low=99.0)
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_ohlc_consistency(bar)
    assert exc_info.value.check_name == "HIGH_LESS_THAN_LOW"


def test_close_outside_range_raises() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST), high=101.0, low=99.0, close=105.0)
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_ohlc_consistency(bar)
    assert exc_info.value.check_name == "CLOSE_OUTSIDE_RANGE"


def test_valid_ohlc_passes() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST))
    check_ohlc_consistency(bar)  # should not raise


def test_zero_volume_during_session_raises() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST), volume=0)
    session_start = datetime(2026, 8, 18, 9, 15, tzinfo=IST)
    session_end = datetime(2026, 8, 18, 15, 30, tzinfo=IST)
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_zero_volume_during_session(bar, session_start, session_end)
    assert exc_info.value.check_name == "ZERO_VOLUME_ACTIVE_HOURS"


def test_zero_volume_outside_session_allowed() -> None:
    bar = _bar(datetime(2026, 8, 18, 20, 0, tzinfo=IST), volume=0)
    session_start = datetime(2026, 8, 18, 9, 15, tzinfo=IST)
    session_end = datetime(2026, 8, 18, 15, 30, tzinfo=IST)
    check_zero_volume_during_session(bar, session_start, session_end)  # should not raise


def test_circuit_band_breach_raises() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST), close=130.0, high=131.0, low=99.0, open_=100.0)
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_price_jump_within_circuit(bar, prev_close=100.0, circuit_band_pct=20.0)
    assert exc_info.value.check_name == "CIRCUIT_BAND_BREACH"


def test_price_move_within_circuit_passes() -> None:
    bar = _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST), close=105.0, high=106.0, low=99.0, open_=100.0)
    check_price_jump_within_circuit(bar, prev_close=100.0, circuit_band_pct=20.0)  # should not raise


def test_missing_bar_gap_raises() -> None:
    bars = [
        _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST)),
        _bar(datetime(2026, 8, 18, 10, 20, tzinfo=IST)),  # 20 min gap, expected 5 min
    ]
    with pytest.raises(DataIntegrityFail) as exc_info:
        check_no_missing_bars(bars, expected_interval=timedelta(minutes=5))
    assert exc_info.value.check_name == "MISSING_BAR"


def test_consecutive_bars_no_gap_passes() -> None:
    bars = [
        _bar(datetime(2026, 8, 18, 10, 0, tzinfo=IST)),
        _bar(datetime(2026, 8, 18, 10, 5, tzinfo=IST)),
    ]
    check_no_missing_bars(bars, expected_interval=timedelta(minutes=5))  # should not raise


def test_run_structural_checks_all_pass() -> None:
    bars = [
        _bar(datetime(2026, 8, 18, 9, 15, tzinfo=IST), close=100.0),
        _bar(datetime(2026, 8, 18, 9, 20, tzinfo=IST), close=101.0),
        _bar(datetime(2026, 8, 18, 9, 25, tzinfo=IST), close=100.5),
    ]
    run_structural_checks(
        bars,
        session_start=datetime(2026, 8, 18, 9, 15, tzinfo=IST),
        session_end=datetime(2026, 8, 18, 15, 30, tzinfo=IST),
        circuit_band_pct=20.0,
        expected_interval=timedelta(minutes=5),
    )  # should not raise


def test_run_structural_checks_catches_embedded_failure() -> None:
    bars = [
        _bar(datetime(2026, 8, 18, 9, 15, tzinfo=IST), close=100.0),
        _bar(datetime(2026, 8, 18, 9, 20, tzinfo=IST), high=98.0, low=99.0, close=98.5),
    ]
    with pytest.raises(DataIntegrityFail) as exc_info:
        run_structural_checks(
            bars,
            session_start=datetime(2026, 8, 18, 9, 15, tzinfo=IST),
            session_end=datetime(2026, 8, 18, 15, 30, tzinfo=IST),
            circuit_band_pct=20.0,
            expected_interval=timedelta(minutes=5),
        )
    assert exc_info.value.check_name == "HIGH_LESS_THAN_LOW"


def test_run_structural_checks_handles_unsorted_input() -> None:
    bars = [
        _bar(datetime(2026, 8, 18, 9, 25, tzinfo=IST), close=100.5),
        _bar(datetime(2026, 8, 18, 9, 15, tzinfo=IST), close=100.0),
        _bar(datetime(2026, 8, 18, 9, 20, tzinfo=IST), close=101.0),
    ]
    run_structural_checks(
        bars,
        session_start=datetime(2026, 8, 18, 9, 15, tzinfo=IST),
        session_end=datetime(2026, 8, 18, 15, 30, tzinfo=IST),
        circuit_band_pct=20.0,
        expected_interval=timedelta(minutes=5),
    )  # should not raise -- sorted internally before checking
