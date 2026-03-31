import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

class _CloudFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": getattr(record, "levelname", "INFO"),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
        }
        for key, val in record.__dict__.items():
            if key not in ("msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process", "taskName", "name", "message"):
                payload[key] = val
        return json.dumps(payload, default=str)

class _StructuredAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.pop("extra", {})
        keys_to_move = [k for k in kwargs.keys() if k not in ("exc_info", "stack_info", "stacklevel")]
        for k in keys_to_move:
            extra[k] = kwargs.pop(k)
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