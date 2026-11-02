"""Shared "coerce this decision to 不下单" helper."""

from __future__ import annotations

from pa_agent.ai.no_order import (
    NO_ORDER_NULL_FIELDS,
    clear_decision_to_no_order,
    decision_has_trade_prices,
)


def _trade_decision() -> dict:
    return {
        "order_type": "突破单",
        "order_direction": "做多",
        "entry_price": 101.0,
        "entry_basis_bar": "K1",
        "entry_basis_extreme": "high",
        "entry_rule": "K1高点上方1跳动",
        "stop_loss_price": 99.0,
        "take_profit_price": 103.0,
        "take_profit_price_2": 105.0,
        "estimated_win_rate": 55,
        "estimated_win_rate_reasoning": "ok",
        "trade_confidence": None,
        "trade_confidence_reasoning": "",
    }


def test_clear_nulls_every_trade_field() -> None:
    decision = _trade_decision()
    clear_decision_to_no_order(decision)
    assert decision["order_type"] == "不下单"
    for field in NO_ORDER_NULL_FIELDS:
        assert decision[field] is None, field
    assert decision["estimated_win_rate"] is None
    assert decision["estimated_win_rate_reasoning"] is None


def test_clear_fills_required_confidence_defaults() -> None:
    decision = _trade_decision()
    clear_decision_to_no_order(decision)
    # Schema requires non-null confidence on no-order decisions too.
    assert decision["trade_confidence"] == 0
    assert decision["trade_confidence_reasoning"]


def test_clear_keeps_existing_trade_confidence() -> None:
    decision = _trade_decision()
    decision["trade_confidence"] = 42
    decision["trade_confidence_reasoning"] = "已评估"
    clear_decision_to_no_order(decision)
    assert decision["trade_confidence"] == 42
    assert decision["trade_confidence_reasoning"] == "已评估"


def test_decision_has_trade_prices_requires_all_four() -> None:
    decision = _trade_decision()
    assert decision_has_trade_prices(decision)
    decision["take_profit_price_2"] = None
    assert not decision_has_trade_prices(decision)
