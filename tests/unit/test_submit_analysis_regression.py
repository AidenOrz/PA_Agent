"""Regression tests for the 「提交分析」 submit path (2026-09 code review fixes).

Root cause being locked in: WeStock rewrites a bare 6-digit code inside
``subscribe`` ("002475" → "sz002475").  The submit path used to compare the
raw combo text against the stored subscription, so EVERY click of 提交分析
re-triggered a symbol switch and the analysis never started.

Also covered:
- submit must refuse loudly (visible reason) when the data source is
  disconnected instead of silently returning;
- wait-for-close submit must fall back to a background fetch when no bars
  are cached, instead of giving up with a status message;
- ``_check_auto_incremental`` must never arm auto analysis after a switch.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QMainWindow  # noqa: E402

from pa_agent.app_context import AppContext  # noqa: E402
from pa_agent.config.settings import Settings  # noqa: E402
from pa_agent.data.base import KlineBar  # noqa: E402
from pa_agent.data.westock_source import WeStockSource  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────


class _RawStorageSource:
    """Source without canonical_* overrides (MT5/TV-like: stores input verbatim)."""

    def __init__(self, symbol: str, timeframe: str) -> None:
        self._symbol = symbol
        self._timeframe = timeframe
        self._connected = True

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "1h", "4h", "1d"]


class _StubBarsSource:
    """Minimal connected source returning fabricated 1h bars for the fetch test."""

    _connected = True

    def __init__(self, bars: list[KlineBar]) -> None:
        self._bars = bars

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        return list(self._bars[: max(0, n)])


def _make_window(qtbot, data_source) -> QMainWindow:
    """Build a MainWindow wired to a stub context (no network, no dialogs)."""
    from pa_agent.gui.main_window import MainWindow

    ctx = AppContext()
    ctx.settings = Settings()
    ctx.settings.provider.api_key = "sk-regression-test-key"
    ctx.data_source = data_source

    window = MainWindow(ctx=ctx)
    qtbot.addWidget(window)
    # Startup QTimer callbacks must not pop the API-key dialog mid-test.
    window._on_startup_api_key_check()
    return window


def _patch_submit_targets(window) -> tuple[MagicMock, MagicMock]:
    start = MagicMock()
    switch = MagicMock()
    window._start_analysis = start
    window._on_symbol_or_tf_changed = switch
    return start, switch


# ── Data layer: canonical hooks mirror subscribe() storage ────────────────────


def test_westock_canonical_symbol_matches_subscribe_storage():
    """The canonical compare only helps if it reproduces what subscribe stores."""
    ws = WeStockSource()
    ws.subscribe("002475", "1d")
    assert ws._symbol == "sz002475"  # subscribe rewrites bare codes
    assert ws.canonical_symbol("002475") == ws._symbol
    assert ws.canonical_timeframe("1d") == ws._timeframe


def test_westock_canonical_prefixed_code_is_stable():
    ws = WeStockSource()
    ws.subscribe("sh600519", "1w")
    assert ws.canonical_symbol("sh600519") == ws._symbol == "sh600519"
    assert ws.canonical_timeframe("1w") == ws._timeframe


# ── P0: submit with an unchanged (normalized-equal) symbol must analyze ──────


def test_westock_bare_code_submit_starts_analysis(qtbot):
    """2026-09 regression: '002475' vs stored 'sz002475' dead-locked the button."""
    ws = WeStockSource()
    ws._connected = True
    ws.subscribe("002475", "1d")

    window = _make_window(qtbot, ws)
    start, switch = _patch_submit_targets(window)
    window._symbol_combo.setCurrentText("002475")
    window._tf_combo.setCurrentText("1d")

    window._begin_submit_analysis(force_incremental=False)

    assert switch.call_count == 0, "unchanged symbol must not re-trigger a switch"
    assert start.call_count == 1
    args = start.call_args
    assert args.args[0] == "002475"
    assert args.args[1] == "1d"


def test_westock_normalized_input_also_starts_analysis(qtbot):
    ws = WeStockSource()
    ws._connected = True
    ws.subscribe("002475", "1d")

    window = _make_window(qtbot, ws)
    start, switch = _patch_submit_targets(window)
    window._symbol_combo.setCurrentText("sz002475")
    window._tf_combo.setCurrentText("1d")

    window._begin_submit_analysis(force_incremental=False)

    assert switch.call_count == 0
    assert start.call_count == 1


def test_westock_changed_symbol_still_switches(qtbot):
    """A genuinely different symbol must keep taking the switch branch."""
    ws = WeStockSource()
    ws._connected = True
    ws.subscribe("sh600519", "1d")

    window = _make_window(qtbot, ws)
    start, switch = _patch_submit_targets(window)
    window._symbol_combo.setCurrentText("000001")

    window._begin_submit_analysis(force_incremental=False)

    assert start.call_count == 0
    assert switch.call_count == 1
    assert switch.call_args.args[0] == "000001"


def test_raw_storage_source_keeps_exact_compare(qtbot):
    """Sources without canonical hooks must behave exactly as before.

    Note: the tf combo's currentTextChanged signal triggers a switch by
    design, so this test leaves both combos untouched — the stub is built to
    match the combo defaults (symbol XAUUSDm / tf 15m from Settings defaults).
    """
    ds = _RawStorageSource("XAUUSDm", "15m")

    window = _make_window(qtbot, ds)
    start, switch = _patch_submit_targets(window)

    window._begin_submit_analysis(force_incremental=False)

    assert switch.call_count == 0
    assert start.call_count == 1
    assert start.call_args.args[0] == "XAUUSDm"


def test_raw_storage_source_changed_symbol_still_switches(qtbot):
    """Exact-compare sources keep taking the switch branch on a new symbol."""
    ds = _RawStorageSource("EURUSD", "15m")

    window = _make_window(qtbot, ds)
    start, switch = _patch_submit_targets(window)
    # Symbol combo text changes do NOT emit the switch signal by design.
    window._symbol_combo.setCurrentText("XAUUSDm")

    window._begin_submit_analysis(force_incremental=False)

    assert start.call_count == 0
    assert switch.call_count == 1
    assert switch.call_args.args[0] == "XAUUSDm"


# ── P1: disconnected data source blocks submit with a visible reason ─────────


def test_submit_blocked_and_explained_when_source_disconnected(qtbot):
    ws = WeStockSource()
    ws._connected = False
    ws.subscribe("002475", "1d")

    window = _make_window(qtbot, ws)
    start, switch = _patch_submit_targets(window)
    window._symbol_combo.setCurrentText("002475")

    window._begin_submit_analysis(force_incremental=False)

    reason = window._submit_block_reason()
    assert reason is not None and "数据源未连接" in reason
    assert "数据源未连接" in window._status_bar.currentMessage()
    assert "提交分析已锁定" in window._status_bar.currentMessage()
    assert start.call_count == 0
    assert switch.call_count == 0


# ── P2: wait-for-close with empty cache falls back to a background fetch ─────


def _fabricated_hour_bars(count: int) -> list[KlineBar]:
    """Newest-first 1h bars; head bar is forming (opened 10 minutes ago)."""
    now_ms = int(time.time() * 1000)
    head_open = now_ms - 10 * 60 * 1000
    bars = [
        KlineBar(
            seq=0,
            ts_open=head_open,
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=10.0,
            closed=False,
        )
    ]
    for i in range(1, count):
        bars.append(
            KlineBar(
                seq=i,
                ts_open=head_open - i * 3_600_000,
                open=2000.0,
                high=2010.0,
                low=1995.0,
                close=2005.0,
                volume=10.0,
                closed=True,
            )
        )
    return bars


def test_wait_close_with_empty_cache_fetches_then_arms(qtbot):
    bars = _fabricated_hour_bars(150)
    ds = _StubBarsSource(bars)

    window = _make_window(qtbot, ds)
    start, _switch = _patch_submit_targets(window)
    window._last_frame_ready_bars = None
    window._wait_close_checkbox.setChecked(False)

    handled = window._arm_wait_for_bar_close("XAUUSD", "1h", 100)

    assert handled is True
    # The background fetch arms the wait once bars arrive (no silent give-up).
    qtbot.waitUntil(
        lambda: window._pending_submit_after_close, timeout=10_000
    )
    assert window._pending_submit_symbol == "XAUUSD"
    assert window._pending_submit_timeframe == "1h"
    assert start.call_count == 0  # armed, not started — bar is still forming
    window._clear_pending_bar_close_wait()
    window._cancel_snapshot_fetch_worker(join_ms=2000)


# ── P2: _check_auto_incremental must not arm auto analysis ───────────────────


def test_check_auto_incremental_only_hints_never_arms(qtbot, monkeypatch):
    import pa_agent.records.analysis_history as history

    monkeypatch.setattr(
        history, "find_latest_successful_record", lambda **kwargs: object()
    )

    window = _make_window(qtbot, WeStockSource())

    window._check_auto_incremental("002475", "1d")

    assert window._auto_incremental_pending is False
    assert "增量分析" in window._status_bar.currentMessage()
