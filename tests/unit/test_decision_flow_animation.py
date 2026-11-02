"""决策路径动画的实例级状态回归测试。

缺陷：_ANIM_PHASE / 相位曾是模块级全局状态，且 60ms 定时器对所有视图无条件
全场景重绘。全屏副本会再起一个定时器 → 动画速度随窗口数翻倍、CPU 常驻。

修复后：相位存在各视图自己的 _FlowScene 上；定时器只在视图可见时运行；
每次 tick 只重绘扫描光带与终结节点的呼吸描边，而不是整个场景。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QRectF

from pa_agent.gui import decision_flow_viz as viz

_TRACE = dict(
    gate_trace=[
        {
            "node_id": "1.1",
            "phase": "gate",
            "section": "周期",
            "question": "是否可识别周期？",
            "answer": "是",
            "reason": "test",
            "skipped": False,
        }
    ],
    decision_trace=[
        {
            "node_id": "4.1",
            "phase": "decision",
            "section": "顺势通道",
            "question": "是否为顺势通道？",
            "answer": "是",
            "reason": "test",
            "skipped": False,
        }
    ],
    terminal={"node_id": "11.2", "outcome": "trade", "label": "做多"},
    gate_result="proceed",
)


def test_no_module_level_animation_phase() -> None:
    """全局相位必须彻底移除，否则动画状态仍会被多个视图共享。"""
    assert not hasattr(viz, "_ANIM_PHASE")


def test_scene_phase_is_per_instance(qapp) -> None:
    """两个 scene 的相位互不影响（这正是全屏副本速度翻倍的根因）。"""
    a = viz._FlowScene()
    b = viz._FlowScene()
    a.advance_phase(0.5)
    assert a.anim_phase == pytest.approx(0.5)
    assert b.anim_phase == 0.0


def test_two_panels_do_not_share_phase(qtbot) -> None:
    first = viz.DecisionFlowVizPanel()
    second = viz.DecisionFlowVizPanel()
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    first.set_trace(**_TRACE)
    second.set_trace(**_TRACE)
    first.show()  # 只有可见的视图才跑动画

    first._scene.advance_phase(0.24)
    first._on_fx_tick()

    assert first._scene.anim_phase == pytest.approx(0.3)
    assert second._scene.anim_phase == pytest.approx(0.0)


def test_fx_timer_starts_hidden_and_follows_visibility(qtbot) -> None:
    """定时器只在可见时跑；隐藏/关闭必须停掉。"""
    panel = viz.DecisionFlowVizPanel()
    qtbot.addWidget(panel)
    panel.set_trace(**_TRACE)
    assert panel._fx_timer.isActive() is False

    panel.show()
    assert panel._fx_timer.isActive() is True

    panel.hide()
    assert panel._fx_timer.isActive() is False


def test_shutdown_stops_every_timer(qtbot) -> None:
    panel = viz.DecisionFlowVizPanel()
    qtbot.addWidget(panel)
    panel.set_trace(**_TRACE)
    panel.show()
    assert panel._fx_timer.isActive() is True

    panel.shutdown()

    assert panel._fx_timer.isActive() is False
    assert panel._play_timer.isActive() is False
    assert panel._refit_timer.isActive() is False


def test_hidden_panel_tick_does_not_advance_phase(qtbot) -> None:
    panel = viz.DecisionFlowVizPanel()
    qtbot.addWidget(panel)
    panel.set_trace(**_TRACE)
    panel.hide()
    before = panel._scene.anim_phase

    panel._on_fx_tick()

    assert panel._scene.anim_phase == before


def test_tick_repaints_band_not_whole_scene(qtbot, monkeypatch) -> None:
    """每次 tick 的重绘区域必须远小于场景矩形（原来是 update(sceneRect())）。"""
    panel = viz.DecisionFlowVizPanel()
    qtbot.addWidget(panel)
    panel.set_trace(**_TRACE)
    panel.show()

    scene = panel._scene
    full = scene.sceneRect()
    regions: list[QRectF] = []
    original_update = scene.update

    def _spy(rect: QRectF | None = None) -> None:
        if isinstance(rect, QRectF):
            regions.append(QRectF(rect))
        original_update(rect)

    monkeypatch.setattr(scene, "update", _spy)
    panel._on_fx_tick()

    band_regions = [r for r in regions if r.height() <= viz._SCAN_BAND_H + 1]
    assert band_regions, "应当只重绘扫描光带"
    for rect in band_regions:
        assert rect.height() < full.height()
        assert rect.width() <= full.width() + 1


def test_clear_stops_animation_timer(qtbot) -> None:
    panel = viz.DecisionFlowVizPanel()
    qtbot.addWidget(panel)
    panel.set_trace(**_TRACE)
    panel.show()
    assert panel._fx_timer.isActive() is True

    panel.clear()

    assert panel._fx_timer.isActive() is False
def test_paint_survives_scene_cleared_underneath(qtbot) -> None:
    """场景被清空后仍有排队重绘时，paint() 不得抛 RuntimeError。

    ``QGraphicsScene.clear()`` 销毁 C++ 对象，但 Python 侧可能还持有 item
    引用（面板缓存了 placed item），QueuedConnection 的 paint 事件可能晚于
    销毁到达。此时 ``self.scene()`` 会抛
    ``RuntimeError: wrapped C/C++ object ... has been deleted``；异常从
    paint() 逃到 Qt 事件循环会直接 abort 整个进程（Windows 上表现为
    ``Fatal Python error: Aborted``，CI 就是这么挂的）。
    """
    panel = viz.DecisionFlowVizPanel()
    qtbot.addWidget(panel)
    panel.set_trace(**_TRACE)
    panel.show()

    edges = [i for i in panel._scene.items() if isinstance(i, viz._BranchEdge)]
    terminals = [i for i in panel._scene.items() if isinstance(i, viz._TerminalNode)]
    assert edges and terminals

    panel._scene.clear()  # C++ 侧对象已销毁，Python 包装器仍被下面引用

    # 模拟迟到的重绘：两个取相位的入口都必须安全降级而不是抛异常
    for edge in edges:
        assert isinstance(edge.phase(), float)
    for node in terminals:
        assert isinstance(node._anim_phase(), float)