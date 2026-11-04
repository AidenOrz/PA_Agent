"""Centralised path constants for PA Agent.

All runtime directories are rooted at PROJECT_ROOT.
Import this module everywhere instead of hard-coding paths.

Two roots exist because the packaged (PyInstaller) build keeps read-only
assets inside _internal/ while user data must live next to the .exe:

* PROJECT_ROOT — where the app *writes* (config/records/logs/...).
  In a source checkout this is the repository root; in a frozen build it is
  the folder that contains PA_Agent.exe.
* BUNDLE_ROOT — where read-only assets ship (prompt_engineering).
  In a source checkout this equals PROJECT_ROOT; frozen it is sys._MEIPASS.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_INVALID_FILENAME_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def sanitize_filename_component(value: object, *, fallback: str = "unknown") -> str:
    """Return a single safe filename component for runtime record paths.

    Separators, Windows-invalid characters, control characters, and repeated
    dots are replaced so caller-controlled identifiers cannot escape the
    directory that owns the resulting file.
    """
    text = "" if value is None else str(value).strip()
    text = _INVALID_FILENAME_COMPONENT_CHARS.sub("-", text)
    text = text.replace("..", "-").strip(" .-")
    return text or fallback


def _is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def _source_root() -> Path:
    """Repository root in a source checkout.

    Resolve dynamically: this file is pa_agent/config/paths.py, so go up 3 levels.
    """
    return Path(__file__).resolve().parent.parent.parent


def _runtime_root() -> Path:
    """Directory that owns user-writable data."""
    if _is_frozen():
        # dist/PA_Agent/PA_Agent.exe -> dist/PA_Agent
        return Path(sys.executable).resolve().parent
    return _source_root()


def _bundle_root() -> Path:
    """Directory that owns read-only bundled assets."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _source_root()


# ── Roots ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = _runtime_root()
BUNDLE_ROOT: Path = _bundle_root()


def _prompt_dir() -> Path:
    """Prompt .txt assets: next to the exe when unpacked there, else bundled."""
    override = os.environ.get("PA_AGENT_PROMPT_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    for base in (PROJECT_ROOT, BUNDLE_ROOT):
        candidate = base / "prompt_engineering"
        if candidate.is_dir():
            return candidate
    return PROJECT_ROOT / "prompt_engineering"


# ── Prompt engineering assets (read-only at runtime) ─────────────────────────
PROMPT_DIR: Path = _prompt_dir()

# Alias kept for backward compat with design doc
PA_AGENT_DIR: Path = PROJECT_ROOT

# ── Runtime write directories ─────────────────────────────────────────────────
RECORDS_PENDING_DIR: Path = PROJECT_ROOT / "records" / "pending"
TRADE_RECORDS_DIR: Path = PROJECT_ROOT / "trade_records"
EXPERIENCE_DIR: Path = PROJECT_ROOT / "experience"
CONFIG_DIR: Path = PROJECT_ROOT / "config"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# ── Individual file paths ─────────────────────────────────────────────────────
FEISHU_JSON_LEGACY_PATH: Path = CONFIG_DIR / "feishu.json"
SETTINGS_JSON_PATH: Path = CONFIG_DIR / "settings.json"
LOG_FILE_PATH: Path = LOGS_DIR / "pa_agent.log"
CRASH_LOG_PATH: Path = LOGS_DIR / "crash.log"
