"""COLUM structured logging.

- Rotating file logs in data/logs/ + console output.
- NEVER log secrets: a message filter redacts anything that looks like a key,
  and helpers encourage logging masked values only.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.config import LOGS_DIR

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
SECRET_KEY_PATTERN = re.compile(
    r"(sk-or-[A-Za-z0-9\-_]{8,}|sk-[A-Za-z0-9\-_]{12,}|Bearer\s+\S{12,})", re.IGNORECASE
)


class SecretRedactionFilter(logging.Filter):
    """Defense-in-depth: strip anything resembling an API key from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = SECRET_KEY_PATTERN.sub("[REDACTED]", msg)
            if redacted != msg:
                record.msg = redacted
                record.args = None
        except Exception:  # never break logging
            pass
        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    root = logging.getLogger("colum")
    if root.handlers:  # idempotent setup (uvicorn reload etc.)
        return root

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(LOG_FORMAT)
    redactor = SecretRedactionFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(redactor)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOGS_DIR / "colum.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    root.addHandler(file_handler)

    root.propagate = False
    return root


def log_json(logger: logging.Logger, level: int, event: str, **fields) -> None:
    """Emit a single-line structured JSON log entry."""
    payload = {"event": event, **fields}
    try:
        logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.log(level, "event=%s (json serialization failed)", event)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"colum.{name}")
