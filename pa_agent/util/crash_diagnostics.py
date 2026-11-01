"""Fatal crash diagnostics: faulthandler dump file for native/Qt crashes."""
from __future__ import annotations

import faulthandler
import logging
import signal
from pathlib import Path

from pa_agent.config.paths import CRASH_LOG_PATH, LOG_FILE_PATH

logger = logging.getLogger(__name__)

_crash_file = None
_enabled = False

# faulthandler writes straight to the file descriptor, so MaskingFormatter never
# sees it.  Keep the file bounded and scrub secrets from the previous run before
# appending new dumps.
_CRASH_LOG_MAX_BYTES = 5 * 1024 * 1024


def _scrub_crash_log() -> None:
    """Mask known secrets in an existing crash.log (previous run leftovers)."""
    try:
        if not CRASH_LOG_PATH.exists():
            return
        size = CRASH_LOG_PATH.stat().st_size
        if size > _CRASH_LOG_MAX_BYTES:
            CRASH_LOG_PATH.replace(CRASH_LOG_PATH.with_suffix(".log.1"))
            return
        if size == 0:
            return
        from pa_agent.util.logging import mask_known_secrets_in_text

        original = CRASH_LOG_PATH.read_text(encoding="utf-8", errors="replace")
        scrubbed = mask_known_secrets_in_text(original)
        if scrubbed != original:
            CRASH_LOG_PATH.write_text(scrubbed, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - best effort
        logger.debug("crash.log scrub skipped: %s", exc)


def enable_crash_diagnostics() -> None:
    """Write Python/native stack traces to logs/crash.log on fatal errors."""
    global _crash_file, _enabled  # noqa: PLW0603

    if _enabled:
        return

    CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _scrub_crash_log()
    _crash_file = open(CRASH_LOG_PATH, "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(file=_crash_file, all_threads=True)
    if hasattr(faulthandler, "register"):
        try:
            faulthandler.register(signal.SIGTERM, file=_crash_file, all_threads=True)
        except (AttributeError, OSError, ValueError):
            pass
    _enabled = True
    logger.info("faulthandler enabled → %s", CRASH_LOG_PATH)


def _log_file_handler_attached(root: logging.Logger) -> bool:
    """True when our RotatingFileHandler for pa_agent.log is on the root logger."""
    from logging.handlers import RotatingFileHandler

    expected = str(Path(LOG_FILE_PATH).resolve())
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            base = getattr(handler, "baseFilename", "")
            if str(Path(base).resolve()) == expected:
                return True
    return False


def log_startup_diagnostics() -> None:
    """Emit one INFO line confirming logging + crash dump paths (call after configure_logging)."""
    root = logging.getLogger()
    file_ok = _log_file_handler_attached(root)
    logger.info(
        "startup diagnostics: log_file=%s handler_attached=%s crash_file=%s faulthandler=%s",
        LOG_FILE_PATH,
        file_ok,
        CRASH_LOG_PATH,
        _enabled,
    )
    if not file_ok:
        logger.warning(
            "RotatingFileHandler for %s missing from root logger — file logging may be broken",
            LOG_FILE_PATH,
        )
