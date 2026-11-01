"""E2E smoke test — symbol switch mid-flight cancels the AI worker.

Task 19.3
"""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock

import pytest

from tests.e2e.smoke_support import SmokeDataSource, make_smoke_ctx, make_trend_bars
from tests.fixtures.ai_payloads import VALID_STAGE1, VALID_STAGE2_ORDER


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


def _make_ctx_slow_stage2(tmp_path):
    """Build a context where stage2 blocks until the cancel token is set."""
    stage2_started = threading.Event()

    def slow_chat(messages, cancel_token=None, **kwargs):
        call_count = slow_chat._call_count
        slow_chat._call_count += 1

        if call_count == 0:
            return _make_reply(VALID_STAGE1)
        stage2_started.set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if cancel_token is not None and cancel_token.is_set():
                from pa_agent.ai.deepseek_client import CancelledError

                raise CancelledError("cancelled by token")
            time.sleep(0.05)
        return _make_reply(VALID_STAGE2_ORDER)

    slow_chat._call_count = 0

    mock_client = MagicMock()
    mock_client.stream_chat.side_effect = slow_chat

    mock_assembler = MagicMock()
    mock_assembler.build_stage1.return_value = [{"role": "system", "content": "s1"}]
    mock_assembler.build_stage2.return_value = [{"role": "system", "content": "s2"}]

    pending_writer = MagicMock()

    bars = make_trend_bars(40)
    source = SmokeDataSource(bars)
    ctx = make_smoke_ctx(source)
    ctx.client = mock_client
    ctx.assembler = mock_assembler
    ctx.pending_writer = pending_writer

    return ctx, pending_writer, stage2_started


@pytest.mark.e2e
def test_switch_mid_flight_cancels_worker(qtbot, tmp_path):
    """Switching symbol while stage2 is running cancels the worker."""
    from pa_agent.gui.main_window import MainWindow

    ctx, pending_writer, stage2_started = _make_ctx_slow_stage2(tmp_path)

    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.show()

    window._ctx.settings.general.analysis_bar_count = 20
    window._last_frame_ready_bars = make_trend_bars(40)

    window._on_submit_analysis()
    # Submission goes through the prep worker first; poll until the analysis
    # worker exists instead of assuming it is assigned synchronously.
    deadline = time.monotonic() + 5.0
    while window._worker is None and time.monotonic() < deadline:
        qtbot.wait(20)
    worker = window._worker
    assert worker is not None, "Worker should have been created"

    # Wait until stage2 has started (so we know the worker is mid-flight)
    assert stage2_started.wait(timeout=5.0), "Stage 2 did not start within 5 s"

    # Trigger the symbol switch mid-flight.  Typing in the combo only refreshes
    # the alert label by design; the switch happens when the user applies it
    # (获取数据 / 提交分析), which is this handler.
    window._symbol_combo.setCurrentText("EURUSD")
    window._on_symbol_or_tf_changed("EURUSD", "15m")

    # Worker should be cancelled and finish within a reasonable time
    deadline = time.monotonic() + 5.0
    while window._analysis_in_progress and time.monotonic() < deadline:
        qtbot.wait(50)
    assert not window._analysis_in_progress, "Worker still running after switch"
