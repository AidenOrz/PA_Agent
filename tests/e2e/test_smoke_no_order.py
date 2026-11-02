"""E2E smoke test — no-order path: stage2 returns 不下单.

Task 19.2
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pyqtgraph as pg
import pytest

from tests.e2e.smoke_support import SmokeDataSource, make_smoke_ctx
from tests.fixtures.ai_payloads import VALID_STAGE1, VALID_STAGE2_NO_ORDER
from tests.fixtures.kline_bars import make_newest_first_bars


def _make_reply(content_dict: dict) -> MagicMock:
    reply = MagicMock()
    reply.content = json.dumps(content_dict)
    reply.raw = {"content": reply.content}
    reply.usage = MagicMock()
    reply.usage.prompt_tokens = 100
    reply.usage.completion_tokens = 50
    reply.usage.cached_prompt_tokens = 0
    reply.usage.total_tokens = 150
    return reply


def _make_ctx(tmp_path):
    """Build a minimal AppContext configured for a no-order response."""
    mock_client = MagicMock()
    mock_client.stream_chat.side_effect = [
        _make_reply(VALID_STAGE1),
        _make_reply(VALID_STAGE2_NO_ORDER),
    ]

    mock_assembler = MagicMock()
    mock_assembler.build_stage1.return_value = [{"role": "system", "content": "s1"}]
    mock_assembler.build_stage2.return_value = [{"role": "system", "content": "s2"}]

    pending_writer = MagicMock()

    bars = make_newest_first_bars(30, with_forming=True)
    source = SmokeDataSource(bars)
    ctx = make_smoke_ctx(source)
    ctx.client = mock_client
    ctx.assembler = mock_assembler
    ctx.pending_writer = pending_writer

    return ctx, pending_writer


@pytest.mark.e2e
def test_no_order_shows_no_trade_conclusion(qtbot, tmp_path):
    """When stage2 returns 不下单, DecisionPanel shows that conclusion."""
    from pa_agent.gui.main_window import MainWindow

    ctx, pending_writer = _make_ctx(tmp_path)

    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.show()

    window._ctx.settings.general.analysis_bar_count = 20
    window._last_frame_ready_bars = make_newest_first_bars(30, with_forming=True)
    window._on_submit_analysis()

    # Poll until the analysis is no longer in progress
    qtbot.waitUntil(
        lambda: not window._analysis_in_progress,
        timeout=10_000,
    )

    # DecisionPanel should show 不下单
    conclusion_text = window._decision_panel._conclusion_label.text()
    assert "不下单" in conclusion_text, (
        f"Expected 不下单 conclusion, got: {conclusion_text!r}"
    )

    # Chart must not draw entry/TP/SL lines for 不下单.  Support/resistance
    # levels come from the Stage-1 structure and legitimately stay on screen,
    # so only the decision overlay is checked here.
    chart = window._chart_widget
    overlay_lines = [
        item for item in chart.decision_overlay_items()
        if isinstance(item, pg.InfiniteLine)
    ]
    assert overlay_lines == [], (
        f"Expected no entry/TP/SL lines for 不下单, found {len(overlay_lines)}"
    )
