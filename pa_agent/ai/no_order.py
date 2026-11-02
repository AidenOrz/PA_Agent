"""Single source of truth for "force this decision to 不下单" coercion.

Several code paths must turn a model trade decision into a no-order decision:
the §10.3 / §14 gates, a failed trader equation, and the §11 router when the
cycle_position does not permit trading (``extreme_tr`` / unknown).  Each used
to carry its own copy of the price-field list, which drifted: the router only
had to *return no §11 nodes*, so a decision the router had classified as
"do not trade" still carried live entry/stop/target prices and reached the
order path with a missing audit node instead of being blocked.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TRADE_ORDER_TYPES = frozenset({"限价单", "突破单", "市价单"})

# Every decision field that must be null when order_type == "不下单"
# (must stay in sync with the schema + JsonValidator._check_no_order_invariant).
NO_ORDER_NULL_FIELDS = (
    "order_direction",
    "entry_price",
    "take_profit_price",
    "take_profit_price_2",
    "stop_loss_price",
    "entry_basis_bar",
    "entry_basis_extreme",
    "entry_rule",
)


def clear_decision_to_no_order(decision: dict[str, Any]) -> None:
    """In-place rewrite *decision* into a schema-valid 不下单 decision."""
    decision["order_type"] = "不下单"
    for field in NO_ORDER_NULL_FIELDS:
        decision[field] = None
    decision["estimated_win_rate"] = None
    decision["estimated_win_rate_reasoning"] = None
    # trade_confidence / trade_confidence_reasoning: schema requires non-null
    # values, so a coerced no-order still needs valid defaults.
    if decision.get("trade_confidence") is None:
        decision["trade_confidence"] = 0
    reasoning = decision.get("trade_confidence_reasoning")
    if not isinstance(reasoning, str) or not reasoning:
        decision["trade_confidence_reasoning"] = "无入场计划，不存在交易信心"


def decision_has_trade_prices(decision: dict[str, Any]) -> bool:
    """True when all four prices are present (a complete trade plan)."""
    return all(
        decision.get(key) is not None
        for key in (
            "entry_price",
            "stop_loss_price",
            "take_profit_price",
            "take_profit_price_2",
        )
    )
