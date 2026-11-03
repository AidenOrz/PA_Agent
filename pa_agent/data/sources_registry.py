"""Single registry of every K-line data source the app knows about.

The source list used to be spread over four places (the factory choices, the
factory hidden kinds, two string tuples inside the GUI window and one in
market_defaults), which is why adding a source meant hunting for tuples.
Everything the UI, the factory and the settings layer need to know about a
kind now lives in SOURCE_SPECS; the rest of the package queries it instead of
hard-coding kind names.

WeStock also covers Hong Kong and US symbols, so "which sources serve China
A-shares" is expressed as market coverage (markets) rather than as yet another
hand-maintained tuple: DOMESTIC_A_SHARE_KINDS is derived from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pa_agent.data.market_defaults import A_SHARE_DEFAULT_SYMBOL

DataSourceKind = Literal[
    "mt5",
    "tradingview",
    "westock",
    "akshare",
    "eastmoney",
    "tushare",
    "yfinance",
    "baostock",
    "binance",
]

#: Market ids. A source may serve several of them (WeStock covers A-share,
#: Hong Kong and US symbols; TradingView covers whatever it can resolve).
MarketId = Literal["global", "cn_a", "cn_hk", "us", "crypto"]

MARKET_LABELS: dict[str, str] = {
    "global": "全球（外汇 / 黄金 / 指数）",
    "cn_a": "中国 A 股（沪深京）",
    "cn_hk": "中国港股",
    "us": "美股",
    "crypto": "加密货币",
}


@dataclass(frozen=True)
class SourceSpec:
    """Everything that differs between two data-source kinds."""

    kind: str
    label: str
    #: Markets whose symbols this source can serve (capability, not focus:
    #: TradingView can resolve an A-share code, but it is not an A-share feed).
    markets: frozenset[str]
    default_symbol: str
    default_timeframe: str = "15m"
    #: Listed in the GUI combo box. Hidden kinds stay selectable through
    #: settings.json only (they are fallbacks driven by other code paths).
    ui_visible: bool = False
    #: Symbol field placeholder shown while this source is active.
    placeholder: str = ""
    #: Combo-box tooltip fragment.
    tooltip: str = ""
    #: Lower bound for the refresh interval. HTTP/socket sources that throttle
    #: bursts declare it here so the GUI does not hammer them at 1 Hz.
    min_refresh_interval_ms: int | None = None
    #: Timeframes the source accepts. None = ask the instance
    #: (DataSource.supported_timeframes()), which is the case for MT5 and
    #: TradingView where the answer depends on the terminal/venue.
    supported_timeframes: tuple[str, ...] | None = None
    #: A mainland-China feed: 6-digit A-share codes are native here, so the
    #: symbol normalizer treats them as codes (and not as "gold missing") and
    #: the GUI throttles refreshes. TradingView can *serve* an A-share code but
    #: is not such a feed, so it does not set this flag.
    domestic: bool = False


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        kind="mt5",
        label="MT5",
        markets=frozenset({"global"}),
        default_symbol="XAUUSDm",
        default_timeframe="15m",
        ui_visible=True,
        placeholder="输入 MT5 品种名，如 XAUUSDm…",
        tooltip="MetaTrader 5 终端（需已登录）",
    ),
    SourceSpec(
        kind="tradingview",
        label="TradingView",
        markets=frozenset({"global", "cn_a", "cn_hk", "us", "crypto"}),
        default_symbol="XAUUSD",
        default_timeframe="15m",
        ui_visible=True,
        placeholder="A股 6 位 / 港股 1810 / 名称 小米集团；交易所可自动；或 XAUUSD+OANDA",
        tooltip="TradingView（tvDatafeed，需可访问 data.tradingview.com）",
    ),
    SourceSpec(
        kind="baostock",
        label="Baostock（A股）",
        markets=frozenset({"cn_a"}),
        default_symbol=A_SHARE_DEFAULT_SYMBOL,
        default_timeframe="1d",
        ui_visible=True,
        placeholder="A股 6 位代码，如 600519；指数 000300 或 sh000300",
        tooltip="Baostock（免费 A 股日线/周线/月线与分钟线）",
        min_refresh_interval_ms=2500,
        supported_timeframes=("1d", "1w", "1M", "5m", "15m", "30m", "1h", "4h"),
        domestic=True,
    ),
    SourceSpec(
        kind="westock",
        label="WeStock",
        markets=frozenset({"cn_a", "cn_hk", "us"}),
        default_symbol=A_SHARE_DEFAULT_SYMBOL,
        default_timeframe="1d",
        ui_visible=True,
        placeholder="A股 6 位或 sh/sz/bj 前缀；港股 hk00700；美股 usAAPL",
        tooltip="WeStock（Node.js/npx CLI，需网络）",
        supported_timeframes=("1d", "1w", "1M", "3M", "1y"),
        domestic=True,
    ),
    SourceSpec(
        kind="binance",
        label="Binance（币安）",
        markets=frozenset({"crypto"}),
        default_symbol="BTCUSDT",
        default_timeframe="15m",
        ui_visible=True,
        placeholder="币安交易对，如 BTCUSDT（可写 btc/usdt）",
        tooltip="Binance 现货 REST（公开行情，无需 API Key；国内网络需代理）",
        supported_timeframes=("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"),
    ),
    SourceSpec(
        kind="akshare",
        label="AkShare",
        markets=frozenset({"cn_a"}),
        default_symbol=A_SHARE_DEFAULT_SYMBOL,
        default_timeframe="1h",
        placeholder="A股 6 位代码，如 600519；指数 000300 或 sh000300",
        min_refresh_interval_ms=2500,
        supported_timeframes=("1h", "4h", "1d"),
        domestic=True,
    ),
    SourceSpec(
        kind="eastmoney",
        label="东方财富",
        markets=frozenset({"cn_a"}),
        default_symbol=A_SHARE_DEFAULT_SYMBOL,
        default_timeframe="1h",
        placeholder="A股 6 位代码，如 600519；指数 000300 或 sh000300",
        min_refresh_interval_ms=2500,
        supported_timeframes=("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"),
        domestic=True,
    ),
    SourceSpec(
        kind="tushare",
        label="Tushare(A股)",
        markets=frozenset({"cn_a"}),
        default_symbol=A_SHARE_DEFAULT_SYMBOL,
        default_timeframe="1d",
        placeholder="A股 6 位代码，如 600519；指数 000300 或 sh000300",
        min_refresh_interval_ms=2500,
        supported_timeframes=("1m", "5m", "15m", "30m", "1h", "1d"),
        domestic=True,
    ),
    SourceSpec(
        kind="yfinance",
        label="YFinance",
        markets=frozenset({"global", "crypto"}),
        default_symbol="GC=F",
        default_timeframe="1d",
        placeholder="Yahoo 代码，如 GC=F / BTC-USD",
    ),
)

_BY_KIND: dict[str, SourceSpec] = {spec.kind: spec for spec in SOURCE_SPECS}

ALL_KINDS: frozenset[str] = frozenset(_BY_KIND)

UI_KINDS: tuple[str, ...] = tuple(spec.kind for spec in SOURCE_SPECS if spec.ui_visible)

HIDDEN_KINDS: frozenset[str] = ALL_KINDS - set(UI_KINDS)


def source_spec(kind: str | None) -> SourceSpec | None:
    """Return the spec for kind, or None when it is unknown."""
    return _BY_KIND.get(str(kind or ""))


def kinds_for_market(market: str) -> tuple[str, ...]:
    """Kinds that can serve market, in registry order."""
    return tuple(spec.kind for spec in SOURCE_SPECS if market in spec.markets)


#: Shared list of the domestic (mainland China) feeds. The four places that
#: used to spell this out by hand — the symbol normalizer, the GUI refresh
#: throttle, the symbol placeholder and the factory hidden kinds — read this
#: list now, so adding an A-share feed is a one-line change here. WeStock
#: belongs to it even though its label does not say "A股": it serves 6-digit
#: codes natively alongside Hong Kong and US symbols.
DOMESTIC_A_SHARE_KINDS: tuple[str, ...] = tuple(spec.kind for spec in SOURCE_SPECS if spec.domestic)
DOMESTIC_HK_KINDS: tuple[str, ...] = kinds_for_market("cn_hk")

_A_SHARE_KIND_SET = frozenset(DOMESTIC_A_SHARE_KINDS)


def is_domestic_a_share(kind: str | None) -> bool:
    """True when kind serves A-share symbols (6-digit codes, sh/sz/bj)."""
    return str(kind or "") in _A_SHARE_KIND_SET


def is_throttled(kind: str | None) -> bool:
    """True when kind needs a slower refresh interval than the user asked for."""
    spec = source_spec(kind)
    return spec is not None and spec.min_refresh_interval_ms is not None


def min_refresh_interval_ms(kind: str | None, requested_ms: int) -> int:
    """Clamp requested_ms up to the source own lower bound."""
    spec = source_spec(kind)
    if spec is None or spec.min_refresh_interval_ms is None:
        return requested_ms
    return max(requested_ms, spec.min_refresh_interval_ms)


def source_placeholder(kind: str | None) -> str:
    spec = source_spec(kind)
    return spec.placeholder if spec is not None else ""


def source_tooltip(kind: str | None) -> str:
    spec = source_spec(kind)
    return spec.tooltip if spec is not None else ""


def source_supported_timeframes(kind: str | None) -> tuple[str, ...] | None:
    """Static timeframe list for kind, or None when it is instance-dependent."""
    spec = source_spec(kind)
    return spec.supported_timeframes if spec is not None else None


def source_default_timeframe(kind: str | None, fallback: str = "15m") -> str:
    spec = source_spec(kind)
    return spec.default_timeframe if spec is not None else fallback
