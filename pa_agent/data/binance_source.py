"""Binance spot K-line data source (REST, public, no API key).

Uses ``GET /api/v3/klines``, which needs no credentials and returns the same
OHLCV rows the web UI shows.  The endpoint is blocked from mainland China, so
the request goes through the same local proxy discovery the TradingView
source uses (``pa_agent.data.proxy_env``); without a proxy the call simply
fails with a transient error and the refresh loop backs off.

Notes that are easy to get wrong:

* ``klines`` returns oldest-first and the **last row is the bar currently
  being filled**.  It must be flagged ``closed=False`` or the AI is handed an
  unfinished K1.
* Binance uses ``1M`` for a month and ``1m`` for a minute; ``timeframe_to_seconds``
  deliberately refuses ``1M``, so the forming check uses its own interval table.
* The symbol has no separator (``BTCUSDT``).  ``BTC/USDT``, ``btc-usdt`` and
  ``BTCUSDT.P`` style input are normalized instead of rejected, because users
  paste them from every corner of the web.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from pa_agent.data.base import (
    DataSource,
    DataSourceTransientError,
    KlineBar,
    normalize_kline_bar,
)
from pa_agent.data.proxy_env import detect_proxy
from pa_agent.data.sources_registry import source_supported_timeframes

logger = logging.getLogger(__name__)

BINANCE_MAX_BARS = 1000
BINANCE_DEFAULT_HOST = "https://api.binance.com"

#: application timeframe → Binance interval (identical strings, kept explicit).
_INTERVALS: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    "1M": "1M",
}

#: Bar duration in ms, used to tell a forming bar from a closed one.
_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
    "1M": 0,  # calendar month: computed from the bar date instead
}

_QUOTE_ASSETS: tuple[str, ...] = (
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "BUSD",
    "BTC",
    "ETH",
    "BNB",
    "TRY",
    "EUR",
)

_PRESET_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "BTCUSDC",
)


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def normalize_binance_symbol(symbol: str) -> str:
    """``btc/usdt`` / ``BTC-USDT`` / ``BINANCE:btcusdt`` → ``BTCUSDT``."""
    raw = str(symbol or "").strip().upper()
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    # ``BTCUSDT.P`` / ``BTCUSDT.PERP`` are perpetual-futures spellings of the
    # spot pair; the spot REST endpoint rejects the suffix.
    if "." in raw:
        raw = raw.split(".", 1)[0]
    cleaned = "".join(ch for ch in raw if ch.isalnum())
    if cleaned.endswith("PERP") and len(cleaned) > len("PERP"):
        cleaned = cleaned[: -len("PERP")]
    return cleaned


def is_binance_pair(symbol: str) -> bool:
    """Whether *symbol* looks like a Binance spot pair (base + quote asset)."""
    pair = normalize_binance_symbol(symbol)
    if len(pair) < 5 or not pair.isalnum():
        return False
    return any(pair.endswith(quote) and len(pair) > len(quote) for quote in _QUOTE_ASSETS)


def binance_host() -> str:
    return (os.environ.get("PA_AGENT_BINANCE_HOST", "").strip() or BINANCE_DEFAULT_HOST).rstrip("/")


def _month_close_ms(ts_open_ms: int) -> int:
    from datetime import UTC, datetime

    opened = datetime.fromtimestamp(int(ts_open_ms) / 1000, tz=UTC)
    year, month = (opened.year + 1, 1) if opened.month == 12 else (opened.year, opened.month + 1)
    return int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)


def head_bar_still_forming(ts_open_ms: int, interval: str, now_ms: int) -> bool:
    """Whether the newest Binance row is the bar still being filled."""
    if interval == "1M":
        return int(now_ms) < _month_close_ms(ts_open_ms)
    duration = _INTERVAL_MS.get(interval)
    if not duration:
        return False
    return int(now_ms) < int(ts_open_ms) + duration


def _float_of(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if out == out else 0.0


def _request_json(url: str, *, timeout_s: float, proxy_override: str = "") -> Any:
    """GET *url* and decode JSON, routed through the detected local proxy."""
    handlers: list[urllib.request.BaseHandler] = []
    found = detect_proxy(proxy_override)
    if found is not None:
        proxy_url = found[0]
        logger.debug("Binance 走代理 %s（来源 %s）", found[1] + ":" + str(found[2]), found[3])
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pa-agent/0.1 (+binance-klines)",
            "Accept": "application/json",
        },
    )
    with opener.open(request, timeout=timeout_s) as response:
        payload = response.read().decode("utf-8", errors="replace")
    return json.loads(payload)


class BinanceSource(DataSource):
    """Spot K-line data from the public Binance REST API."""

    def __init__(self, proxy_override: str = "") -> None:
        self._symbol: str = ""
        self._timeframe: str = ""
        self._connected: bool = False
        self._proxy_override = (proxy_override or "").strip()
        self._cache_key: tuple[str, str] | None = None
        self._cache_ts: float = 0.0
        self._cache_bars: list[KlineBar] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """No handshake: the endpoint is public, errors surface on first fetch."""
        self._connected = True
        logger.info("BinanceSource connected (%s)", binance_host())

    def disconnect(self) -> None:
        self._connected = False
        self._cache_key = None
        self._cache_bars = []
        logger.info("BinanceSource disconnected")

    def set_proxy_override(self, proxy: str) -> None:
        self._proxy_override = (proxy or "").strip()

    # ── Discovery ─────────────────────────────────────────────────────────────

    def list_symbols(self) -> list[str]:
        return list(_PRESET_SYMBOLS)

    def supported_timeframes(self) -> list[str]:
        return list(source_supported_timeframes("binance") or ())

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, symbol: str, timeframe: str) -> None:
        supported = self.supported_timeframes()
        if timeframe not in supported:
            raise ValueError(f"Binance 不支持周期 {timeframe!r}；可选 {supported}")
        pair = normalize_binance_symbol(symbol)
        if not pair:
            raise ValueError("Binance 需要交易对，如 BTCUSDT")
        if not is_binance_pair(pair):
            raise ValueError(f"{symbol!r} 不像币安现货交易对（例：BTCUSDT / ETHUSDT）")
        self._symbol = pair
        self._timeframe = timeframe
        self._cache_key = None
        logger.info("BinanceSource subscribed: %s %s", pair, timeframe)

    def unsubscribe(self) -> None:
        self._symbol = ""
        self._timeframe = ""
        self._cache_key = None
        logger.info("BinanceSource unsubscribed")

    def canonical_symbol(self, symbol: str) -> str:
        return normalize_binance_symbol(symbol)

    # ── Data fetch ────────────────────────────────────────────────────────────

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        if not self._connected:
            raise DataSourceTransientError("Binance 未连接：请先 connect()")
        if not self._symbol or not self._timeframe:
            raise DataSourceTransientError("Binance 未订阅品种/周期")
        if n <= 0:
            return []
        if n > BINANCE_MAX_BARS:
            raise DataSourceTransientError(f"Binance 单次最多返回 {BINANCE_MAX_BARS} 条 K 线")

        key = (self._symbol, self._timeframe)
        ttl = _env_float("PA_AGENT_BINANCE_CACHE_TTL_S", 2.0, minimum=0.0, maximum=60.0)
        now_mono = time.monotonic()
        if (
            self._cache_key == key
            and len(self._cache_bars) >= n
            and now_mono - self._cache_ts < ttl
        ):
            return list(self._cache_bars[:n])

        interval = _INTERVALS[self._timeframe]
        limit = min(n + 1, BINANCE_MAX_BARS)
        rows = self._fetch_klines(self._symbol, interval, limit)
        if not rows:
            raise DataSourceTransientError(f"Binance 未返回 K 线：{self._symbol} {interval}")

        now_ms = int(time.time() * 1000)
        bars: list[KlineBar] = []
        for i, row in enumerate(reversed(rows[-n:])):
            ts_open = int(_float_of(row[0]))
            forming = i == 0 and head_bar_still_forming(ts_open, interval, now_ms)
            bars.append(
                normalize_kline_bar(
                    KlineBar(
                        seq=i + 1,
                        ts_open=float(ts_open),
                        open=_float_of(row[1]),
                        high=_float_of(row[2]),
                        low=_float_of(row[3]),
                        close=_float_of(row[4]),
                        volume=_float_of(row[5]),
                        amount=_float_of(row[7]),
                        closed=not forming,
                    )
                )
            )
        self._cache_key = key
        self._cache_ts = time.monotonic()
        self._cache_bars = list(bars)
        return bars

    def _fetch_klines(self, symbol: str, interval: str, limit: int) -> list[list[Any]]:
        url = (
            f"{binance_host()}/api/v3/klines?symbol={symbol}" f"&interval={interval}&limit={limit}"
        )
        timeout_s = _env_float("PA_AGENT_BINANCE_TIMEOUT_S", 10.0, minimum=1.0, maximum=60.0)
        try:
            payload = _request_json(url, timeout_s=timeout_s, proxy_override=self._proxy_override)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                detail = ""
            raise DataSourceTransientError(
                f"Binance HTTP {exc.code}：{detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DataSourceTransientError(
                f"Binance 网络不可达（{exc.reason}）；国内网络需配置代理"
            ) from exc
        except json.JSONDecodeError as exc:
            raise DataSourceTransientError(f"Binance 返回非 JSON：{exc}") from exc
        except OSError as exc:
            raise DataSourceTransientError(f"Binance 请求失败：{exc}") from exc

        if not isinstance(payload, list):
            raise DataSourceTransientError(f"Binance 返回格式异常：{str(payload)[:200]}")
        return payload
