"""
Relative Volume (RVOL).

Master spec reference: section 6 -- "RVOL | Current cumulative volume /
median cumulative volume at same clock time over 20 sessions."

Unlike the other indicators, RVOL needs data from *other sessions*, not
just a longer lookback within one series -- hence the different signature
(a separate `historical_sessions` argument) versus every other indicator
in this package, which only takes one bar series.
"""

from __future__ import annotations

import statistics
from typing import Sequence

from src.data.contracts import Bar

DEFAULT_LOOKBACK_SESSIONS = 20  # spec section 6


def rvol(
    current_session_bars: Sequence[Bar],
    historical_sessions: Sequence[Sequence[Bar]],
    lookback_sessions: int = DEFAULT_LOOKBACK_SESSIONS,
) -> list[float | None]:
    """Returns RVOL aligned index-for-index with `current_session_bars`.

    `historical_sessions` is a sequence of prior sessions' bars, oldest
    first; each inner sequence is one full session's bars. If fewer than
    `lookback_sessions` are supplied, every output is None -- spec 6.2's
    "missing input means missing output" applies to insufficient
    historical breadth exactly as it does to missing fields on a single
    bar; a median over 6 sessions is not what the spec's 20-session
    definition means, so it is withheld rather than silently computed
    over less data.

    For each bar, cumulative volume up to and including that bar's
    time-of-day is compared against the median of the same
    same-time-of-day cumulative volume across the most recent
    `lookback_sessions` historical sessions.
    """
    n = len(current_session_bars)
    result: list[float | None] = [None] * n

    if len(historical_sessions) < lookback_sessions:
        return result

    sessions = historical_sessions[-lookback_sessions:]

    cum_vol = 0.0
    for i, bar in enumerate(current_session_bars):
        cum_vol += bar.volume
        cutoff_time = bar.bar_open_time_ist.time()

        historical_cums = [
            sum(b.volume for b in session if b.bar_open_time_ist.time() <= cutoff_time)
            for session in sessions
        ]
        median_cum = statistics.median(historical_cums)
        if median_cum > 0:
            result[i] = cum_vol / median_cum

    return result
