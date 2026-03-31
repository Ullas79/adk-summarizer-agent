"""
logger.py — Structured JSON logging for Google Cloud Logging.

Supports logging calls like:
  log.info("message", request_id="...", project="...")
without crashing on unexpected keyword arguments.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _CloudFormatter(logging.Formatter):
    """Emit one JSON object per log record, compatible with Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "severity": getattr(record, "levelname", "INFO"),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
        }

        skip_keys = {
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
            "name",
            "message",
        }

        for key, val in record.__dict__.items():
            if key not in skip_keys:
                payload[key] = val

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class _StructuredAdapter(logging.LoggerAdapter):
    """Move arbitrary keyword arguments into `extra` for structured logging."""

    def process(self, msg, kwargs):
        extra = kwargs.pop("extra", {}) or {}
        reserved = {"exc_info", "stack_info", "stacklevel"}
        keys_to_move = [k for k in list(kwargs.keys()) if k not in reserved]
        for key in keys_to_move:
            extra[key] = kwargs.pop(key)
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str) -> logging.LoggerAdapter:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_CloudFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    logger.setLevel(logging.INFO)
    return _StructuredAdapter(logger, {})
