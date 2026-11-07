"""Tests for SessionTokenLedger token thresholds (pricing removed)."""

from __future__ import annotations

from pa_agent.ai.deepseek_client import AIUsage
from pa_agent.ai.session_ledger import SessionTokenLedger


def _usage(prompt: int, completion: int, cached: int = 0) -> AIUsage:
    return AIUsage(
        prompt_tokens=prompt,
        cached_prompt_tokens=cached,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def test_ledger_accumulates_tokens():
    ledger = SessionTokenLedger(context_window=1_000_000)
    ledger.add(_usage(100, 50))
    ledger.add(_usage(200, 80))
    assert ledger.total_input == 300
    assert ledger.total_output == 130


def test_context_used_is_last_request_not_cumulative():
    """上下文占用 = 最近一次请求的实际输入，不是历史消费累计（开发文档 §9.3）。

    多轮追问把历史重发，累计输入会虚增；但每次请求占用的上下文只看该请求
    自己的 prompt。累计消费（total_*）与上下文占用（context_used）必须分开。
    """
    ledger = SessionTokenLedger(context_window=1_000_000)
    ledger.add(_usage(100, 50))
    assert ledger.context_used == 100
    ledger.add(_usage(200, 80))
    assert ledger.context_used == 200  # 不是 100+200+130
    bd = ledger.breakdown()
    assert bd["context_used"] == 200
    assert bd["total_input"] == 300  # 累计消费口径保持不变
    assert bd["context_pct"] == 0.02


def test_breakdown_keeps_latest_call_for_cache_rate():
    """整轮累计与最近一次请求必须分开：命中率要按单次请求算。"""
    ledger = SessionTokenLedger(context_window=1_000_000)
    ledger.add(_usage(60381, 100, cached=0))
    ledger.add(_usage(119852, 100, cached=60288))
    bd = ledger.breakdown()

    # 累计值仍用于上下文用量与总开销
    assert bd["total_input"] == 180233
    assert bd["total_cached_input"] == 60288
    # 命中率只取最近一次请求（阶段二），不能用 180233 作分母
    assert bd["last_input"] == 119852
    assert bd["last_cached_input"] == 60288


def test_breakdown_without_calls_reports_zero_last_call():
    ledger = SessionTokenLedger(context_window=1000)
    bd = ledger.breakdown()
    assert bd["last_input"] == 0
    assert bd["last_cached_input"] == 0


def test_reset_clears_last_call():
    ledger = SessionTokenLedger(context_window=1000)
    ledger.add(_usage(500, 10, cached=200))
    ledger.reset()
    bd = ledger.breakdown()
    assert bd["last_input"] == 0
    assert bd["last_cached_input"] == 0
    assert bd["total_input"] == 0


def test_ledger_breakdown_keys():
    ledger = SessionTokenLedger(context_window=10_000)
    ledger.add(_usage(1000, 500))
    bd = ledger.breakdown()
    assert "total_input" in bd
    assert "context_used" in bd
    assert "total_cny" not in bd


def test_yellow_threshold_at_80_pct():
    ledger = SessionTokenLedger(context_window=1000, warn_pct=80.0)
    events: list[tuple[str, dict]] = []
    ledger.threshold_crossed.connect(lambda level, data: events.append((level, data)))
    ledger.add(_usage(800, 0))
    assert len(events) == 1
    assert events[0][0] == "yellow"


def test_red_threshold_at_95_pct():
    ledger = SessionTokenLedger(context_window=1000, warn_pct=80.0)
    events: list[tuple[str, dict]] = []
    ledger.threshold_crossed.connect(lambda level, data: events.append((level, data)))
    ledger.add(_usage(950, 0))
    assert any(e[0] == "red" for e in events)


def test_reset_clears_counters():
    ledger = SessionTokenLedger(context_window=1000)
    ledger.add(_usage(500, 100))
    ledger.reset()
    assert ledger.total_input == 0
    assert ledger.total_output == 0
