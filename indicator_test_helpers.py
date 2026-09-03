"""Shared helpers for indicator tests -- not a test file itself."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data.contracts import AdjustmentStatus, Bar, Exchange, Timeframe

IST = timezone(timedelta(hours=5, minutes=30))


def make_bars(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[int] | None = None,
    start: datetime | None = None,
    interval_minutes: int = 5,
    symbol: str = "TEST",
) -> list[Bar]:
    """Builds a simple ascending 5-min bar series from a list of closes.
    Defaults: high = close + 0.5, low = close - 0.5, open = previous close
    (or close on the first bar), volume = 1000."""
    n = len(closes)
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    volumes = volumes or [1000] * n
    start = start or datetime(2026, 8, 18, 9, 15, tzinfo=IST)

    bars = []
    prev_close = closes[0]
    for i in range(n):
        open_time = start + timedelta(minutes=interval_minutes * i)
        close_time = open_time + timedelta(minutes=interval_minutes)
        bars.append(
            Bar(
                symbol=symbol,
                exchange=Exchange.NSE,
                timeframe=Timeframe.FIVE_MIN,
                bar_open_time_ist=open_time,
                bar_close_time_ist=close_time,
                open=prev_close if i > 0 else closes[0],
                high=highs[i],
                low=lows[i],
                close=closes[i],
                volume=volumes[i],
                source_id="test",
                fetched_at_ist=close_time,
                adjustment_status=AdjustmentStatus.ADJUSTED,
            )
        )
        prev_close = closes[i]
    return bars
