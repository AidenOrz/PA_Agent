"""Regression tests for the 2026-09 logging fix.

Root cause: ``_QUIET_LOGGER_NAMES`` contained the bare name ``"root"``.
On Python >= 3.9 ``logging.getLogger("root")`` returns the REAL root logger,
so ``_silence_noisy_libraries`` levelled the whole application down to
WARNING and every INFO/DEBUG record silently vanished from the log file.
"""
from __future__ import annotations

import logging
import logging.handlers

import pytest

import pa_agent.util.logging as logging_module
from pa_agent.config.paths import LOG_FILE_PATH
from pa_agent.util.logging import (
    _RootDirectNoiseFilter,
    _QUIET_LOGGER_NAMES,
    configure_logging,
)


@pytest.fixture
def restored_root_logging():
    """Snapshot root logging state and restore it after the test."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def _force_full_configure() -> None:
    # Bypass the _configured early-return so the test always exercises the
    # full (re)configuration path, regardless of test execution order.
    logging_module._configured = False
    configure_logging()


def test_root_logger_stays_debug_after_configure(restored_root_logging):
    _force_full_configure()
    assert logging.getLogger().level == logging.DEBUG


def test_quiet_list_never_contains_root_name():
    """Guards the regression: 'root' must never be levelled down again."""
    assert "root" not in _QUIET_LOGGER_NAMES


def test_handlers_carry_the_root_noise_filter(restored_root_logging):
    _force_full_configure()
    handlers = logging.getLogger().handlers
    file_handlers = [
        h
        for h in handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert file_handlers, "rotating file handler must be attached to root"
    for handler in file_handlers:
        assert any(
            isinstance(f, _RootDirectNoiseFilter) for f in handler.filters
        ), "file handler must filter direct-to-root chatter per record"


def test_root_noise_filter_scope(restored_root_logging):
    f = _RootDirectNoiseFilter()

    def _record(name: str, level: int) -> logging.LogRecord:
        return logging.LogRecord(name, level, "path", 1, "msg", None, None)

    # tvDatafeed's direct-to-root chatter (DEBUG/INFO) is dropped...
    assert f.filter(_record("root", logging.DEBUG)) is False
    assert f.filter(_record("root", logging.INFO)) is False
    # ...but its warnings still pass...
    assert f.filter(_record("root", logging.WARNING)) is True
    # ...and application records are never affected, at any level.
    assert f.filter(_record("pa_agent", logging.DEBUG)) is True
    assert f.filter(_record("pa_agent.gui.main_window", logging.INFO)) is True


def test_info_record_reaches_log_file(restored_root_logging):
    _force_full_configure()
    probe = logging.getLogger("pa_agent.tests.info_probe")
    marker = "INFO-REACHES-FILE-marker-20260905"
    probe.info(marker)
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = LOG_FILE_PATH.read_text(encoding="utf-8", errors="replace")
    assert marker in content
