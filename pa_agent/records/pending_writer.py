"""PendingWriter — persists AnalysisRecord and FollowupTurn to disk.

File naming convention:
    {YYYY-MM-DD_HH-MM-SS-mmm}_{symbol}_{timeframe}.json
    {YYYY-MM-DD_HH-MM-SS-mmm}_{symbol}_{timeframe}.followups.jsonl

Disk failures are logged and emitted to the event bus but never propagated.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pa_agent.config.paths import sanitize_filename_component
from pa_agent.records.schema import AnalysisRecord, FollowupTurn
from pa_agent.util.mask_secret import mask_secret

_FOLLOWUP_WRITE_LOCK = threading.RLock()


def _default_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def _ms_to_local_datetime(ms: int) -> datetime:
    """Convert epoch milliseconds to local datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone()


def build_record_id(record: AnalysisRecord) -> str:
    """Build the safe filename stem (without extension) for a record.

    Milliseconds are included so two records created in the same second do
    not overwrite one another.  The timestamp portion intentionally uses
    ``%M`` for minutes; older files with the former ``%m`` spelling remain
    readable because history lookup scans record contents rather than names.
    """
    dt = _ms_to_local_datetime(record.meta.timestamp_local_ms)
    ts_str = dt.strftime("%Y-%m-%d_%H-%M-%S")
    ms_str = f"{dt.microsecond // 1000:03d}"
    symbol = sanitize_filename_component(record.meta.symbol)
    timeframe = sanitize_filename_component(record.meta.timeframe)
    return f"{ts_str}-{ms_str}_{symbol}_{timeframe}"


def _build_basename(record: AnalysisRecord) -> str:
    """Backward-compatible private alias for :func:`build_record_id`."""
    return build_record_id(record)


class PendingWriter:
    """Writes analysis records and followup turns to the pending directory."""

    def __init__(
        self,
        pending_dir: Optional[Path] = None,
        event_bus=None,
        logger: Optional[logging.Logger] = None,
        api_key: str = "",
    ) -> None:
        if pending_dir is None:
            from pa_agent.config.paths import RECORDS_PENDING_DIR
            pending_dir = RECORDS_PENDING_DIR

        self._pending_dir = pending_dir
        self._event_bus = event_bus
        self._logger = logger or _default_logger()
        self._api_key = api_key

        try:
            self._pending_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._logger.error(
                "PendingWriter: failed to create pending directory %s: %s",
                self._pending_dir,
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_full(self, record: AnalysisRecord) -> Path:
        """Serialize and save a complete analysis record.

        Returns the path written to, or a best-effort path on failure.
        """
        basename = build_record_id(record)
        path = self._path_for_filename(f"{basename}.json")
        data = record.model_dump()
        data = self._sanitize(data, self._api_key)
        self._write_json(path, data)
        try:
            from pa_agent.records.analysis_history import invalidate_latest_record_cache

            invalidate_latest_record_cache()
        except (ImportError, OSError) as exc:
            self._logger.debug("PendingWriter: failed to invalidate history cache: %s", exc)
        return path

    def save_partial(self, record: AnalysisRecord, reason: str) -> Path:
        """Serialize and save a partial analysis record with a reason field.

        The ``_partial_reason`` key is injected into the serialized dict
        (it is not part of the Pydantic model).

        Returns the path written to, or a best-effort path on failure.
        """
        basename = build_record_id(record)
        path = self._path_for_filename(f"{basename}.json")
        data = record.model_dump()
        data["_partial_reason"] = reason
        data = self._sanitize(data, self._api_key)
        self._write_json(path, data)
        return path

    def append_followup(self, record_id: str, turn: FollowupTurn) -> None:
        """Append a single followup turn to the JSONL sidecar file.

        ``record_id`` is the basename (without extension) of the record file,
        e.g. ``"2026-05-18_14-00-13_XAUUSD_1h"``.
        """
        safe_record_id = sanitize_filename_component(
            record_id,
            fallback="unknown-record",
        )
        path = self._path_for_filename(f"{safe_record_id}.followups.jsonl")
        line = json.dumps(turn.model_dump(), ensure_ascii=False)
        try:
            with _FOLLOWUP_WRITE_LOCK, path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            self._handle_disk_error(exc, path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize(data: dict, api_key: str) -> dict:
        """Recursively replace any occurrence of *api_key* in string values.

        If *api_key* is empty, returns *data* unchanged.
        Handles nested dicts, lists, and plain string values at any depth.
        """
        if not api_key:
            return data

        masked = mask_secret(api_key)

        def _walk(node):
            if isinstance(node, str):
                return node.replace(api_key, masked)
            if isinstance(node, dict):
                return {k: _walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [_walk(item) for item in node]
            return node

        return _walk(data)

    def _write_json(self, path: Path, data: dict) -> None:
        """Atomically write *data* as pretty-printed JSON to *path*."""
        temp_path: Path | None = None
        open_fd: int | None = None
        try:
            text = json.dumps(data, ensure_ascii=False, indent=2)
            path.parent.mkdir(parents=True, exist_ok=True)
            open_fd, temp_name = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=str(path.parent),
            )
            temp_path = Path(temp_name)
            with os.fdopen(open_fd, "w", encoding="utf-8", newline="") as fh:
                open_fd = None
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_path, path)
            temp_path = None
        except OSError as exc:
            self._handle_disk_error(exc, path)
        finally:
            if open_fd is not None:
                with suppress(OSError):
                    os.close(open_fd)
            if temp_path is not None:
                with suppress(OSError):
                    temp_path.unlink(missing_ok=True)

    def _path_for_filename(self, filename: str) -> Path:
        """Return a path under the pending directory, rejecting escapes."""
        path = self._pending_dir / filename
        root = self._pending_dir.resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(f"pending path escapes directory: {filename!r}") from exc
        return path

    def _handle_disk_error(self, exc: OSError, path: Path) -> None:
        """Log the error and optionally emit to the event bus."""
        self._logger.error(
            "PendingWriter: disk error writing %s: %s", path, exc
        )
        if self._event_bus is not None:
            try:
                self._event_bus.emit("disk_error", {"path": str(path), "error": str(exc)})
            except Exception as bus_exc:  # noqa: BLE001
                self._logger.error(
                    "PendingWriter: event_bus emit failed: %s", bus_exc
                )
