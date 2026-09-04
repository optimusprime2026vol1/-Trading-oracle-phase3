"""
Data contracts: the shape every OHLCV bar must satisfy before it can enter
the system.

Master spec reference: TRADING_ORACLE_v2_MASTER_SPEC.md, section 3 (Data
Integrity Contract) -- specifically 3.1 (mandatory fields on every bar) and
3.4 (corporate action adjustment status).

A Bar is the unit of truth for the whole system. Every field listed in
spec 3.1 is required and typed here; a bar built with a missing or
wrong-shaped field fails fast (BarValidationError) at construction time
rather than silently propagating a hole into an indicator calculation
three modules later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"


class Timeframe(str, Enum):
    ONE_MIN = "1min"
    FIVE_MIN = "5min"
    FIFTEEN_MIN = "15min"
    DAILY = "daily"


class AdjustmentStatus(str, Enum):
    ADJUSTED = "ADJUSTED"
    UNADJUSTED = "UNADJUSTED"
    UNKNOWN = "UNKNOWN"  # spec 3.4: UNKNOWN is treated as unusable for indicators


class BarValidationError(Exception):
    """Raised when a bar is missing a mandatory field or has an invalid shape.

    Spec 3.1: "A bar missing any field is discarded, not patched." Providers
    catch this per-row and skip+log the bad bar rather than letting one bad
    row abort an entire fetch (see providers/historical_csv.py).
    """


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar. Every field in spec section 3.1 is mandatory:
    symbol, exchange, timeframe, bar_open_time_ist, bar_close_time_ist,
    open, high, low, close, volume, source_id, fetched_at_ist,
    adjustment_status.

    Timestamps must be timezone-aware with an explicit offset (spec 3.5:
    "everything stored in IST, ISO-8601, explicit offset"). A naive
    datetime is treated as a missing field, not silently assumed to be IST.
    """

    symbol: str
    exchange: Exchange
    timeframe: Timeframe
    bar_open_time_ist: datetime
    bar_close_time_ist: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    source_id: str
    fetched_at_ist: datetime
    adjustment_status: AdjustmentStatus

    def __post_init__(self) -> None:
        for field_name, ts in (
            ("bar_open_time_ist", self.bar_open_time_ist),
            ("bar_close_time_ist", self.bar_close_time_ist),
            ("fetched_at_ist", self.fetched_at_ist),
        ):
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise BarValidationError(
                    f"{field_name} must be timezone-aware with an explicit "
                    f"offset (spec 3.5); got naive datetime {ts!r}"
                )

        if not self.symbol:
            raise BarValidationError("symbol is mandatory (spec 3.1)")
        if not self.source_id:
            raise BarValidationError("source_id is mandatory (spec 3.1)")
        if self.volume < 0:
            raise BarValidationError(f"volume cannot be negative, got {self.volume}")
        if self.bar_close_time_ist < self.bar_open_time_ist:
            raise BarValidationError(
                "bar_close_time_ist cannot be before bar_open_time_ist "
                f"({self.bar_close_time_ist} < {self.bar_open_time_ist})"
            )
