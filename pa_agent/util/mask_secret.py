"""Secret masking utility (standalone, no dependencies)."""

import threading


def mask_secret(s: str) -> str:
    """Return s with all but the last 4 characters replaced by '*'.

    If len(s) < 4, return s unchanged (including empty string).
    """
    if len(s) < 4:
        return s
    return "*" * (len(s) - 4) + s[-4:]


# ---------------------------------------------------------------------------
# Shared disk-secret registry
#
# The log formatter (util/logging.py) and every on-disk writer (records/
# pending_writer.py, debug exports) must mask the SAME set of credentials.
# The sets previously diverged: the formatter learned feishu/pushplus/tushare
# tokens while PendingWriter._sanitize only ever knew provider.api_key, so a
# webhook URL pasted into the follow-up box landed in records in plaintext.
# ---------------------------------------------------------------------------

_REGISTRY_LOCK = threading.Lock()
_DISK_SECRETS: set[str] = set()


def register_disk_secret(value: object) -> None:
    """Register one credential for on-disk masking (no-op for empty values)."""
    text = str(value or "")
    if text:
        with _REGISTRY_LOCK:
            _DISK_SECRETS.add(text)


def registered_disk_secrets() -> tuple[str, ...]:
    """Snapshot of every registered secret (thread-safe copy)."""
    with _REGISTRY_LOCK:
        return tuple(_DISK_SECRETS)


def clear_disk_secrets() -> None:
    """Drop every registered secret (test isolation / credential wipe)."""
    with _REGISTRY_LOCK:
        _DISK_SECRETS.clear()
