"""
ZerodhaKiteProvider tests use a fake `kite_client` (see the class's
`kite_client=` injection point) so instrument-token resolution and bar
mapping are proven correct without real credentials, network access, or
the `kiteconnect` package installed. None of this hits Zerodha's servers
-- that can only be verified by running the real provider against a live,
authenticated session on your own machine (see README's "Data layer"
section and scripts/generate_kite_session.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.data.contracts import Exchange, Timeframe
from src.utils.config import ConfigError
from src.data.providers.zerodha_kite import ZerodhaKiteProvider

IST = timezone(timedelta(hours=5, minutes=30))


class FakeKite:
    """Stands in for kiteconnect.KiteConnect's two methods this provider
    calls, with a small fixed instrument universe and a fixed candle set."""

    def __init__(self) -> None:
        self.instruments_calls: list[str] = []
        self.historical_data_calls: list[tuple] = []

    def instruments(self, exchange: str) -> list[dict]:
        self.instruments_calls.append(exchange)
        if exchange == "NSE":
            return [
                {"tradingsymbol": "RELIANCE", "instrument_token": 738561, "exchange": "NSE"},
                {"tradingsymbol": "TCS", "instrument_token": 2953217, "exchange": "NSE"},
            ]
        return []

    def historical_data(self, token, start, end, interval) -> list[dict]:
        self.historical_data_calls.append((token, start, end, interval))
        base = datetime(2026, 8, 18, 9, 15, tzinfo=IST)
        return [
            {
                "date": base,
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 1000,
            },
            {
                "date": base + timedelta(minutes=5),
                "open": 100.5,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 1200,
            },
        ]


def test_resolve_instrument_token_finds_known_symbol() -> None:
    fake = FakeKite()
    provider = ZerodhaKiteProvider(kite_client=fake)
    token = provider._resolve_instrument_token("RELIANCE", Exchange.NSE)
    assert token == 738561
    assert fake.instruments_calls == ["NSE"]  # loaded once


def test_instrument_cache_loaded_only_once_per_exchange() -> None:
    fake = FakeKite()
    provider = ZerodhaKiteProvider(kite_client=fake)
    provider._resolve_instrument_token("RELIANCE", Exchange.NSE)
    provider._resolve_instrument_token("TCS", Exchange.NSE)
    assert fake.instruments_calls == ["NSE"]  # not called twice


def test_resolve_unknown_symbol_raises_config_error() -> None:
    fake = FakeKite()
    provider = ZerodhaKiteProvider(kite_client=fake)
    with pytest.raises(ConfigError):
        provider._resolve_instrument_token("NOT_A_REAL_SYMBOL", Exchange.NSE)


def test_fetch_historical_maps_candles_to_valid_bars() -> None:
    fake = FakeKite()
    provider = ZerodhaKiteProvider(kite_client=fake)
    bars = provider.fetch_historical(
        "RELIANCE",
        Exchange.NSE,
        Timeframe.FIVE_MIN,
        start=datetime(2026, 8, 18, 9, 0, tzinfo=IST),
        end=datetime(2026, 8, 18, 9, 30, tzinfo=IST),
    )
    assert len(bars) == 2
    assert bars[0].symbol == "RELIANCE"
    assert bars[0].close == 100.5
    assert bars[0].source_id == "zerodha_kite"
    assert fake.historical_data_calls[0][0] == 738561  # correct token used
    assert fake.historical_data_calls[0][3] == "5minute"  # correct interval mapping


def test_fetch_latest_returns_last_completed_bar() -> None:
    fake = FakeKite()
    provider = ZerodhaKiteProvider(kite_client=fake)
    latest = provider.fetch_latest("RELIANCE", Exchange.NSE, Timeframe.FIVE_MIN)
    assert latest is not None
    assert latest.close == 101.5


def test_missing_credentials_raise_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        ZerodhaKiteProvider()  # no kite_client injected -> real env lookup path
