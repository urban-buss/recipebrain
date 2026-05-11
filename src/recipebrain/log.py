"""Structured logging setup for recipebrain.

Provides a JSON log formatter and rotating file handler alongside a concise
console handler. Call ``setup_logging()`` once at application startup (CLI).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

__all__ = ["setup_logging"]

_DEFAULT_LOG_DIR = "logs"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(
    *,
    level: int = logging.INFO,
    log_dir: str | Path | None = _DEFAULT_LOG_DIR,
    enable_file: bool = True,
) -> None:
    """Configure root logger with console and optional rotating file handler.

    Args:
        level: Logging level for both handlers.
        log_dir: Directory for log files. Created if absent.
        enable_file: If False, skip the file handler (useful in tests).
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    root.handlers.clear()

    # Console — human-readable
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(console)

    # File — JSON, rotating
    if enable_file and log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path / "recipebrain.log",
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
