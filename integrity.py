"""
Data integrity contract enforcement: structural checks (spec section 3.5)
and freshness checks (spec section 3.2).

Every check here maps to a specifically-named failure so it can be logged,
tested, and audited by name -- "some check somewhere failed" is not an
acceptable outcome (spec section 16, audit & reproducibility; spec 3.5:
"Any failure raises DATA_INTEGRITY_FAIL with the specific check name.").

These functions are deterministic and side-effect free (besides raising).
They never patch, interpolate, or forward-fill (spec 6.2) -- a failing
check always means the caller blocks the signal (spec section 4, gates
1 and 2), never that this module tries to "fix" the data itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from src.data.contracts import Bar


class DataIntegrityFail(Exception):
    """Raised with a specific check name, per spec 3.5."""

    def __init__(self, check_name: str, detail: str):
        self.check_name = check_name
        self.detail = detail
        super().__init__(f"DATA_INTEGRITY_FAIL[{check_name}]: {detail}")


@dataclass(frozen=True)
class FreshnessResult:
    """Spec 3.2: every emitted output carries data_timestamp and
    data_age_seconds. This is returned, never raised -- staleness is a
    gate-1 condition (spec section 4: STALE_DATA), evaluated by the caller
    alongside the other 12 gates, not a hard crash here."""

    is_fresh: bool
    data_age_seconds: float
    threshold_seconds: float


def check_freshness(
    latest_bar: Bar, now_ist: datetime, freshness_seconds: dict[str, float]
) -> FreshnessResult:
    """Spec 3.2 freshness thresholds, keyed by Timeframe.value (e.g. "5min").

    Raises DataIntegrityFail if the config has no threshold for this
    timeframe -- an unconfigured timeframe must never silently pass as
    fresh (spec 1: Tier 2 data integrity beats Tier 7 operator request).
    """
    threshold = freshness_seconds.get(latest_bar.timeframe.value)
    if threshold is None:
        raise DataIntegrityFail(
            "UNKNOWN_TIMEFRAME_THRESHOLD",
            f"No freshness threshold configured for timeframe "
            f"{latest_bar.timeframe.value!r}",
        )
    age = (now_ist - latest_bar.bar_close_time_ist).total_seconds()
    return FreshnessResult(
        is_fresh=0 <= age <= threshold, data_age_seconds=age, threshold_seconds=threshold
    )


def check_no_duplicate_timestamps(bars: Sequence[Bar]) -> None:
    """Spec 3.5: 'Duplicate timestamps'."""
    seen: set[tuple] = set()
    for bar in bars:
        key = (bar.symbol, bar.exchange, bar.timeframe, bar.bar_open_time_ist)
        if key in seen:
            raise DataIntegrityFail(
                "DUPLICATE_TIMESTAMP",
                f"Duplicate bar_open_time_ist {bar.bar_open_time_ist} for {bar.symbol}",
            )
        seen.add(key)


def check_ohlc_consistency(bar: Bar) -> None:
    """Spec 3.5: 'High < low, or close outside high-low range'."""
    if bar.high < bar.low:
        raise DataIntegrityFail(
            "HIGH_LESS_THAN_LOW",
            f"{bar.symbol} @ {bar.bar_open_time_ist}: high {bar.high} < low {bar.low}",
        )
    if not (bar.low <= bar.close <= bar.high):
        raise DataIntegrityFail(
            "CLOSE_OUTSIDE_RANGE",
            f"{bar.symbol} @ {bar.bar_open_time_ist}: close {bar.close} "
            f"outside [{bar.low}, {bar.high}]",
        )
    if not (bar.low <= bar.open <= bar.high):
        raise DataIntegrityFail(
            "OPEN_OUTSIDE_RANGE",
            f"{bar.symbol} @ {bar.bar_open_time_ist}: open {bar.open} "
            f"outside [{bar.low}, {bar.high}]",
        )


def check_zero_volume_during_session(
    bar: Bar, session_start: datetime, session_end: datetime
) -> None:
    """Spec 3.5: 'Zero-volume bars during active hours'."""
    if session_start <= bar.bar_open_time_ist <= session_end and bar.volume == 0:
        raise DataIntegrityFail(
            "ZERO_VOLUME_ACTIVE_HOURS",
            f"{bar.symbol} @ {bar.bar_open_time_ist}: zero volume during active session",
        )


def check_price_jump_within_circuit(
    bar: Bar, prev_close: float, circuit_band_pct: float
) -> None:
    """Spec 3.5: 'Price jump beyond the applicable circuit band'.
    circuit_band_pct is per-symbol (2/5/10/20, spec 5.3) -- caller supplies
    the value applicable to this symbol; this function does not look it up."""
    if prev_close <= 0:
        return
    move_pct = abs(bar.close - prev_close) / prev_close * 100
    if move_pct > circuit_band_pct:
        raise DataIntegrityFail(
            "CIRCUIT_BAND_BREACH",
            f"{bar.symbol} @ {bar.bar_open_time_ist}: move {move_pct:.2f}% "
            f"exceeds circuit band {circuit_band_pct}%",
        )


def check_no_missing_bars(bars: Sequence[Bar], expected_interval: timedelta) -> None:
    """Spec 3.5: 'Missing bars inside a session'. `bars` must already be
    sorted ascending by bar_open_time_ist (run_structural_checks guarantees
    this)."""
    for prev, curr in zip(bars, bars[1:]):
        gap = curr.bar_open_time_ist - prev.bar_open_time_ist
        if gap > expected_interval:
            raise DataIntegrityFail(
                "MISSING_BAR",
                f"{curr.symbol}: gap of {gap} between {prev.bar_open_time_ist} "
                f"and {curr.bar_open_time_ist}, expected at most {expected_interval}",
            )


def run_structural_checks(
    bars: Sequence[Bar],
    *,
    session_start: datetime,
    session_end: datetime,
    circuit_band_pct: float,
    expected_interval: timedelta,
) -> None:
    """Runs every section-3.5 check across a bar series in one call.
    Raises DataIntegrityFail on the first failure found, naming the
    specific check, per spec 3.5. Sorts defensively -- callers should not
    rely on input order."""
    sorted_bars = sorted(bars, key=lambda b: b.bar_open_time_ist)

    check_no_duplicate_timestamps(sorted_bars)
    check_no_missing_bars(sorted_bars, expected_interval)

    prev_close: float | None = None
    for bar in sorted_bars:
        check_ohlc_consistency(bar)
        check_zero_volume_during_session(bar, session_start, session_end)
        if prev_close is not None:
            check_price_jump_within_circuit(bar, prev_close, circuit_band_pct)
        prev_close = bar.close
