"""Baostock (证券宝) A-share K-line data source.

Baostock is a free HTTP API with no key.  It is also the backup source East
Money already falls back to when its rolling minute window is exceeded, but
until now it could not be selected on its own: ``_BaostockSession`` lived in
the East Money module and only ran as a hidden fallback.

The socket singleton is not thread-safe, so every query goes through
``BaostockSession.execute`` (one class-level lock, one login, one retry).
Both this source and the East Money fallback share that session.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

from pa_agent.data.ashare_common import (
    ashare_head_bar_live,
    bar_trade_date,
    cn_now,
    index_symbol_for_api,
    is_index_symbol,
    normalize_ashare_symbol,
    resample_rows_to_4h,
    rows_to_kline_bars,
)
from pa_agent.data.ashare_common import (
    baostock_shares_to_lots as _shares_to_lots,
)
from pa_agent.data.base import (
    DataSource,
    DataSourceTransientError,
    KlineBar,
)
from pa_agent.data.eastmoney_baostock import (
    BaostockSession,
    baostock_adjust_flag,
    baostock_code,
    calendar_days_for_bars,
    collect_baostock_rows,
)
from pa_agent.data.kline_adjust import get_kline_adjust
from pa_agent.data.sources_registry import source_supported_timeframes

logger = logging.getLogger(__name__)

BAOSTOCK_MAX_BARS = 2000

_FREQUENCY: dict[str, str] = {"1d": "d", "1w": "w", "1M": "m"}
_MINUTE_FREQUENCY: dict[str, str] = {"5m": "5", "15m": "15", "30m": "30", "1h": "60"}
_DAILY_FIELDS = "date,code,open,high,low,close,volume,amount,pctChg"
_MINUTE_FIELDS = "date,time,code,open,high,low,close,volume,amount"
# Same mapping as the East Money / AkShare fallbacks (see baostock_adjust_flag).
_ADJUST_FLAG = baostock_adjust_flag

_PRESET_SYMBOLS: tuple[str, ...] = (
    "600000",
    "600519",
    "000001",
    "000300",
    "sh000001",
    "399001",
    "399006",
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


def normalize_baostock_symbol(symbol: str) -> str:
    """Return the 6-digit code (or ``sh000300`` for an index) to query."""
    return normalize_ashare_symbol(symbol)


def _query_code(symbol: str) -> str:
    """``600519`` → ``sh.600519``; ``000300`` → ``sh.000300`` (index)."""
    if is_index_symbol(symbol):
        api = index_symbol_for_api(symbol)  # e.g. "sh000300"
        return f"{api[:2]}.{api[2:]}"
    return baostock_code(symbol)


def _adjust_flag() -> str:
    return _ADJUST_FLAG(get_kline_adjust())


def _ts_ms_of_daily(day: str) -> int:
    from pa_agent.data.ashare_common import row_time_to_ts_ms

    return row_time_to_ts_ms(day)


def _ts_ms_of_minute(stamp: str) -> int:
    """Baostock minute stamps look like ``20261103103000000``."""
    digits = "".join(ch for ch in str(stamp) if ch.isdigit())
    if len(digits) < 14:
        return 0
    from pa_agent.data.ashare_common import row_time_to_ts_ms

    text = (
        f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
    )
    return row_time_to_ts_ms(text)


def _float_of(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if out == out else 0.0  # NaN guard


def head_bar_still_forming(ts_open_ms: int, timeframe: str, now: datetime | None = None) -> bool:
    """Whether the newest Baostock row is a bar the exchange is still filling.

    Baostock stamps a weekly bar with the last trading day inside that week
    and a monthly bar with the last trading day of the month, so "same date as
    today" is only the right test for daily and intraday bars.  Weekly/monthly
    window logic is shared with the other A-share sources via
    ``ashare_head_bar_live`` so the same chart can't disagree across sources.
    """
    now = now or cn_now()
    tf = str(timeframe or "").strip()
    if tf in ("1w", "1M"):
        return ashare_head_bar_live(tf, now, head_ts_open_ms=ts_open_ms)
    if bar_trade_date(ts_open_ms) != now.date():
        return False
    return ashare_head_bar_live("1d" if tf == "1d" else tf, now)


class BaostockSource(DataSource):
    """A-share daily / weekly / monthly / intraday bars from Baostock."""

    def __init__(self) -> None:
        self._symbol: str = ""
        self._timeframe: str = ""
        self._connected: bool = False
        self._cache_key: tuple[str, str, str] | None = None
        self._cache_ts: float = 0.0
        self._cache_bars: list[KlineBar] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Verify the package is importable; the login happens on first query.

        A real ``bs.login()`` here would stall every data-source switch on a
        network round trip, and the GUI switches sources synchronously.
        """
        try:
            import baostock  # noqa: F401
        except ImportError as exc:
            raise DataSourceTransientError("baostock 未安装 — 执行: pip install baostock") from exc
        self._connected = True
        logger.info("BaostockSource connected")

    def disconnect(self) -> None:
        self._connected = False
        self._cache_bars = []
        self._cache_key = None
        BaostockSession.logout()
        logger.info("BaostockSource disconnected")

    # ── Discovery ─────────────────────────────────────────────────────────────

    def list_symbols(self) -> list[str]:
        return list(_PRESET_SYMBOLS)

    def supported_timeframes(self) -> list[str]:
        return list(source_supported_timeframes("baostock") or ())

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, symbol: str, timeframe: str) -> None:
        supported = self.supported_timeframes()
        if timeframe not in supported:
            raise ValueError(f"Baostock 不支持周期 {timeframe!r}；可选 {supported}")
        code = normalize_baostock_symbol(symbol)
        if not code:
            raise ValueError("Baostock 需要 6 位 A 股代码")
        self._symbol = code
        self._timeframe = timeframe
        self._cache_key = None
        logger.info("BaostockSource subscribed: %s %s", code, timeframe)

    def unsubscribe(self) -> None:
        self._symbol = ""
        self._timeframe = ""
        self._cache_key = None
        logger.info("BaostockSource unsubscribed")

    # ── Data fetch ────────────────────────────────────────────────────────────

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        if not self._connected:
            raise DataSourceTransientError("Baostock 未连接：请先 connect()")
        if not self._symbol or not self._timeframe:
            raise DataSourceTransientError("Baostock 未订阅品种/周期")
        if n <= 0:
            return []
        if n > BAOSTOCK_MAX_BARS:
            raise DataSourceTransientError(f"Baostock 单次最多返回 {BAOSTOCK_MAX_BARS} 条 K 线")

        adjust = _adjust_flag()
        key = (self._symbol, self._timeframe, adjust)
        ttl = _env_float("PA_AGENT_BAOSTOCK_CACHE_TTL_S", 3.0, minimum=0.0, maximum=60.0)
        now_mono = time.monotonic()
        if (
            self._cache_key == key
            and len(self._cache_bars) >= n
            and now_mono - self._cache_ts < ttl
        ):
            return list(self._cache_bars[:n])

        rows_asc = self._fetch_rows_asc(self._symbol, self._timeframe, n)
        if not rows_asc:
            raise DataSourceTransientError(
                f"Baostock 未返回 K 线：{self._symbol} {self._timeframe}"
            )

        now = cn_now()
        rows_newest = list(reversed(rows_asc[-n:]))
        head_live = head_bar_still_forming(int(rows_newest[0]["ts_open"]), self._timeframe, now)
        for i, row in enumerate(rows_newest):
            row["closed"] = not (i == 0 and head_live)

        bars = rows_to_kline_bars(rows_newest, n)
        self._cache_key = key
        self._cache_ts = time.monotonic()
        self._cache_bars = list(bars)
        return bars

    def _fetch_rows_asc(self, symbol: str, timeframe: str, n: int) -> list[dict[str, Any]]:
        if timeframe == "4h":
            hourly = self._fetch_rows_asc(symbol, "1h", n * 4 + 8)
            return resample_rows_to_4h(hourly)[-(n + 4) :]
        if timeframe in _MINUTE_FREQUENCY:
            return self._fetch_minute_asc(symbol, timeframe, n)
        return self._fetch_period_asc(symbol, timeframe, n)

    def _fetch_period_asc(self, symbol: str, timeframe: str, n: int) -> list[dict[str, Any]]:
        frequency = _FREQUENCY.get(timeframe)
        if frequency is None:
            raise DataSourceTransientError(f"Baostock 不支持周期: {timeframe}")
        if frequency == "d":
            cal_days = min(max(int(n * 1.45) + 25, 75), 420)
        elif frequency == "w":
            cal_days = min(max(int(n * 8.0) + 40, 90), 5000)
        else:
            cal_days = min(max(int(n * 32.0) + 90, 450), 15000)
        now = cn_now()
        start = (now - timedelta(days=cal_days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        code = _query_code(symbol)
        fields = _DAILY_FIELDS
        adjust = _adjust_flag()

        def _query() -> list[list[str]]:
            import baostock as bs

            rs = bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start,
                end_date=end,
                frequency=frequency,
                adjustflag=adjust,
            )
            return collect_baostock_rows(rs)

        data = BaostockSession.execute(f"{timeframe} K线", _query)
        columns = fields.split(",")
        rows: list[dict[str, Any]] = []
        for raw in data:
            record = dict(zip(columns, raw, strict=False))
            ts_ms = _ts_ms_of_daily(record.get("date", ""))
            if ts_ms <= 0:
                continue
            rows.append(
                {
                    "ts_open": ts_ms,
                    "open": _float_of(record.get("open")),
                    "high": _float_of(record.get("high")),
                    "low": _float_of(record.get("low")),
                    "close": _float_of(record.get("close")),
                    "volume": _shares_to_lots(_float_of(record.get("volume"))),
                    "amount": _float_of(record.get("amount")),
                    "pct_chg": _pct_or_none(record.get("pctChg")),
                }
            )
        rows.sort(key=lambda row: row["ts_open"])
        return rows[-(n + 5) :]

    def _fetch_minute_asc(self, symbol: str, timeframe: str, n: int) -> list[dict[str, Any]]:
        frequency = _MINUTE_FREQUENCY[timeframe]
        if is_index_symbol(symbol):
            raise DataSourceTransientError("Baostock 不提供指数分钟线，请改用 1d / 1w / 1M")
        days = calendar_days_for_bars(n)
        now = cn_now()
        start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        code = _query_code(symbol)
        fields = _MINUTE_FIELDS
        adjust = _adjust_flag()

        def _query() -> list[list[str]]:
            import baostock as bs

            rs = bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start,
                end_date=end,
                frequency=frequency,
                adjustflag=adjust,
            )
            return collect_baostock_rows(rs)

        data = BaostockSession.execute(f"{timeframe} 分钟线", _query)
        columns = fields.split(",")
        rows: list[dict[str, Any]] = []
        for raw in data:
            record = dict(zip(columns, raw, strict=False))
            ts_ms = _ts_ms_of_minute(record.get("time", ""))
            if ts_ms <= 0:
                continue
            rows.append(
                {
                    "ts_open": ts_ms,
                    "open": _float_of(record.get("open")),
                    "high": _float_of(record.get("high")),
                    "low": _float_of(record.get("low")),
                    "close": _float_of(record.get("close")),
                    "volume": _shares_to_lots(_float_of(record.get("volume"))),
                    "amount": _float_of(record.get("amount")),
                    "pct_chg": None,
                }
            )
        rows.sort(key=lambda row: row["ts_open"])
        return rows[-n:]


def _pct_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
