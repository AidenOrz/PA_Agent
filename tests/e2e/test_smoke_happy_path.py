"""E2E smoke test — happy path: two-stage analysis produces a trading decision.

Task 19.1

The sentinel reply below is not the shared ``VALID_STAGE2`` fixture: that
fixture carries entry=2010.5 / stop=1995 / tp=2050 prices that no longer match
the synthetic 2080-2090 snapshots, so the program trade-metrics guard (RR floor,
TP2 geometry, K1 freshness) correctly rewrote it to 不下单 and the "happy path"
assertion could never pass.  Prices here are derived from the newest closed bar
with a deliberately conservative RR inside the 1.0-1.5 TP1 band.
"""

from __future__ import annotations

import copy
import json
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


def make_trade_payload() -> dict:
    """A breakout order whose prices satisfy the program trade guards."""
    from pa_agent.data.snapshot import take_snapshot_from_bars

    payload = copy.deepcopy(VALID_STAGE2_ORDER)
    # Use the same frame the orchestrator will build: the normalizer recomputes
    # a breakout entry as "K1 high + 1 tick", so K1 must be read from there.
    frame = take_snapshot_from_bars(make_trend_bars(40), 20, "XAUUSDm", "15m")
    k1_high = float(frame.bars[0].high)
    # A breakout order is program-repriced to "K1 high + 1 tick" (tick inferred
    # from the snapshot decimals), so derive the plan from that exact entry —
    # otherwise the repricing silently rewrites the risk/reward under test.
    entry = round(k1_high + 0.01, 2)
    risk = 2.0
    decision = payload["decision"]
    decision.update(
        {
            "order_type": "突破单",
            "order_direction": "做多",
            "entry_price": entry,
            "stop_loss_price": round(entry - risk, 2),
            "take_profit_price": round(entry + risk * 1.3, 2),
            "take_profit_price_2": round(entry + risk * 2.6, 2),
            "entry_basis_bar": "K1",
            "entry_basis_extreme": "high",
            "entry_rule": "breakout above K1 high by 1 tick",
            "estimated_win_rate": 55,
        }
    )
    payload["terminal"] = {"node_id": "11.2", "outcome": "trade", "label": "10.3 pass"}
    for node in payload["decision_trace"]:
        if str(node.get("node_id")) == "10.3":
            node["answer"] = "是"
    return payload


def _make_ctx(tmp_path, stage2_response=None):
    """Build a minimal AppContext with all required components."""
    if stage2_response is None:
        stage2_response = make_trade_payload()

    mock_client = MagicMock()
    mock_client.stream_chat.side_effect = [
        _make_reply(VALID_STAGE1),
        _make_reply(stage2_response),
    ]

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

    return ctx, pending_writer


@pytest.mark.e2e
def test_happy_path_shows_trading_decision(qtbot, tmp_path):
    """Full two-stage analysis completes and DecisionPanel shows a trade."""
    from pa_agent.gui.main_window import MainWindow

    ctx, pending_writer = _make_ctx(tmp_path)

    window = MainWindow(ctx)
    qtbot.addWidget(window)
    window.show()

    window._ctx.settings.general.analysis_bar_count = 20
    window._last_frame_ready_bars = make_trend_bars(40)

    window._on_submit_analysis()

    # Poll until the analysis is no longer in progress (worker done).
    # Using waitUntil avoids the race where the worker finishes before
    # waitSignal is set up (mock data is very fast).
    qtbot.waitUntil(
        lambda: not window._analysis_in_progress,
        timeout=10_000,
    )

    # DecisionPanel should show a trading decision (not 不下单)
    conclusion_text = window._decision_panel._conclusion_label.text()
    assert "不下单" not in conclusion_text, f"Expected a trading decision, got: {conclusion_text!r}"
    assert conclusion_text != "—", "DecisionPanel still shows default '—', expected a decision"

    # PendingWriter.save_full should have been called
    pending_writer.save_full.assert_called_once()
