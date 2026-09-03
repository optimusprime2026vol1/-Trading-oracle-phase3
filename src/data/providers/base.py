"""
Provider interface: every data source (live broker feed, historical
replay, and any future alternate) implements this contract so the rest of
the system never needs to know which provider produced a bar.

Master spec reference: section 3.6 (provider transparency -- "Never blend
providers inside one calculation. Never substitute cached data for live
data silently.") and section 13 (output schema field "data_source":
"provider_id").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from src.data.contracts import Bar, Exchange, Timeframe


class DataProvider(ABC):
    """Abstract base for all data providers.

    `source_id` must be a stable, unique string -- it is stamped on every
    Bar (spec 3.1) and, later, on every emitted signal (spec 13). Two
    providers must never share a source_id, or spec 3.6's "never blend
    providers" check becomes unenforceable.
    """

    source_id: str

    @abstractmethod
    def fetch_historical(
        self,
        symbol: str,
        exchange: Exchange,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]:
        """Returns bars in [start, end], ascending by bar_open_time_ist.
        Never forward-fills or interpolates a gap (spec 6.2) -- a missing
        bar is simply absent from the returned sequence, and
        integrity.check_no_missing_bars is what surfaces that absence."""
        raise NotImplementedError

    @abstractmethod
    def fetch_latest(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe
    ) -> Bar | None:
        """Returns the most recent **completed** bar only (spec 3.3,
        closed-bar rule) -- a forming/in-progress candle is never returned
        here, even if the underlying feed has one. None if no data is
        available at all."""
        raise NotImplementedError
