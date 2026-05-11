"""Tests for recipebrain.log — structured logging setup."""

from __future__ import annotations

import json
import logging

from recipebrain.log import JsonFormatter, setup_logging


class TestJsonFormatter:
    def test_formats_as_json(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        line = fmt.format(record)
        data = json.loads(line)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["logger"] == "test"
        assert "ts" in data

    def test_includes_exception(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="fail",
                args=(),
                exc_info=exc_info,
            )
        line = fmt.format(record)
        data = json.loads(line)
        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestSetupLogging:
    def test_configures_console_handler(self):
        setup_logging(enable_file=False)
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_configures_file_handler(self, tmp_path):
        setup_logging(log_dir=tmp_path, enable_file=True)
        root = logging.getLogger()
        assert len(root.handlers) == 2
        log_file = tmp_path / "recipebrain.log"
        assert log_file.exists()

    def test_no_duplicate_handlers_on_repeated_calls(self):
        setup_logging(enable_file=False)
        setup_logging(enable_file=False)
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_file_handler_writes_json(self, tmp_path):
        setup_logging(log_dir=tmp_path, enable_file=True)
        logger = logging.getLogger("test.file")
        logger.info("test message")
        # Flush handlers
        for h in logging.getLogger().handlers:
            h.flush()
        log_file = tmp_path / "recipebrain.log"
        content = log_file.read_text(encoding="utf-8")
        lines = [line for line in content.strip().splitlines() if line.strip()]
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data["message"] == "test message"
