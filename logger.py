"""
logger.py — Structured JSON logging for Google Cloud Logging.

Cloud Logging ingests JSON log lines written to stdout/stderr and maps:
  "severity"  → log level
  "message"   → main log text
  "httpRequest" → request metadata (auto-displayed in Logs Explorer)

All extra kwargs passed to log calls are added as jsonPayload fields.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class _CloudFormatter(logging.Formatter):
    """Emit one JSON object per log record, compatible with Cloud Logging."""

    SEVERITY_MAP = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "severity": self.SEVERITY_MAP.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
        }

        # Attach any extra fields the caller passed in
        for key, val in record.__dict__.items():
            if key not in (
                "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "taskName", "name",
                "message",
            ):
                payload[key] = val

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_CloudFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    return logger
