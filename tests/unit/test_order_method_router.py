"""Tests for §11 order-method routing."""

from __future__ import annotations

from pa_agent.ai.decision_nodes import route_order_method


def test_breakout_without_basis_falls_back_to_limit() -> None:
    decision = {
        "order_type": "突破单",
        "entry_price": 101.0,
        "stop_loss_price": 99.0,
        "take_profit_price": 102.0,
    }
    trace = [{"node_id": "10.3", "answer": "是", "reason": "ok"}]
    stage1 = {"cycle_position": "normal_channel"}
    nodes = route_order_method(stage1, decision, trace)
    assert decision["order_type"] == "限价单"
    assert nodes
    assert nodes[-1].node_id == "11.2"
    assert nodes[-1].answer == "是"
    assert "限价单" in nodes[-1].reason


def test_model_breakout_preserved_for_broad_channel() -> None:
    decision = {
        "order_type": "突破单",
        "order_direction": "做空",
        "entry_price": 4210.348,
        "entry_basis_bar": "K1",
        "entry_basis_extreme": "low",
        "stop_loss_price": 4228.399,
        "take_profit_price": 4183.278,
        "take_profit_price_2": 4160.0,
    }
    trace = [{"node_id": "10.3", "answer": "是", "reason": "ok"}]
    stage1 = {"cycle_position": "broad_channel"}
    nodes = route_order_method(stage1, decision, trace)
    assert decision["order_type"] == "突破单"
    assert nodes
    assert nodes[-1].node_id == "11.2"
    assert nodes[-1].answer == "是"


def test_model_limit_order_preserved_for_breakout_cycle() -> None:
    decision = {
        "order_type": "限价单",
        "entry_price": 100.5,
        "stop_loss_price": 99.0,
        "take_profit_price": 101.5,
    }
    trace = [{"node_id": "10.3", "answer": "是", "reason": "ok"}]
    stage1 = {"cycle_position": "normal_channel"}
    nodes = route_order_method(stage1, decision, trace)
    assert decision["order_type"] == "限价单"
    assert nodes[-1].answer == "是"


def test_extreme_tr_cycle_clears_decision_to_no_order() -> None:
    """A cycle that forbids trading must not leave a live trade plan behind.

    The router used to only return no §11 nodes, so decision.order_type stayed
    突破单 with full entry/stop/target prices and reached the order path with no
    audit node at all.
    """
    decision = {
        "order_type": "突破单",
        "order_direction": "做多",
        "entry_price": 101.0,
        "entry_basis_bar": "K1",
        "entry_basis_extreme": "high",
        "entry_rule": "K1高点上方1跳动",
        "stop_loss_price": 99.0,
        "take_profit_price": 103.0,
        "take_profit_price_2": 105.0,
        "trade_confidence": 60,
        "estimated_win_rate": 55,
    }
    trace = [{"node_id": "10.3", "answer": "是", "reason": "ok"}]
    nodes = route_order_method({"cycle_position": "extreme_tr"}, decision, trace)
    assert nodes == []
    assert decision["order_type"] == "不下单"
    for field in (
        "order_direction",
        "entry_price",
        "stop_loss_price",
        "take_profit_price",
        "take_profit_price_2",
        "entry_basis_bar",
        "entry_basis_extreme",
        "entry_rule",
        "estimated_win_rate",
        "estimated_win_rate_reasoning",
    ):
        assert decision[field] is None, field
    assert decision["trade_confidence"] == 60


def test_missing_stage1_does_not_coerce_the_trade() -> None:
    """No stage1 means no routing decision, not unknown-cycle-so-do-not-trade.

    Normalizing a missing input into cycle=unknown made the router coerce every
    trade to 不下单, hiding a missing-input bug as an order rejection.
    """
    decision = {
        "order_type": "突破单",
        "entry_price": 101.0,
        "stop_loss_price": 99.0,
        "take_profit_price": 103.0,
        "take_profit_price_2": 105.0,
    }
    trace = [{"node_id": "10.3", "answer": "是", "reason": "ok"}]
    nodes = route_order_method(None, decision, trace)
    assert nodes == []
    assert decision["order_type"] == "突破单"


def test_spike_ending_breakout_keeps_section11_nodes() -> None:
    """The preserved 突破单 must still get its §11 audit node."""
    decision = {
        "order_type": "突破单",
        "entry_basis_bar": "K1",
        "entry_basis_extreme": "high",
        "entry_price": 101.0,
        "stop_loss_price": 99.0,
        "take_profit_price": 103.0,
        "take_profit_price_2": 105.0,
    }
    trace = [{"node_id": "10.3", "answer": "是", "reason": "ok"}]
    stage1 = {"cycle_position": "spike", "spike_stage": "ending"}
    nodes = route_order_method(stage1, decision, trace)
    assert decision["order_type"] == "突破单"
    assert nodes, "spike-ending breakout lost its §11 nodes"
    assert nodes[-1].node_id == "11.1"
