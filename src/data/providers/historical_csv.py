"""
Historical/offline data provider: reads pre-downloaded OHLCV bars from CSV
files.

This exists so indicators, gates, strategies, and the backtest harness
(phases 3-10) can be built and unit-tested without requiring live Zerodha
Kite Connect credentials. It implements the same DataProvider contract as
ZerodhaKiteProvider (see providers/base.py and providers/zerodha_kite.py),
so nothing downstream needs to special-case "no live feed yet" -- swapping
providers is a one-line change once real credentials exist.

CSV schema (one row per bar), header required:
    bar_open_time_ist,bar_close_time_ist,open,high,low,close,volume,adjustment_status

Timestamps must be ISO-8601 with an explicit offset, e.g.
"2026-08-18T09:20:00+05:30" (spec 3.5). `source_id` is always
"historical_csv:<filename>" so spec 3.6's "never blend providers" check
can tell this apart from a live feed at a glance.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Sequence

from src.data.contracts import AdjustmentStatus, Bar, BarValidationError, Exchange, Timeframe
from src.utils.logging import get_logger

logger = get_logger("data.historical_csv")


class HistoricalCsvProvider:
    """Implements the DataProvider contract by reading bars from a CSV file
    per (exchange, symbol, timeframe), located at
    ``<data_dir>/<exchange>/<symbol>_<timeframe>.csv``.
    """

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.source_id = "historical_csv"

    def _csv_path(self, symbol: str, exchange: Exchange, timeframe: Timeframe) -> Path:
        return self.data_dir / exchange.value / f"{symbol}_{timeframe.value}.csv"

    def _row_to_bar(
        self,
        row: dict[str, str],
        symbol: str,
        exchange: Exchange,
        timeframe: Timeframe,
        path: Path,
        row_num: int,
    ) -> Bar | None:
        # Spec 3.1: "A bar missing any field is discarded, not patched." A
        # malformed row is logged and skipped -- it never aborts the whole
        # fetch, and it never gets a guessed/patched value.
        try:
            open_time = datetime.fromisoformat(row["bar_open_time_ist"])
            close_time = datetime.fromisoformat(row["bar_close_time_ist"])
            return Bar(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                bar_open_time_ist=open_time,
                bar_close_time_ist=close_time,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(float(row["volume"])),
                source_id=f"{self.source_id}:{path.name}",
                fetched_at_ist=close_time,  # offline data: "fetched" = bar close time
                adjustment_status=AdjustmentStatus(row.get("adjustment_status", "UNKNOWN")),
            )
        except (KeyError, ValueError, BarValidationError) as exc:
            logger.warning(
                "historical_csv_row_discarded",
                extra={
                    "extra_fields": {
                        "path": str(path),
                        "row_num": row_num,
                        "reason": str(exc),
                    }
                },
            )
            return None

    def _read_all(self, symbol: str, exchange: Exchange, timeframe: Timeframe) -> list[Bar]:
        path = self._csv_path(symbol, exchange, timeframe)
        if not path.is_file():
            logger.warning(
                "historical_csv_file_missing", extra={"extra_fields": {"path": str(path)}}
            )
            return []

        bars: list[Bar] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # header is row 1
                bar = self._row_to_bar(row, symbol, exchange, timeframe, path, row_num)
                if bar is not None:
                    bars.append(bar)
        bars.sort(key=lambda b: b.bar_open_time_ist)
        return bars

    def fetch_historical(
        self,
        symbol: str,
        exchange: Exchange,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]:
        all_bars = self._read_all(symbol, exchange, timeframe)
        return [b for b in all_bars if start <= b.bar_open_time_ist <= end]

    def fetch_latest(
        self, symbol: str, exchange: Exchange, timeframe: Timeframe
    ) -> Bar | None:
        all_bars = self._read_all(symbol, exchange, timeframe)
        return all_bars[-1] if all_bars else None
