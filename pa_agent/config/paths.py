"""Centralised path constants for PA Agent.

All runtime directories are rooted at PROJECT_ROOT.
Import this module everywhere instead of hard-coding paths.
"""
from __future__ import annotations

import re
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

# ── Root ──────────────────────────────────────────────────────────────────────
# Resolve dynamically: this file is pa_agent/config/paths.py, so go up 3 levels.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# ── Prompt engineering assets (read-only at runtime) ─────────────────────────
PROMPT_DIR: Path = PROJECT_ROOT / "prompt_engineering"

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
