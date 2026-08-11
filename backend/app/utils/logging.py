"""Structured logging helper. Never log secrets/tokens."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.config import get_settings

_CONFIGURED = False


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def get_logger(name: str = "app") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        level = getattr(logging, get_settings().LOG_LEVEL.upper(), logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        root = logging.getLogger("app")
        root.setLevel(level)
        root.addHandler(handler)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(f"app.{name}" if not name.startswith("app.") else name)
