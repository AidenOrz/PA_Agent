"""TradingView 连通性探测不得在 GUI 主线程阻塞的回归测试。

缺陷：``_on_fetch_data_clicked`` 曾在主线程同步调用
``check_tradingview_connectivity()``（3 次 × 20s 超时 + 3s 休眠，最坏约 66s），
整段期间窗口冻结。修复后探测跑在 ``_TradingViewProbeWorker`` 后台线程，
结果用信号回主线程；启动预检失败/超时不得阻塞启动流程。

本文件全部使用假的探测函数，既不打网络也不做真实等待。
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

import pa_agent.data.tradingview_connectivity as tv_conn
from pa_agent.app_context import AppContext
from pa_agent.config.settings import Settings
from pa_agent.gui import main_window as mw


class _TvStubSource:
    """TradingView 数据源替身（不联网）。"""

    _connected = True

    # 默认值与 Settings 的 last_symbol / last_timeframe 对齐，否则
    # 「获取数据」会先走品种切换分支，探测根本不会启动。
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

    def latest_snapshot(self, n: int) -> list:
        return []


def _make_window(qtbot):
    ctx = AppContext()
    ctx.settings = Settings()
    ctx.settings.provider.api_key = "sk-tv-key"
    ctx.data_source = _TvStubSource()
    window = mw.MainWindow(ctx=ctx)
    qtbot.addWidget(window)
    window._active_data_source_kind = "tradingview"
    return window


def _patch_probe(monkeypatch, func) -> None:
    monkeypatch.setattr(tv_conn, "check_tradingview_connectivity", func)


def test_probe_worker_emits_result(qtbot, monkeypatch) -> None:
    """worker 只负责调用探测并把 (ok, detail) 通过信号送回。"""
    _patch_probe(monkeypatch, lambda **kwargs: (True, None))
    worker = mw._TradingViewProbeWorker()
    results: list[tuple[bool, str]] = []
    worker.probe_finished.connect(lambda ok, detail: results.append((ok, detail)))
    worker.start()
    assert worker.wait(10_000)
    qtbot.wait(50)
    assert results == [(True, "")]


def test_probe_worker_reports_failure_detail(qtbot, monkeypatch) -> None:
    """失败时 detail 必须传到主线程（用户才知道为什么拿不到数据）。"""
    _patch_probe(monkeypatch, lambda **kwargs: (False, "连接超时"))
    worker = mw._TradingViewProbeWorker()
    results: list[tuple[bool, str]] = []
    worker.probe_finished.connect(lambda ok, detail: results.append((ok, detail)))
    worker.start()
    assert worker.wait(10_000)
    qtbot.wait(50)
    assert results == [(False, "连接超时")]


def test_probe_worker_swallows_exceptions(qtbot, monkeypatch) -> None:
    """探测代码抛异常也必须变成一次「失败」而不是崩掉线程。"""

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    _patch_probe(monkeypatch, _boom)
    worker = mw._TradingViewProbeWorker()
    results: list[tuple[bool, str]] = []
    worker.probe_finished.connect(lambda ok, detail: results.append((ok, detail)))
    worker.start()
    assert worker.wait(10_000)
    qtbot.wait(50)
    assert results and results[0][0] is False
    assert "kaboom" in results[0][1]


def test_fetch_click_returns_immediately_while_probe_runs(qtbot, monkeypatch) -> None:
    """核心回归：点「获取数据」必须立刻返回，探测在后台线程里跑。"""
    release = threading.Event()

    def _slow_probe(**kwargs):
        release.wait(10.0)  # 模拟 socket 阻塞
        return True, None

    _patch_probe(monkeypatch, _slow_probe)
    window = _make_window(qtbot)

    started = time.monotonic()
    window._on_fetch_data_clicked()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, "探测不得阻塞 GUI 线程"
    assert window._is_tv_probe_running() is True
    assert window._fetch_data_btn.isEnabled() is False
    assert "探测" in window._status_bar.currentMessage()

    release.set()
    qtbot.waitUntil(lambda: not window._is_tv_probe_running(), timeout=10_000)
    qtbot.waitUntil(lambda: window._fetch_data_btn.isEnabled(), timeout=10_000)


def test_second_fetch_click_does_not_start_duplicate_probe(qtbot, monkeypatch) -> None:
    release = threading.Event()
    calls: list[int] = []

    def _slow_probe(**kwargs):
        calls.append(1)
        release.wait(10.0)
        return True, None

    _patch_probe(monkeypatch, _slow_probe)
    window = _make_window(qtbot)

    window._on_fetch_data_clicked()
    qtbot.waitUntil(lambda: len(calls) == 1, timeout=10_000)
    window._on_fetch_data_clicked()  # 第二次点击必须被忽略

    assert len(calls) == 1
    release.set()
    qtbot.waitUntil(lambda: not window._is_tv_probe_running(), timeout=10_000)


def test_failed_probe_does_not_block_or_start_refresh_loop(qtbot, monkeypatch) -> None:
    _patch_probe(monkeypatch, lambda **kwargs: (False, "连接超时"))
    window = _make_window(qtbot)
    restart = MagicMock()
    window._restart_refresh_loop = restart
    # 失败时不应弹真实对话框（会把测试挂住）
    import pa_agent.gui.tv_connectivity_dialog as dlg_mod

    monkeypatch.setattr(
        dlg_mod,
        "show_tv_connectivity_blocked_dialog",
        lambda parent: "cancel",
    )

    window._on_fetch_data_clicked()
    qtbot.waitUntil(lambda: not window._is_tv_probe_running(), timeout=10_000)
    qtbot.wait(50)

    assert restart.call_count == 0
    assert window._fetch_data_btn.isEnabled() is True


def test_successful_probe_restarts_refresh_loop(qtbot, monkeypatch) -> None:
    _patch_probe(monkeypatch, lambda **kwargs: (True, None))
    window = _make_window(qtbot)
    restart = MagicMock()
    window._restart_refresh_loop = restart

    window._on_fetch_data_clicked()
    qtbot.waitUntil(lambda: restart.call_count == 1, timeout=10_000)


def test_startup_probe_is_background_and_silent(qtbot, monkeypatch) -> None:
    """启动预检：后台跑、失败不弹窗、不阻塞启动。"""
    _patch_probe(monkeypatch, lambda **kwargs: (False, "连接超时"))
    window = _make_window(qtbot)
    window._startup_tv_connectivity_check_done = False
    popups: list[int] = []
    import pa_agent.gui.tv_connectivity_dialog as dlg_mod

    monkeypatch.setattr(
        dlg_mod,
        "show_tv_connectivity_blocked_dialog",
        lambda parent: popups.append(1) or "cancel",
    )

    window._on_startup_tv_connectivity_check()
    qtbot.waitUntil(lambda: not window._is_tv_probe_running(), timeout=10_000)
    qtbot.wait(50)

    assert popups == [], "启动预检失败不得打断启动流程"
    assert "获取数据" in window._status_bar.currentMessage()


def test_fetch_click_during_startup_probe_is_not_swallowed(qtbot, monkeypatch) -> None:
    """启动预检进行中点「获取数据」：那次点击不能被吞掉。"""
    release = threading.Event()

    def _slow_probe(**kwargs):
        release.wait(10.0)
        return True, None

    _patch_probe(monkeypatch, _slow_probe)
    window = _make_window(qtbot)
    restart = MagicMock()
    window._restart_refresh_loop = restart

    window._start_tv_connectivity_probe(background=True)
    assert window._is_tv_probe_running() is True

    window._on_fetch_data_clicked()  # 复用进行中的探测，记下取数意图
    assert window._tv_probe_fetch_requested is True

    release.set()
    qtbot.waitUntil(lambda: restart.call_count == 1, timeout=10_000)


def test_close_event_stops_probe_worker(qtbot, monkeypatch) -> None:
    """关闭窗口必须安全收尾探测线程，不留悬空线程。"""
    release = threading.Event()

    def _slow_probe(**kwargs):
        release.wait(10.0)
        return True, None

    _patch_probe(monkeypatch, _slow_probe)
    window = _make_window(qtbot)
    window._on_fetch_data_clicked()
    assert window._is_tv_probe_running() is True

    window.close()
    assert window._tv_probe_worker is None

    release.set()
    qtbot.wait(100)
    # 窗口已标记关闭：迟到的探测结果不得再碰控件
    assert window._window_closing is True
