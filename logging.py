"""
Structured, reproducible logging.

Master spec reference: section 3.5 ("everything stored in IST, ISO-8601,
explicit offset"), section 16 (audit & reproducibility -- every decision
must be reconstructable from stored records alone), section 18 (dashboard
must show data timestamp / age).

Every log line is a single JSON object on its own line (JSON-Lines), so logs
are machine-parseable for audits and tests, not just human-readable text.
"Reproducible" here means: given the same inputs (event name + fields), the
JSON structure and field set are always identical -- only the wall-clock
timestamp and any explicitly-varying field (like a UUID) differ between
calls. Tests assert on structure and required fields, not on exact text.

IST is a fixed UTC+05:30 offset with no daylight saving, so it is defined
directly as a `timezone` object instead of depending on system tzdata
(which may be missing in minimal CI containers).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "logs"

_REQUIRED_LOG_RECORD_FIELDS = ("timestamp_ist", "level", "logger", "message")


def now_ist_iso() -> str:
    """Current time as ISO-8601 with an explicit +05:30 offset, e.g.
    '2026-08-18T14:05:32.123456+05:30'. Never naive, never UTC-labelled-as-IST."""
    return datetime.now(tz=IST).isoformat()


class JsonLinesFormatter(logging.Formatter):
    """Renders each LogRecord as one JSON object per line.

    Extra structured fields are passed via `logger.info(msg, extra={"extra_fields": {...}})`
    and merged into the output object alongside the required fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_ist": now_ist_iso(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def get_logger(name: str, *, log_file: str = "oracle.log", level: int = logging.INFO) -> logging.Logger:
    """Return a logger configured for structured JSON-lines output.

    Writes to both stdout (for `docker logs` / CI output) and a rotating file
    under logs/, so nothing depends on the process's stdout being captured.
    Safe to call repeatedly with the same name -- handlers are not duplicated.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger  # already configured

    formatter = JsonLinesFormatter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_DIR / log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Read-only filesystem or similar -- stdout logging still works.
        logger.warning("Could not open log file under %s; stdout-only logging active", LOG_DIR)

    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields: Any) -> None:
    """Convenience wrapper: log_event(logger, "signal_blocked", level=logging.WARNING,
    symbol="EXAMPLE", gate="STALE_DATA")."""
    logger.log(level, message, extra={"extra_fields": fields})
