"""通用设置的持久化与「保存后立即生效」回归测试。

背景：main_window 在 _setup_ui 里把 keep_analysis 强制改成 False（只在内存里），
于是重启后通用设置对话框永远显示未勾选，之后任何一次整份保存又把 False 写回磁盘，
用户此前勾选的「持续跟踪分析」被永久抹掉 —— 表现为「通用设置记不住，每次都重置」。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from pa_agent.ai.session_ledger import SessionTokenLedger
from pa_agent.app_context import AppContext
from pa_agent.config.settings import Settings
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


class _RunningLoop:
    """RefreshLoop 替身：只回答 isRunning()。"""

    def isRunning(self) -> bool:  # QThread 的 API 名，保持大写
        return True


def _make_window(qtbot, *, keep_analysis: bool = False):
    ctx = AppContext()
    ctx.settings = Settings()
    ctx.settings.provider.api_key = "sk-settings-persistence"
    ctx.settings.general.last_data_source = "mt5"  # type: ignore[assignment]
    ctx.settings.general.keep_analysis = keep_analysis
    ctx.data_source = _StubSource()
    ctx.ledger = SessionTokenLedger(warn_pct=80.0)
    window = mw.MainWindow(ctx=ctx)
    qtbot.addWidget(window)
    return window


def test_startup_restores_keep_analysis_instead_of_resetting_it(qtbot) -> None:
    window = _make_window(qtbot, keep_analysis=True)

    assert window._ctx.settings.general.keep_analysis is True
    assert window._keep_analysis_checkbox.isChecked() is True
    # 勾选状态与「等待K线收盘」的锁定语义保持一致
    assert window._wait_close_checkbox.isChecked() is True
    assert window._wait_close_checkbox.isEnabled() is False


def test_startup_does_not_auto_start_the_refresh_loop(qtbot) -> None:
    """恢复勾选只还原 UI：启动阶段不该自己拉数据（数据源可能还没连上）。"""
    window = _make_window(qtbot, keep_analysis=True)

    assert getattr(window, "_refresh_loop", None) is None


def test_startup_leaves_a_disabled_preference_disabled(qtbot) -> None:
    window = _make_window(qtbot, keep_analysis=False)

    assert window._ctx.settings.general.keep_analysis is False
    assert window._keep_analysis_checkbox.isChecked() is False
    assert window._wait_close_checkbox.isEnabled() is True


def test_saving_an_unchanged_interval_does_not_restart_the_loop(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot)
    window._refresh_loop = _RunningLoop()
    calls: list[str] = []
    monkeypatch.setattr(window, "_restart_refresh_loop", lambda: calls.append("restart"))

    before = window._general_runtime_snapshot(window._ctx.settings)
    window._ctx.settings.general.refresh_interval_ms = before[0]
    window._apply_general_runtime_settings(before, window._ctx.settings)

    assert calls == []


def test_saving_a_new_interval_restarts_the_running_loop(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot)
    window._refresh_loop = _RunningLoop()
    calls: list[str] = []
    monkeypatch.setattr(window, "_restart_refresh_loop", lambda: calls.append("restart"))

    before = window._general_runtime_snapshot(window._ctx.settings)
    window._ctx.settings.general.refresh_interval_ms = before[0] + 1500
    window._apply_general_runtime_settings(before, window._ctx.settings)

    assert calls == ["restart"]


def test_saving_the_context_threshold_updates_the_live_ledger(qtbot) -> None:
    window = _make_window(qtbot)
    ledger = window._ctx.ledger
    assert ledger._warn_pct == 80.0

    before = window._general_runtime_snapshot(window._ctx.settings)
    window._ctx.settings.general.context_warning_threshold_pct = 65.0
    window._apply_general_runtime_settings(before, window._ctx.settings)

    assert ledger._warn_pct == 65.0


def test_saving_keep_analysis_syncs_the_toolbar_checkbox(qtbot, monkeypatch) -> None:
    window = _make_window(qtbot, keep_analysis=False)
    # 勾选框处理器会落盘并启动 RefreshLoop：本用例只验证 UI 同步，屏蔽两者。
    monkeypatch.setattr("pa_agent.config.settings.save_settings", lambda *a, **k: None)
    monkeypatch.setattr(window, "_ensure_refresh_loop_running", lambda: None)

    before = window._general_runtime_snapshot(window._ctx.settings)
    window._ctx.settings.general.keep_analysis = True
    window._apply_general_runtime_settings(before, window._ctx.settings)

    assert window._keep_analysis_checkbox.isChecked() is True
    assert window._wait_close_checkbox.isChecked() is True
    assert window._wait_close_checkbox.isEnabled() is False


def test_dialogs_never_edit_a_fresh_default_settings_object(qtbot, monkeypatch) -> None:
    """ctx.settings 为 None 时必须读盘，而不是拿 Settings() 兜底覆盖磁盘。"""
    window = _make_window(qtbot)
    sentinel = Settings()
    sentinel.general.analysis_bar_count = 321
    window._ctx.settings = None
    monkeypatch.setattr("pa_agent.config.settings.load_settings", lambda *a, **k: sentinel)

    assert window._ensure_settings_loaded() is sentinel
    assert window._ctx.settings is sentinel


def test_settings_path_is_redirected_to_this_tests_tmpdir(tmp_path) -> None:
    from pa_agent.config import paths

    assert paths.SETTINGS_JSON_PATH.parent == tmp_path
    assert paths.SETTINGS_JSON_PATH != paths.CONFIG_DIR / "settings.json"


def test_saving_settings_never_touches_the_repo_config() -> None:
    """跑测试不得改写用户真实的 config/settings.json（含 DPAPI 加密的 api_key）。"""
    from pa_agent.config import paths
    from pa_agent.config.settings import Settings, save_settings

    repo_config = paths.CONFIG_DIR / "settings.json"
    before = repo_config.read_bytes() if repo_config.exists() else None

    settings = Settings()
    settings.general.analysis_bar_count = 37
    save_settings(settings)

    after = repo_config.read_bytes() if repo_config.exists() else None
    assert after == before
