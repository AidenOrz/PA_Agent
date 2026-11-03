"""Shared test configuration.

The GUI test suite runs on PyQt6.  Set ``PYTEST_QT_API`` before pytest-qt loads
so the plugin does not probe (and import) PyQt5 first: on Windows, loading
Qt5 and Qt6 bindings in the same process makes the later PyQt6 import fail
with ``DLL load failed while importing QtCore``.
"""

from __future__ import annotations

import os

import pytest

os.environ["PYTEST_QT_API"] = "pyqt6"


@pytest.fixture(autouse=True)
def _isolated_settings_path(tmp_path, monkeypatch):
    """Point SETTINGS_JSON_PATH at a per-test temp file.

    Several GUI paths call ``save_settings()`` (symbol switch, data-source
    switch, keep-analysis checkbox, the settings dialogs).  With the default
    path the suite rewrote the developer's real ``config/settings.json``:
    test values replaced the saved symbol / bar count, and because
    ``save_settings`` encrypts ``provider.api_key`` with DPAPI the real key
    was replaced by the test key.  Tests must never touch user data.
    """
    from pa_agent.config import paths

    monkeypatch.setattr(paths, "SETTINGS_JSON_PATH", tmp_path / "settings.json")
