"""Centralised logging configuration for PA Agent.

Public API
----------
configure_logging(api_key: str = "") -> None
update_api_key(new_key: str) -> None
verify_logging_handlers() -> bool
"""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

from pa_agent.config.paths import LOG_FILE_PATH
from pa_agent.util.mask_secret import mask_secret

# ── Module-level state ────────────────────────────────────────────────────────

_active_formatters: list[MaskingFormatter] = []
_configured: bool = False

# Shapes that are secrets no matter which config field they came from.  Order
# matters: the longer/more specific patterns run first.
_OBVIOUS_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{12,})"
    r"|(Bearer\s+[A-Za-z0-9._\-]{12,})"
    r"|(/hook/[A-Za-z0-9\-]{12,})"
    r"|([A-Za-z0-9._\-]{24,}\.[A-Za-z0-9._\-]{12,})"
)


def _mask_obvious_secrets(message: str) -> str:
    """Mask token-looking substrings that were not registered explicitly."""

    def _sub(match: re.Match) -> str:
        return mask_secret(match.group(0))

    return _OBVIOUS_SECRET_RE.sub(_sub, message)


# ── MaskingFormatter ──────────────────────────────────────────────────────────


class MaskingFormatter(logging.Formatter):
    """Logging formatter that replaces every known secret with its masked form.

    Besides the API key this covers the Feishu webhook/secret, PushPlus token and
    Tushare token: a failing HTTP request logs its URL, and a Feishu hook URL
    *is* the credential.  Any obvious secret shape (sk-..., Bearer ...,
    /hook/<token>) is masked as a fallback for values we were never told about.
    """

    def __init__(self, fmt: str, api_key: str = "") -> None:
        super().__init__(fmt)
        self._api_key = ""
        self._secrets: set[str] = set()
        self.set_api_key(api_key)

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        for secret in self._secrets:
            message = message.replace(secret, mask_secret(secret))
        return _mask_obvious_secrets(message)

    def set_api_key(self, new_key: str) -> None:
        self._api_key = str(new_key or "")
        if len(self._api_key) >= 4:
            self._secrets.add(self._api_key)

    def register_secret(self, secret: str) -> None:
        """Add one more value to mask (too-short values are ignored)."""
        value = str(secret or "").strip()
        if len(value) >= 4:
            self._secrets.add(value)


# ── Public functions ──────────────────────────────────────────────────────────

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

_THIRD_PARTY_LOGGERS = ("urllib3", "openai", "httpx")

# tvdatafeed opens a websocket every refresh tick and logs at DEBUG — keep quiet.
# NOTE: never put the bare name "root" in this list.  On Python >= 3.9
# logging.getLogger("root") returns the REAL root logger, so levelling it here
# would silence the entire application (it silently dropped every INFO record
# from the file log).  tvDatafeed's direct-to-root chatter is filtered
# per-record by _RootDirectNoiseFilter instead.
_QUIET_LOGGER_NAMES = (
    "urllib3",
    "openai",
    "httpx",
    "tvDatafeed",
    "tvDatafeed.main",
    "websocket",
)


class _RootDirectNoiseFilter(logging.Filter):
    """Drop sub-WARNING records emitted directly on the root logger.

    tvDatafeed logs websocket traffic via ``logging.getLogger("root")``, which
    resolves to the real root logger on modern CPython.  Records coming from
    application loggers keep their own name and are never affected — only
    records whose name is literally "root" (third-party direct root logging)
    are filtered below WARNING.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "root":
            return record.levelno >= logging.WARNING
        return True


def verify_logging_handlers() -> bool:
    """Return True when the expected rotating file handler is attached to root."""
    expected = str(LOG_FILE_PATH.resolve())
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            base = getattr(handler, "baseFilename", "")
            if str(Path(base).resolve()) == expected:
                return True
    return False


def configure_logging(api_key: str = "") -> None:
    """Configure the root logger with rotating file handler and console handler.

    Both handlers use MaskingFormatter that replaces api_key with mask_secret(api_key).
    Third-party loggers (urllib3, openai, httpx) are also attached to the same handlers.

    If handlers were removed after a prior configure_logging call, re-attaches them.
    """
    global _configured

    if _configured:
        if api_key:
            update_api_key(api_key)
        if verify_logging_handlers():
            return
        # Handlers missing (e.g. external code cleared root.handlers) — re-install.
        _configured = False

    # Build formatters
    file_formatter = MaskingFormatter(_LOG_FORMAT, api_key=api_key)
    console_formatter = MaskingFormatter(_LOG_FORMAT, api_key=api_key)

    # Track all active formatters so update_api_key can reach them
    _active_formatters.clear()
    _active_formatters.append(file_formatter)
    _active_formatters.append(console_formatter)

    # Rotating file handler
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)

    # Console (stream) handler — INFO+ only; file keeps DEBUG for troubleshooting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    root_noise_filter = _RootDirectNoiseFilter()
    for handler in (file_handler, console_handler):
        handler.addFilter(root_noise_filter)

    handlers: list[logging.Handler] = [file_handler, console_handler]

    # Configure root logger
    root_logger = logging.getLogger()
    logging.disable(logging.NOTSET)
    root_logger.setLevel(logging.DEBUG)
    # Remove any previously installed handlers to avoid duplicates on re-call
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    for h in handlers:
        root_logger.addHandler(h)

    # Attach the same handlers to third-party loggers
    for name in _THIRD_PARTY_LOGGERS:
        tp_logger = logging.getLogger(name)
        for h in list(tp_logger.handlers):
            tp_logger.removeHandler(h)
        for h in handlers:
            tp_logger.addHandler(h)
        # Prevent double-logging via root propagation
        tp_logger.propagate = False

    _silence_noisy_libraries()

    _configured = True
    logging.getLogger("pa_agent.diagnostics").info(
        "configure_logging: handlers attached (log_file=%s)", LOG_FILE_PATH
    )


def _silence_noisy_libraries() -> None:
    """Turn down chatty third-party DEBUG loggers (tvdatafeed websocket spam)."""
    for name in _QUIET_LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.WARNING)


def mask_known_secrets_in_text(text: str) -> str:
    """Mask every registered secret plus obvious token shapes in *text*.

    Used for files that bypass ``MaskingFormatter`` (faulthandler dumps).
    """
    result = text
    for formatter in _active_formatters:
        for secret in getattr(formatter, "_secrets", ()):
            result = result.replace(secret, mask_secret(secret))
    return _mask_obvious_secrets(result)


def update_api_key(new_key: str) -> None:
    """Update the masking key in all active MaskingFormatter instances."""
    for formatter in _active_formatters:
        formatter.set_api_key(new_key)


def register_secret(secret: str) -> None:
    """Register one more secret value (Feishu/PushPlus/Tushare) for masking."""
    for formatter in _active_formatters:
        formatter.register_secret(secret)


def register_settings_secrets(settings: object | None) -> None:
    """Register every credential carried by *settings* with the formatters.

    ``configure_logging`` only knows the API key at startup; notification and
    data-source credentials are loaded at the same time but were never masked,
    so a failing Feishu request logged the full hook URL (the credential) in
    clear text.

    Each value also lands in the shared disk-secret registry so on-disk
    writers (PendingWriter, debug exports) mask the same set as the log
    formatter — the two sets used to diverge and follow-up records kept
    plaintext tokens.
    """
    if settings is None:
        return
    from pa_agent.util.mask_secret import register_disk_secret

    provider = getattr(settings, "provider", None)
    feishu = getattr(settings, "feishu", None)
    pushplus = getattr(settings, "pushplus", None)
    tushare = getattr(settings, "tushare", None)
    values = [
        getattr(provider, "api_key", ""),
        getattr(feishu, "webhook_url", ""),
        getattr(feishu, "secret", ""),
        getattr(feishu, "app_secret", ""),
        getattr(pushplus, "token", ""),
        getattr(tushare, "token", ""),
    ]
    for value in values:
        text = str(value or "")
        register_secret(text)
        register_disk_secret(text)
