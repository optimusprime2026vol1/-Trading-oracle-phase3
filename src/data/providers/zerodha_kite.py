"""
Zerodha Kite Connect data provider.

This class only ever *reads* market data (quotes/candles) -- it never
places orders. Spec section 21 keeps LIVE **execution** locked regardless
of whether this provider is wired up; reading a live feed and trading on
it are separate concerns, and this file only touches the first one.

Requires ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN in the environment (see
.env.example). Missing credentials raise ConfigError at construction time
-- this provider refuses to silently fall back to demo data; that is
HistoricalCsvProvider's job, invoked explicitly by whoever wires up the
system, never automatically.

Access tokens are short-lived (expire daily) and are generated via the
Kite Connect login flow, not hardcoded -- see scripts/generate_kite_session.py,
which is a standalone script meant to be run interactively on your own
machine (it opens a browser login), never inside this codebase's test
suite or CI.

Instrument token resolution (Kite requires numeric instrument tokens, not
raw trading symbols, for historical calls) is done via `kite.instruments()`,
a full per-exchange instrument dump, cached in memory per provider
instance after first use.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from src.data.contracts import AdjustmentStatus, Bar, Exchange, Timeframe
from src.utils.config import ConfigError, get_env
from src.utils.logging import get_logger, log_event

logger = get_logger("data.zerodha_kite")

_TIMEFRAME_TO_KITE_INTERVAL = {
    Timeframe.ONE_MIN: "minute",
    Timeframe.FIVE_MIN: "5minute",
    Timeframe.FIFTEEN_MIN: "15minute",
    Timeframe.DAILY: "day",
}

_LOOKBACK_FOR_LATEST = {
    Timeframe.ONE_MIN: timedelta(hours=6),
    Timeframe.FIVE_MIN: timedelta(days=1),
    Timeframe.FIFTEEN_MIN: timedelta(days=2),
    Timeframe.DAILY: timedelta(days=5),
}


class ZerodhaKiteProvider:
    """Implements the DataProvider contract (see providers/base.py) against
    Zerodha Kite Connect.

    `kiteconnect` is imported lazily inside __init__, not at module import
    time, so the rest of the codebase -- and its test suite -- never
    requires the package or live credentials just to import this module.

    A `kite_client` may be injected directly (bypassing env-var lookup and
    the real KiteConnect construction entirely) -- this is how the unit
    tests exercise instrument-token resolution and bar-mapping logic
    without needing real credentials, a network connection, or the
    kiteconnect package installed. Leave it as None for real usage.
    """

    def __init__(self, *, kite_client: Any | None = None) -> None:
        self._instrument_tokens: dict[tuple[Exchange, str], int] = {}
        self._loaded_exchanges: set[Exchange] = set()
        self.source_id = "zerodha_kite"

        if kite_client is not None:
            self._kite = kite_client
            return

        api_key = get_env("ZERODHA_API_KEY", required=True)
        access_token = get_env("ZERODHA_ACCESS_TOKEN", required=True)

        try:
            from kiteconnect import KiteConnect  # type: ignore
        except ImportError as exc:
            raise ConfigError(
                "kiteconnect package not installed. Run: "
                "pip install kiteconnect --break-system-packages"
            ) from exc

        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)

    def _ensure_instruments_loaded(self, exchange: Exchange) -> None:
        """Loads and caches the full instrument dump for one exchange.
        Kite's instruments() call returns tens of thousands of rows, so
        this happens at most once per exchange per provider instance, not
        once per symbol lookup."""
        if exchange in self._loaded_exchanges:
            return

        raw = self._kite.instruments(exchange.value)
        for row in raw:
            key = (exchange, row["tradingsymbol"])
            self._instrument_tokens[key] = int(row["instrument_token"])
        self._loaded_exchanges.add(exchange)
        log_event(
            logger,
            "instrument_cache_loaded",
            exchange=exchange.value,
            instrument_count=len(raw),
        )

    def _resolve_instrument_token(self, symbol: str, exchange: Exchange) -> int:
        self._ensure_instruments_loaded(exchange)
        token = self._instrument_tokens.get((exchange, symbol))
        if token is None:
            raise ConfigError(
                f"No instrument_token found for symbol={symbol!r} on "
                f"{exchange.value}. Check the tradingsymbol matches Kite's "
                f"exact naming exactly (e.g. 'RELIANCE', not 'RELIANCE.NS' "
                f"or 'NSE:RELIANCE')."
            )
        return token

    def fetch_historical(
        self,
        symbol: str,
        exchange: Exchange,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]:
        token = self._resolve_instrument_token(symbol, exchange)
        interval = _TIMEFRAME_TO_KITE_INTERVAL[timeframe]
        raw = self._kite.historical_data(token, start, end, interval)

        fetched_at = datetime.now(start.tzinfo)
        bars: list[Bar] = []
        for candle in raw:
            bars.append(
                Bar(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    bar_open_time_ist=candle["date"],
                    bar_close_time_ist=candle["date"],
                    open=float(candle["open"]),
                    high=float(candle["high"]),
                    low=float(candle["low"]),
                    close=float(candle["close"]),
                    volume=int(candle["volume"]),
                    source_id=self.source_id,
                    fetched_at_ist=fetched_at,
                    adjustment_status=AdjustmentStatus.ADJUSTED,
                )
            )
        return bars

    def fetch_latest(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe
    ) -> Bar | None:
        # Spec 3.3 closed-bar rule: must return the last **completed** bar,
        # never the currently-forming one -- hence a historical-data call
        # with a short lookback window, not a raw quote() call. `now` must
        # be timezone-aware (spec 3.5) since it flows into fetch_historical
        # and ultimately into Bar.fetched_at_ist.
        from src.utils.logging import IST

        now = datetime.now(tz=IST)
        lookback = _LOOKBACK_FOR_LATEST[timeframe]
        bars = self.fetch_historical(symbol, exchange, timeframe, start=now - lookback, end=now)
        return bars[-1] if bars else None
