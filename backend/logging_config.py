from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


_SAFE_EXTRA_FIELDS = (
    "request_id",
    "http_method",
    "http_path",
    "http_status",
    "duration_ms",
    "error_type",
)


class JsonLogFormatter(logging.Formatter):
    """Emit machine-readable logs while allowing only explicitly safe fields."""

    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _SAFE_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                event[field] = value
        return json.dumps(event, separators=(",", ":"), ensure_ascii=False)


def configure_logging() -> None:
    """Set the root logger to JSON without replacing application handlers."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))
    for handler in root.handlers:
        handler.setFormatter(JsonLogFormatter())
