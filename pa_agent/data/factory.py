"""Construct DataSource implementations by kind id."""

from __future__ import annotations

from pa_agent.data.base import DataSource
from pa_agent.data.sources_registry import ALL_KINDS as _ALL_KINDS
from pa_agent.data.sources_registry import (
    HIDDEN_KINDS,
    SOURCE_SPECS,
    DataSourceKind,
    source_spec,
)

#: (kind, label) pairs shown in the data-source combo box.
DATA_SOURCE_CHOICES: tuple[tuple[DataSourceKind, str], ...] = tuple(
    (spec.kind, spec.label) for spec in SOURCE_SPECS if spec.ui_visible
)

# UI-visible sources only — ``eastmoney`` is config/programmatic, not listed.
_HIDDEN_KINDS: frozenset[DataSourceKind] = HIDDEN_KINDS  # type: ignore[assignment]


def default_tradingview_exchange() -> str:
    """Empty string = UI «（自动）» — probe all TV preset venues."""
    return ""


def normalize_data_source_kind(kind: str | None) -> DataSourceKind:
    """Return a supported data-source kind, defaulting to MT5."""
    if kind in _ALL_KINDS:
        return kind  # type: ignore[return-value]
    return "mt5"


def data_source_label(kind: str | None) -> str:
    """Human-readable label for *kind*."""
    normalized = normalize_data_source_kind(kind)
    spec = source_spec(normalized)
    return spec.label if spec is not None else "MT5"


def default_symbol_for_kind(kind: str | None) -> str:
    spec = source_spec(normalize_data_source_kind(kind))
    return spec.default_symbol if spec is not None else "XAUUSDm"


def create_data_source(kind: str | None) -> DataSource:
    """Instantiate a fresh data source for *kind* (not connected)."""
    from pa_agent.config.paths import SETTINGS_JSON_PATH
    from pa_agent.config.settings import load_settings

    normalized = normalize_data_source_kind(kind)
    if normalized == "tradingview":
        from pa_agent.data.tradingview import TradingViewSource

        settings = load_settings(SETTINGS_JSON_PATH)
        return TradingViewSource(
            proxy_override=str(getattr(settings.general, "tradingview_proxy", "") or "")
        )
    if normalized == "westock":
        from pa_agent.data.westock_source import WeStockSource

        return WeStockSource()
    if normalized == "binance":
        from pa_agent.data.binance_source import BinanceSource

        # Binance falls back to the TradingView proxy, then auto-detection, so
        # a user who already configured one proxy does not configure it twice.
        settings = load_settings(SETTINGS_JSON_PATH)
        proxy = str(getattr(settings.general, "binance_proxy", "") or "").strip()
        if not proxy:
            proxy = str(getattr(settings.general, "tradingview_proxy", "") or "").strip()
        return BinanceSource(proxy_override=proxy)
    if normalized == "baostock":
        from pa_agent.data.baostock_source import BaostockSource

        return BaostockSource()
    if normalized == "eastmoney":
        from pa_agent.data.eastmoney_source import EastMoneySource

        return EastMoneySource()
    if normalized == "tushare":
        from pa_agent.data.tushare_source import TushareSource

        return TushareSource(settings=load_settings(SETTINGS_JSON_PATH))
    if normalized == "akshare":
        from pa_agent.data.akshare_source import AkShareSource

        return AkShareSource()
    if normalized == "yfinance":
        from pa_agent.data.yfinance_source import YFinanceSource

        return YFinanceSource()
    from pa_agent.data.mt5 import MT5Source

    return MT5Source()
