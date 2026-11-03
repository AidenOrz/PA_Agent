"""GUI 数据源下拉与注册表保持一致（新增数据源自动出现、无重复维护）。"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from pa_agent.app_context import AppContext
from pa_agent.config.settings import Settings
from pa_agent.data.factory import DATA_SOURCE_CHOICES
from pa_agent.data.sources_registry import (
    DOMESTIC_A_SHARE_KINDS,
    SOURCE_SPECS,
    min_refresh_interval_ms,
    source_placeholder,
)
from pa_agent.gui import main_window as mw


class _StubSource:
    """离线数据源替身（窗口构造期间不会联网）。"""

    _connected = True

    def __init__(self, symbol: str = "XAUUSDm", timeframe: str = "15m") -> None:
        self._symbol = symbol
        self._timeframe = timeframe

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "1h", "4h", "1d"]

    def canonical_symbol(self, symbol: str) -> str:
        return symbol

    def canonical_timeframe(self, timeframe: str) -> str:
        return timeframe

    def subscribe(self, symbol: str, timeframe: str) -> None:
        self._symbol = symbol
        self._timeframe = timeframe

    def unsubscribe(self) -> None:
        pass

    def list_symbols(self) -> list[str]:
        return [self._symbol]

    def latest_snapshot(self, n: int) -> list:
        return []


def _make_window(qtbot, kind: str = "mt5"):
    ctx = AppContext()
    ctx.settings = Settings()
    ctx.settings.provider.api_key = "sk-registry-key"
    ctx.settings.general.last_data_source = kind  # type: ignore[assignment]
    ctx.data_source = _StubSource()
    window = mw.MainWindow(ctx=ctx)
    qtbot.addWidget(window)
    return window


def test_combo_lists_every_visible_source_in_registry_order(qtbot) -> None:
    window = _make_window(qtbot)
    combo = window._data_source_combo
    kinds = [combo.itemData(i) for i in range(combo.count())]
    assert kinds == [kind for kind, _ in DATA_SOURCE_CHOICES]
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert labels == [label for _, label in DATA_SOURCE_CHOICES]


def test_new_sources_are_selectable(qtbot) -> None:
    window = _make_window(qtbot)
    combo = window._data_source_combo
    for kind in ("baostock", "binance", "westock"):
        assert combo.findData(kind) >= 0, kind


def test_combo_tooltip_describes_every_visible_source(qtbot) -> None:
    window = _make_window(qtbot)
    tooltip = window._data_source_combo.toolTip()
    for spec in SOURCE_SPECS:
        if spec.ui_visible and spec.tooltip:
            assert spec.tooltip in tooltip, spec.kind


def test_symbol_placeholder_follows_the_active_source(qtbot) -> None:
    window = _make_window(qtbot)
    for kind in ("baostock", "binance", "westock", "tradingview", "mt5"):
        window._active_data_source_kind = kind
        window._apply_data_source_symbol_placeholder()
        expected = source_placeholder(kind) or "输入 MT5 品种名，如 XAUUSDm…"
        assert window._symbol_combo.lineEdit().placeholderText() == expected, kind


def test_refresh_interval_is_clamped_for_throttled_sources(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot)
    captured: dict = {}

    import pa_agent.data.refresh_loop as refresh_loop

    class _FakeLoop:
        def __init__(self, data_source=None, n_bars=0, interval_ms=0, cancel_token=None) -> None:
            captured["interval_ms"] = interval_ms
            self.frame_ready = _Signal()
            self.status_changed = _Signal()

        def start(self) -> None:
            captured["started"] = True

    class _Signal:
        def connect(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(refresh_loop, "RefreshLoop", _FakeLoop)
    window._active_data_source_kind = "baostock"
    window._start_refresh_loop()
    assert captured["interval_ms"] == min_refresh_interval_ms("baostock", 1000) == 2500

    captured.clear()
    window._active_data_source_kind = "mt5"
    window._start_refresh_loop()
    assert captured["interval_ms"] == min_refresh_interval_ms("mt5", 1000) == 1000


def test_domestic_list_drives_the_symbol_default(qtbot) -> None:
    from pa_agent.data.market_defaults import normalize_gold_symbol_for_kind

    for kind in DOMESTIC_A_SHARE_KINDS:
        assert normalize_gold_symbol_for_kind(kind, "btc/usdt") == "000001", kind
    assert normalize_gold_symbol_for_kind("binance", "btc/usdt") == "BTCUSDT"
    assert normalize_gold_symbol_for_kind("mt5", "BTCUSDT") == "XAUUSDm"
