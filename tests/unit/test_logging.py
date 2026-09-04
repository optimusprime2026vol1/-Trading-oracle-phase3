"""
Phase 1 exit criterion: "Logs reproducible."

"Reproducible" means structurally reproducible: the same log call always
produces a JSON object with the same required fields and the same values
for anything that isn't inherently time-varying (spec section 16 -- audit
records must be reconstructable). These tests assert on structure, not on
literal timestamps.
"""

from __future__ import annotations

import json
import logging

from src.utils.logging import IST, get_logger, log_event, now_ist_iso


def _capture(logger_name: str):
    """Attach a fresh in-memory handler and return (logger, list-of-lines)."""
    logger = get_logger(logger_name)
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(logger.handlers[0].formatter)
    logger.addHandler(handler)
    return logger, records


def test_now_ist_iso_has_explicit_offset() -> None:
    ts = now_ist_iso()
    assert ts.endswith("+05:30")
    # ISO-8601 with a 'T' separator, per spec section 3.5.
    assert "T" in ts


def test_ist_is_fixed_offset_no_dst() -> None:
    assert IST.utcoffset(None).total_seconds() == 5.5 * 3600


def test_log_event_produces_valid_json_line() -> None:
    logger, records = _capture("test.reproducible")
    log_event(logger, "signal_blocked", symbol="EXAMPLE", gate="STALE_DATA")

    assert len(records) == 1
    payload = json.loads(records[0])  # raises if not valid JSON
    for field in ("timestamp_ist", "level", "logger", "message"):
        assert field in payload
    assert payload["message"] == "signal_blocked"
    assert payload["symbol"] == "EXAMPLE"
    assert payload["gate"] == "STALE_DATA"
    assert payload["timestamp_ist"].endswith("+05:30")


def test_log_event_structure_is_reproducible_across_calls() -> None:
    logger, records = _capture("test.reproducible.repeat")
    log_event(logger, "signal_blocked", symbol="EXAMPLE", gate="STALE_DATA")
    log_event(logger, "signal_blocked", symbol="EXAMPLE", gate="STALE_DATA")

    first = json.loads(records[0])
    second = json.loads(records[1])
    # Same fields, same non-time-varying values -- only the timestamp differs.
    assert set(first.keys()) == set(second.keys())
    for key in first:
        if key == "timestamp_ist":
            continue
        assert first[key] == second[key]


def test_get_logger_does_not_duplicate_handlers_on_repeat_calls() -> None:
    logger_a = get_logger("test.no_dup")
    handler_count_after_first = len(logger_a.handlers)
    logger_b = get_logger("test.no_dup")
    assert logger_a is logger_b
    assert len(logger_b.handlers) == handler_count_after_first
