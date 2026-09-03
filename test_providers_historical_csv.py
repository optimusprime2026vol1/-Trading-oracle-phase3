"""
Phase 2 exit criterion (partial): HistoricalCsvProvider must implement the
DataProvider contract correctly against real files -- correct rows parsed
into valid Bars, malformed rows discarded (not crashing the whole fetch,
per spec 3.1), and a missing file returning an empty sequence rather than
raising.
"""

from __future__ import annotations

from pathlib import Path

from src.data.contracts import AdjustmentStatus, Exchange, Timeframe
from src.data.providers.historical_csv import HistoricalCsvProvider

CSV_HEADER = "bar_open_time_ist,bar_close_time_ist,open,high,low,close,volume,adjustment_status\n"


def _write_csv(tmp_path: Path, exchange: Exchange, symbol: str, timeframe: Timeframe, rows: list[str]) -> None:
    d = tmp_path / exchange.value
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{symbol}_{timeframe.value}.csv"
    path.write_text(CSV_HEADER + "".join(rows), encoding="utf-8")


def test_fetch_historical_returns_bars_in_range(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        Exchange.NSE,
        "RELIANCE",
        Timeframe.FIVE_MIN,
        [
            "2026-08-18T09:15:00+05:30,2026-08-18T09:20:00+05:30,100,101,99,100.5,1000,ADJUSTED\n",
            "2026-08-18T09:20:00+05:30,2026-08-18T09:25:00+05:30,100.5,102,100,101.5,1200,ADJUSTED\n",
            "2026-08-18T09:25:00+05:30,2026-08-18T09:30:00+05:30,101.5,103,101,102.5,900,ADJUSTED\n",
        ],
    )
    provider = HistoricalCsvProvider(tmp_path)
    from datetime import datetime, timedelta, timezone

    IST = timezone(timedelta(hours=5, minutes=30))
    bars = provider.fetch_historical(
        "RELIANCE",
        Exchange.NSE,
        Timeframe.FIVE_MIN,
        start=datetime(2026, 8, 18, 9, 15, tzinfo=IST),
        end=datetime(2026, 8, 18, 9, 22, tzinfo=IST),
    )
    assert len(bars) == 2
    assert bars[0].close == 100.5
    assert bars[1].close == 101.5
    assert bars[0].source_id.startswith("historical_csv:")
    assert bars[0].adjustment_status == AdjustmentStatus.ADJUSTED


def test_fetch_latest_returns_last_bar(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        Exchange.NSE,
        "TCS",
        Timeframe.FIVE_MIN,
        [
            "2026-08-18T09:15:00+05:30,2026-08-18T09:20:00+05:30,3900,3910,3895,3905,500,ADJUSTED\n",
            "2026-08-18T09:20:00+05:30,2026-08-18T09:25:00+05:30,3905,3920,3900,3915,600,ADJUSTED\n",
        ],
    )
    provider = HistoricalCsvProvider(tmp_path)
    latest = provider.fetch_latest("TCS", Exchange.NSE, Timeframe.FIVE_MIN)
    assert latest is not None
    assert latest.close == 3915


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    provider = HistoricalCsvProvider(tmp_path)
    bars = provider.fetch_historical(
        "NOPE",
        Exchange.NSE,
        Timeframe.FIVE_MIN,
        start=__import__("datetime").datetime(2026, 1, 1),
        end=__import__("datetime").datetime(2026, 1, 2),
    )
    assert bars == []
    assert provider.fetch_latest("NOPE", Exchange.NSE, Timeframe.FIVE_MIN) is None


def test_malformed_row_discarded_not_crashing(tmp_path: Path) -> None:
    _write_csv(
        tmp_path,
        Exchange.NSE,
        "INFY",
        Timeframe.FIVE_MIN,
        [
            "2026-08-18T09:15:00+05:30,2026-08-18T09:20:00+05:30,1500,1510,1495,1505,300,ADJUSTED\n",
            # missing volume field entirely -> KeyError -> discarded
            "2026-08-18T09:20:00+05:30,2026-08-18T09:25:00+05:30,1505,1520,1500,1515,ADJUSTED\n",
            "2026-08-18T09:25:00+05:30,2026-08-18T09:30:00+05:30,1515,1525,1510,1520,400,ADJUSTED\n",
        ],
    )
    provider = HistoricalCsvProvider(tmp_path)
    latest = provider.fetch_latest("INFY", Exchange.NSE, Timeframe.FIVE_MIN)
    assert latest is not None
    assert latest.close == 1520  # the malformed middle row was skipped, not crashed on

    from datetime import datetime, timedelta, timezone

    IST = timezone(timedelta(hours=5, minutes=30))
    bars = provider.fetch_historical(
        "INFY",
        Exchange.NSE,
        Timeframe.FIVE_MIN,
        start=datetime(2026, 8, 18, 0, 0, tzinfo=IST),
        end=datetime(2026, 8, 19, 0, 0, tzinfo=IST),
    )
    assert len(bars) == 2  # only the 2 well-formed rows survive
