"""Shared test configuration.

The GUI test suite runs on PyQt6.  Set ``PYTEST_QT_API`` before pytest-qt loads
so the plugin does not probe (and import) PyQt5 first: on Windows, loading
Qt5 and Qt6 bindings in the same process makes the later PyQt6 import fail
with ``DLL load failed while importing QtCore``.
"""
from __future__ import annotations

import os

os.environ["PYTEST_QT_API"] = "pyqt6"
