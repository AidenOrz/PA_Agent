"""TradingView symbol semantics and venue guards.

Covers the two failure modes that made TradingView look broken:

* a lowercase ticker ("aapl") being treated as a company name and probed
  against seven forex venues before ever reaching NASDAQ;
* a venue that cannot list the symbol (000001 on OANDA/NASDAQ, 1810 off HKEX)
  being requested anyway, burning one WebSocket timeout per attempt.
"""

from __future__ import annotations

import pytest

from pa_agent.data import tradingview as tv_module
from pa_agent.data.market_defaults import (
    equity_tv_auto_probe_plan,
    is_partial_tv_symbol_input,
    resolve_tv_fetch_pair,
    resolve_tv_pair,
    sanitize_tv_exchange_for_symbol,
)
from pa_agent.data.tv_symbol_lookup import (
    is_tv_alias_input,
    is_tv_name_input,
    lookup_tv_symbol_alias,
)


@pytest.mark.parametrize("text", ["小米", "贵州茅台", "小米集团", " 比亚迪 "])
def test_chinese_input_is_a_name(text: str) -> None:
    assert is_tv_name_input(text)


@pytest.mark.parametrize("text", ["aapl", "APPL", "XAUUSD", "000001", "1810", ""])
def test_tickers_are_never_names(text: str) -> None:
    assert not is_tv_name_input(text)


def test_lowercase_and_uppercase_tickers_probe_identically() -> None:
    assert equity_tv_auto_probe_plan("aapl") == equity_tv_auto_probe_plan("AAPL")
    assert equity_tv_auto_probe_plan("aapl")[0] == ("NASDAQ", "AAPL")


def test_lowercase_alias_still_resolves() -> None:
    assert lookup_tv_symbol_alias("xiaomi") == ("HKEX", "1810")
    assert lookup_tv_symbol_alias("bili") == ("NASDAQ", "BILI")
    assert equity_tv_auto_probe_plan("xiaomi") == [("HKEX", "1810")]


def test_alias_input_distinguishes_names_from_tickers() -> None:
    assert is_tv_alias_input("xiaomi")
    assert is_tv_alias_input("小米")
    assert not is_tv_alias_input("BILI")
    assert not is_tv_alias_input("000001")


def test_unknown_lowercase_ticker_ignores_alias_table() -> None:
    assert lookup_tv_symbol_alias("aapl") is None
    ex, sym, adjusted = resolve_tv_pair("NASDAQ", "aapl")
    assert (ex, sym) == ("NASDAQ", "aapl")


@pytest.mark.parametrize(
    ("exchange", "symbol", "expected"),
    [
        ("OANDA", "000001", ""),
        ("NASDAQ", "000001", ""),
        ("SZSE", "000001", "SZSE"),
        ("sh", "000001", "SH"),
        ("NASDAQQ", "1810", ""),
        ("HKEX", "1810", "HKEX"),
        ("OANDA", "XAUUSD", "OANDA"),
        ("", "000001", ""),
        ("AUTO", "600519", ""),
        ("NASDAQ", "AAPL", "NASDAQ"),
    ],
)
def test_sanitize_exchange_for_symbol(exchange: str, symbol: str, expected: str) -> None:
    assert sanitize_tv_exchange_for_symbol(exchange, symbol) == expected


def test_resolve_tv_fetch_pair_still_follows_aliases() -> None:
    assert resolve_tv_fetch_pair("HKEX", "小米集团") == ("HKEX", "1810")
    assert resolve_tv_fetch_pair("HKEX", "xiaomi") == ("HKEX", "1810")
    assert resolve_tv_fetch_pair("", "aapl") == ("", "aapl")


@pytest.mark.parametrize(("text", "partial"), [("A", True), ("aa", False), ("00", True)])
def test_short_ticker_typing_is_partial(text: str, partial: bool) -> None:
    assert is_partial_tv_symbol_input(text) is partial


def test_ws_timeout_stays_short() -> None:
    # A rejected pair drains ~5 socket reads, so the worst case is ~5x this.
    assert tv_module._TV_WS_TIMEOUT_S <= 3.0
