"""A 股代码 → 交易所前缀：东财内只有一份权威规则。"""
from __future__ import annotations

import pytest

from pa_agent.data.eastmoney_client import (
    _market_prefix_for_code,
    stock_market_code,
    stock_secid,
)


@pytest.mark.parametrize(
    ("code", "prefix"),
    [
        # 沪市主板 / 科创板 / B 股
        ("600519", "1"),
        ("688981", "1"),
        ("900901", "1"),
        # 沪市 ETF / 基金（历史上被判成深市的那一类）
        ("510300", "1"),
        ("512880", "1"),
        ("588000", "1"),
        # 深市主板 / 创业板
        ("000001", "0"),
        ("300750", "0"),
        ("002475", "0"),
        ("200011", "0"),
        # 深市 ETF / 基金
        ("159915", "0"),
        ("161725", "0"),
        # 北交所
        ("430047", "0"),
        ("830799", "0"),
    ],
)
def test_market_prefix(code: str, prefix: str) -> None:
    assert _market_prefix_for_code(code) == prefix


def test_prefixed_symbol_is_stripped_before_lookup() -> None:
    assert _market_prefix_for_code("sh600519") == "1"
    assert _market_prefix_for_code("sz000001") == "0"


def test_shanghai_etf_is_shanghai_market() -> None:
    """回归：510300 曾被 stock_market_code 判成深市，与另处 5 开头规则矛盾。"""
    assert stock_market_code("510300") == 1
    assert stock_secid("510300") == "1.510300"


def test_shenzhen_etf_is_shenzhen_market() -> None:
    assert stock_market_code("159915") == 0
    assert stock_secid("159915") == "0.159915"