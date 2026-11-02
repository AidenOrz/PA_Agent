"""GUI 状态机常量与「分析中」忙碌态的回归测试。

覆盖两处 P1 缺陷：

1. 状态机曾用裸中文字面量分支，与 _EVENT_LABELS 靠「恰好一致」对齐；文案
   一改所有分支静默失效。现在分支依赖模块级 EVENT_* 常量，并在导入时断言
   常量集合与 _EVENT_LABELS 的取值一致。
2. 提交按钮曾无条件 setEnabled(True)，随后又用 button.isEnabled() 判断忙碌，
   构成死分支：按钮永远可点、忙碌判断永远为假，「分析中不能重复提交」失效。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from pa_agent.app_context import AppContext
from pa_agent.config.settings import Settings
from pa_agent.gui import main_window as mw
from pa_agent.util.threading import OrchestratorEvent


class _FakeFlowBar:
    """记录 FlowBar 调用序列的最小替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    def set_step_status(self, idx: int, status: str) -> None:
        self.calls.append(("status", idx, status))

    def set_step_caption(self, idx: int, caption: str) -> None:
        self.calls.append(("caption", idx, caption))


class _FakeStatusWindow:
    """只提供 _on_status_update 需要的属性的替身窗口。"""

    def __init__(self) -> None:
        self._analysis_in_progress = True
        self._status_bar = MagicMock()
        self._stream_panel = MagicMock()
        self._flow_bar = _FakeFlowBar()

    def _ui_is_alive(self) -> bool:
        return True

    def _update_symbol_data_alert(self) -> None:
        pass


class _StubSource:
    """已连接、无网络行为的数据源替身（绝不触发真实拉取）。"""

    _connected = True

    def __init__(self, symbol: str = "XAUUSDm", timeframe: str = "15m") -> None:
        self._symbol = symbol
        self._timeframe = timeframe

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "1h", "4h", "1d"]

    # 这些 hook 只是让提交路径的「品种/周期是否已变」判定走直路，
    # 不会真的订阅或拉数据。
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
        return []  # RefreshLoop 不会拿到真实 K 线，也就不会触发后续动作


def _make_window(qtbot, *, api_key: str = "sk-test-key"):
    """构造窗口：settings 与数据源必须在 ctor 前就位，品种/周期下拉才算已订阅。"""
    ctx = AppContext()
    ctx.settings = Settings()
    ctx.settings.provider.api_key = api_key
    ctx.data_source = _StubSource()
    window = mw.MainWindow(ctx=ctx)
    qtbot.addWidget(window)
    return window


# ── 1. 事件常量与状态机 ───────────────────────────────────────────────────────


def test_event_labels_and_constants_are_consistent() -> None:
    """_EVENT_LABELS 的每个取值都必须落在 ANALYSIS_EVENT_TEXTS 里。"""
    assert set(mw._EVENT_LABELS.values()) == mw.ANALYSIS_EVENT_TEXTS
    # 覆盖所有会驱动界面的 OrchestratorEvent
    for event in (
        OrchestratorEvent.Stage1Started,
        OrchestratorEvent.Stage1Retry,
        OrchestratorEvent.Stage1Done,
        OrchestratorEvent.Stage1Failed,
        OrchestratorEvent.Stage2Started,
        OrchestratorEvent.Stage2Retry,
        OrchestratorEvent.Stage2Done,
        OrchestratorEvent.Stage2Failed,
        OrchestratorEvent.RecordSaved,
        OrchestratorEvent.Cancelled,
    ):
        assert event in mw._EVENT_LABELS
        assert mw._EVENT_LABELS[event] in mw.ANALYSIS_EVENT_TEXTS


def test_event_constants_are_non_empty_strings() -> None:
    """常量必须是可直接展示的非空文本（它们同时是 EventBus 上的状态文本）。"""
    for text in mw.ANALYSIS_EVENT_TEXTS:
        assert isinstance(text, str) and text.strip()


@pytest.mark.parametrize(
    ("event_text", "expected_status", "expected_caption"),
    [
        (mw.EVENT_STAGE1_STARTED, "active", "分析中…"),
        (mw.EVENT_STAGE1_DONE, "done", "已完成"),
        (mw.EVENT_STAGE1_FAILED, "error", "失败"),
    ],
)
def test_stage1_events_drive_flowbar_steps(
    event_text: str, expected_status: str, expected_caption: str
) -> None:
    """阶段一事件（由常量驱动）应更新 FlowBar 第 3 步（index 2）。"""
    win = _FakeStatusWindow()
    mw.MainWindow._on_status_update(win, event_text)
    assert ("status", 2, expected_status) in win._flow_bar.calls
    assert ("caption", 2, expected_caption) in win._flow_bar.calls


@pytest.mark.parametrize(
    ("event_text", "expected_status", "expected_caption"),
    [
        (mw.EVENT_STAGE2_STARTED, "active", "决策中…"),
        (mw.EVENT_STAGE2_DONE, "done", "已完成"),
        (mw.EVENT_STAGE2_FAILED, "error", "失败"),
    ],
)
def test_stage2_events_drive_flowbar_steps(
    event_text: str, expected_status: str, expected_caption: str
) -> None:
    """阶段二事件（由常量驱动）应更新 FlowBar 第 4 步（index 3）。"""
    win = _FakeStatusWindow()
    mw.MainWindow._on_status_update(win, event_text)
    assert ("status", 3, expected_status) in win._flow_bar.calls
    assert ("caption", 3, expected_caption) in win._flow_bar.calls


def test_cancelled_event_resets_every_step() -> None:
    win = _FakeStatusWindow()
    mw.MainWindow._on_status_update(win, mw.EVENT_CANCELLED)
    reset = {idx for kind, idx, status in win._flow_bar.calls if status == "idle"}
    assert reset == {0, 1, 2, 3, 4}


def test_drifted_literal_does_not_silently_drive_state() -> None:
    """文案微调（多一个「已」字）不应再被当成同一个事件。

    这正是旧实现的失效模式：分支写死字面量，文案一改就静默不匹配。现在只
    认常量的精确值 —— 文案变化会立刻在测试里暴露成「状态机无反应」。
    """
    win = _FakeStatusWindow()
    mw.MainWindow._on_status_update(win, "阶段一已完成")
    assert win._flow_bar.calls == []


# ── 2. 忙碌态驱动按钮 ────────────────────────────────────────────────────────


def test_busy_flag_disables_submit_button(qtbot) -> None:
    window = _make_window(qtbot)

    window._analysis_busy = True
    assert window._submit_btn.isEnabled() is False
    assert window._incremental_submit_btn.isEnabled() is False
    assert window._submit_block_reason() == "分析进行中"

    window._analysis_busy = False
    assert window._submit_btn.isEnabled() is True


def test_busy_flag_is_a_view_on_analysis_in_progress(qtbot) -> None:
    """忙碌态是最小改动：与既有 _analysis_in_progress 字段同源，避免两处漂移。"""
    window = _make_window(qtbot)
    window._analysis_in_progress = True
    assert window._analysis_busy is True
    window._analysis_busy = False
    assert window._analysis_in_progress is False


def test_button_stays_clickable_when_only_blocked_by_missing_key(qtbot) -> None:
    """非忙碌的锁定原因（缺 API Key 等）仍保持可点，以便点击后说明原因。"""
    window = _make_window(qtbot, api_key="")
    reason = window._submit_block_reason()
    assert reason is not None and "API Key" in reason
    assert window._submit_btn.isEnabled() is True
    assert "API Key" in window._submit_btn.toolTip()


def test_begin_submit_is_rejected_while_busy(qtbot) -> None:
    """忙碌时重复提交必须被拦截（这是 P1 死分支真正要恢复的语义）。"""
    window = _make_window(qtbot)
    start = MagicMock()
    window._start_analysis = start
    window._analysis_busy = True

    window._begin_submit_analysis(force_incremental=False)

    assert start.call_count == 0


def test_begin_submit_runs_when_not_busy(qtbot) -> None:
    window = _make_window(qtbot)
    start = MagicMock()
    window._start_analysis = start
    window._analysis_busy = False
    window._wait_close_checkbox.setChecked(False)

    window._begin_submit_analysis(force_incremental=False)

    assert start.call_count == 1


def test_incremental_label_uses_busy_flag_not_button_state(qtbot) -> None:
    """_refresh_incremental_label 曾读 button.isEnabled()，是必然为真的死分支。"""
    window = _make_window(qtbot)
    window._submit_btn.setText("增量分析")
    window._incremental_available = True
    window._analysis_busy = True

    window._refresh_incremental_label()

    assert window._submit_btn.text() == "提交分析"
    assert window._incremental_available is False


def test_close_event_shuts_down_decision_flow_panel(qtbot) -> None:
    """关闭窗口必须停掉决策树可视化的定时器。

    _FlowScene 的特效、播放、重排三个定时器都挂在 panel 上，父窗口关闭后
    它们仍会继续 tick，回调打到正在销毁的场景上。此前 closeEvent 只停了
    刷新循环与 worker，没有通知 panel。
    """
    window = _make_window(qtbot)
    panel = window._decision_flow_viz_panel
    panel.shutdown = MagicMock()

    window.close()

    assert panel.shutdown.call_count == 1
