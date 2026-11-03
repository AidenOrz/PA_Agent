"""Registry invariants: one source of truth for kinds, labels and markets."""

from __future__ import annotations

import pytest

from pa_agent.data import sources_registry as registry
from pa_agent.data.factory import (
    DATA_SOURCE_CHOICES,
    data_source_label,
    default_symbol_for_kind,
    normalize_data_source_kind,
)
from pa_agent.data.sources_registry import (
    ALL_KINDS,
    DOMESTIC_A_SHARE_KINDS,
    HIDDEN_KINDS,
    SOURCE_SPECS,
    UI_KINDS,
    is_domestic_a_share,
    is_throttled,
    kinds_for_market,
    min_refresh_interval_ms,
    source_default_timeframe,
    source_placeholder,
    source_spec,
    source_supported_timeframes,
)


def test_kinds_are_unique():
    kinds = [spec.kind for spec in SOURCE_SPECS]
    assert len(kinds) == len(set(kinds))
    assert set(kinds) == ALL_KINDS


def test_every_kind_has_a_label_and_default_symbol():
    for kind in ALL_KINDS:
        spec = source_spec(kind)
        assert spec is not None
        assert spec.label.strip(), kind
        assert spec.default_symbol.strip(), kind
        assert normalize_data_source_kind(kind) == kind


def test_ui_choices_are_the_visible_specs_in_registry_order():
    assert tuple(kind for kind, _ in DATA_SOURCE_CHOICES) == UI_KINDS
    assert {kind for kind, _ in DATA_SOURCE_CHOICES}.isdisjoint(HIDDEN_KINDS)
    assert ALL_KINDS - set(UI_KINDS) == HIDDEN_KINDS


def test_new_sources_are_selectable_from_the_gui():
    ui = {kind for kind, _ in DATA_SOURCE_CHOICES}
    assert {"baostock", "binance", "westock"} <= ui


def test_domestic_share_list_holds_every_a_share_feed():
    # The four hand-maintained tuples this list replaced all agreed on these.
    assert {"akshare", "eastmoney", "tushare", "baostock", "westock"} <= set(DOMESTIC_A_SHARE_KINDS)
    assert is_domestic_a_share("baostock")
    assert is_domestic_a_share("westock")
    # TradingView can serve an A-share code but is not a domestic feed:
    # treating it as one would rewrite crypto/futures symbols into codes.
    assert not is_domestic_a_share("tradingview")
    assert not is_domestic_a_share("binance")
    assert not is_domestic_a_share("mt5")
    assert not is_domestic_a_share(None)


def test_kinds_for_market_matches_market_coverage():
    assert "westock" in kinds_for_market("cn_hk")
    assert "baostock" not in kinds_for_market("cn_hk")
    assert kinds_for_market("crypto") == ("tradingview", "binance", "yfinance")


def test_throttled_sources_clamp_the_refresh_interval():
    assert is_throttled("eastmoney")
    assert is_throttled("baostock")
    assert not is_throttled("mt5")
    assert min_refresh_interval_ms("baostock", 1000) == 2500
    assert min_refresh_interval_ms("baostock", 5000) == 5000
    assert min_refresh_interval_ms("mt5", 1000) == 1000
    assert min_refresh_interval_ms(None, 1000) == 1000


def test_placeholders_and_tooltips_are_registry_driven():
    assert "BTCUSDT" in source_placeholder("binance")
    assert "600519" in source_placeholder("baostock")
    assert source_placeholder("unknown") == ""
    for spec in SOURCE_SPECS:
        if spec.ui_visible:
            assert spec.tooltip.strip(), spec.kind


def test_source_default_timeframe_is_supported_by_that_source():
    for spec in SOURCE_SPECS:
        supported = source_supported_timeframes(spec.kind)
        if supported is None:
            continue
        assert spec.default_timeframe in supported, spec.kind
        assert source_default_timeframe(spec.kind) == spec.default_timeframe
    assert source_default_timeframe("unknown", "15m") == "15m"


def test_labels_and_symbols_come_from_the_registry():
    assert data_source_label("baostock") == source_spec("baostock").label
    assert data_source_label("binance") == source_spec("binance").label
    assert data_source_label("nope") == "MT5"
    assert default_symbol_for_kind("binance") == "BTCUSDT"
    assert default_symbol_for_kind("baostock") == "000001"


def test_hidden_kinds_keep_their_historical_normalization():
    for kind in ("akshare", "eastmoney", "tushare", "yfinance"):
        assert normalize_data_source_kind(kind) == kind
    assert normalize_data_source_kind("nonsense") == "mt5"


@pytest.mark.parametrize("market", sorted(registry.MARKET_LABELS))
def test_every_market_label_is_rendered(market):
    assert registry.MARKET_LABELS[market].strip()
    assert kinds_for_market(market)


def test_settings_literal_matches_the_registry():
    """settings.py keeps its own Literal; drift would silently reject a source.

    The model validator normalizes against ALL_KINDS, but the annotated type is
    what editors and pydantic documentation show — a kind missing there is a
    trap, and a kind present there but missing in the registry gets rewritten
    to MT5 at load time.
    """
    from typing import get_args

    from pa_agent.config.settings import DataSourceKind as SettingsKind

    assert set(get_args(SettingsKind)) == set(ALL_KINDS)
