"""Structured JSON logging (SRS doc 02 §19).

Every record carries: timestamp, module, event, and free-form fields.
Human-readable in development (BL_ENV=development), JSON lines otherwise.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "module": record.name,
            "event": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(module: str) -> "BoundLogger":
    base = logging.getLogger(module)
    if not base.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if os.getenv("BL_ENV", "development") == "development":
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s"))
        else:
            handler.setFormatter(_JsonFormatter())
        base.addHandler(handler)
        base.setLevel(logging.INFO)
        base.propagate = False
    return BoundLogger(base)


class BoundLogger:
    """logger.info("CandleRejected", symbol="XAUUSD", reason="HIGH_BELOW_LOW")"""

    def __init__(self, base: logging.Logger):
        self._base = base

    def _log(self, level: int, event: str, **fields: Any) -> None:
        self._base.log(level, event, extra={"fields": fields or None})

    def info(self, event: str, **fields: Any) -> None:
        self._log(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._base.error(event, exc_info=True, extra={"fields": fields or None})
