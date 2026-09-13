"""Structured log fields stay secret-free."""

from __future__ import annotations

import json
import logging

from qq_ai_bot.logging import JsonFormatter


def test_json_formatter_never_serializes_exception_text() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("https://example.invalid/?token=SYNTHETIC_SECRET_ONLY")
    except ValueError as exc:
        record = logging.LogRecord(
            name="qq_ai_bot.services.processor",
            level=logging.ERROR,
            pathname="processor.py",
            lineno=1,
            msg="turn_internal_failure exception_category=%s",
            args=(type(exc).__name__,),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    payload = json.loads(formatter.format(record))
    serialized = json.dumps(payload)
    assert payload["exception_category"] == "ValueError"
    assert "exception_message" not in payload
    assert "exception_traceback" not in payload
    assert "SYNTHETIC_SECRET_ONLY" not in serialized
