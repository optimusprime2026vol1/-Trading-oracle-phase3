"""
Phase 2 exit criterion (partial): the Bar contract must reject anything
that violates spec section 3.1 (mandatory fields) or 3.5 (explicit-offset
timestamps), rather than accepting it and letting the hole surface later.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.data.contracts import AdjustmentStatus, Bar, BarValidationError, Exchange, Timeframe

IST = timezone(timedelta(hours=5, minutes=30))


def _valid_bar_kwargs() -> dict:
    open_time = datetime(2026, 8, 18, 9, 15, tzinfo=IST)
    return dict(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        timeframe=Timeframe.FIVE_MIN,
        bar_open_time_ist=open_time,
        bar_close_time_ist=open_time + timedelta(minutes=5),
        open=100.0,
        high=101.0,
        low=99.5,
        close=100.5,
        volume=1000,
        source_id="test_provider",
        fetched_at_ist=open_time + timedelta(minutes=5),
        adjustment_status=AdjustmentStatus.ADJUSTED,
    )


def test_valid_bar_constructs() -> None:
    bar = Bar(**_valid_bar_kwargs())
    assert bar.symbol == "RELIANCE"
    assert bar.adjustment_status == AdjustmentStatus.ADJUSTED


def test_naive_bar_open_time_rejected() -> None:
    kwargs = _valid_bar_kwargs()
    kwargs["bar_open_time_ist"] = datetime(2026, 8, 18, 9, 15)  # naive, no tz
    with pytest.raises(BarValidationError):
        Bar(**kwargs)


def test_naive_fetched_at_rejected() -> None:
    kwargs = _valid_bar_kwargs()
    kwargs["fetched_at_ist"] = datetime(2026, 8, 18, 9, 20)  # naive
    with pytest.raises(BarValidationError):
        Bar(**kwargs)


def test_empty_symbol_rejected() -> None:
    kwargs = _valid_bar_kwargs()
    kwargs["symbol"] = ""
    with pytest.raises(BarValidationError):
        Bar(**kwargs)


def test_empty_source_id_rejected() -> None:
    kwargs = _valid_bar_kwargs()
    kwargs["source_id"] = ""
    with pytest.raises(BarValidationError):
        Bar(**kwargs)


def test_negative_volume_rejected() -> None:
    kwargs = _valid_bar_kwargs()
    kwargs["volume"] = -5
    with pytest.raises(BarValidationError):
        Bar(**kwargs)


def test_close_before_open_time_rejected() -> None:
    kwargs = _valid_bar_kwargs()
    kwargs["bar_close_time_ist"] = kwargs["bar_open_time_ist"] - timedelta(minutes=1)
    with pytest.raises(BarValidationError):
        Bar(**kwargs)


def test_bar_is_immutable() -> None:
    bar = Bar(**_valid_bar_kwargs())
    with pytest.raises(Exception):
        bar.close = 999.0  # type: ignore[misc]
