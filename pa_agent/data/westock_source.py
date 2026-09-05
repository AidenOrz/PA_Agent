"""WeStock CLI backed K-line data source.

The project data-source interface is synchronous, while WeStock is exposed as
the user-installed Node CLI.  This adapter keeps that boundary small: it only
uses the raw ``kline`` command and turns its structured result into
``KlineBar`` objects.  It deliberately does not make network requests during
``connect``; the first CLI invocation may need npx to download its package.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pa_agent.data.base import (
    DataSource,
    DataSourceTransientError,
    KlineBar,
    normalize_kline_bar,
)
from pa_agent.data.datetime_ts import ts_open_to_ms
from pa_agent.data.kline_adjust import get_kline_adjust

logger = logging.getLogger(__name__)

WESTOCK_NPM_PACKAGE = "westock-data-skillhub@1.0.5"
WESTOCK_MAX_BARS = 2000
_SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("1d", "1w", "1M", "3M", "1y")
_PERIOD_BY_TIMEFRAME: dict[str, str] = {
    "1d": "day",
    "1w": "week",
    "1M": "month",
    "3M": "season",
    "1y": "year",
}
_TIMEFRAME_ALIASES: dict[str, str] = {
    "day": "1d",
    "week": "1w",
    "month": "1M",
    "season": "3M",
    "year": "1y",
}
_CN_TZ = ZoneInfo("Asia/Shanghai")
_HK_TZ = ZoneInfo("Asia/Hong_Kong")
_US_TZ = ZoneInfo("America/New_York")
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PREFIXED_CODE_RE = re.compile(r"^(sh|sz|bj)(\d{6})$", re.IGNORECASE)
_HK_CODE_RE = re.compile(r"^hk(\d{1,5})$", re.IGNORECASE)
_US_CODE_RE = re.compile(r"^us([A-Za-z][A-Za-z0-9._-]*)$", re.IGNORECASE)
_SIX_DIGIT_RE = re.compile(r"^\d{6}$")

_PRESET_SYMBOLS: tuple[str, ...] = (
    "sh600000",
    "sh600519",
    "sz000001",
    "sh000001",
    "sh000300",
    "hk00700",
    "usAAPL",
)
_PRICE_KEYS = {
    "open",
    "开盘",
    "last",
    "close",
    "收盘",
    "closeprice",
    "最高",
    "high",
    "最高价",
    "low",
    "最低",
    "最低价",
}


def normalize_westock_timeframe(timeframe: str) -> str:
    """Return the application's canonical spelling for a WeStock period."""
    raw = str(timeframe or "").strip()
    if raw in _PERIOD_BY_TIMEFRAME:
        return raw
    alias = _TIMEFRAME_ALIASES.get(raw.lower())
    if alias is not None:
        return alias
    raise ValueError(
        f"Unsupported WeStock timeframe: {timeframe!r}. "
        f"Use one of {list(_SUPPORTED_TIMEFRAMES)}"
    )


def _infer_ashare_prefix(code: str) -> str:
    """Infer Tencent's market prefix for a bare six-digit A-share code."""
    if code.startswith(("4", "8")):
        return "bj"
    if code.startswith(("0", "2", "3")):
        return "sz"
    return "sh"


def normalize_westock_symbol(symbol: str) -> str:
    """Normalize user input to WeStock's ``sh/sz/bj/hk/us`` code format."""
    raw = str(symbol or "").strip()
    if not raw:
        return ""

    prefixed = _PREFIXED_CODE_RE.fullmatch(raw)
    if prefixed:
        return f"{prefixed.group(1).lower()}{prefixed.group(2)}"

    hk = _HK_CODE_RE.fullmatch(raw)
    if hk:
        return f"hk{int(hk.group(1)):05d}"

    us = _US_CODE_RE.fullmatch(raw)
    if us:
        return f"us{us.group(1).upper()}"

    if _SIX_DIGIT_RE.fullmatch(raw):
        return f"{_infer_ashare_prefix(raw)}{raw}"

    return ""


def _npx_command() -> str | None:
    """Resolve a non-interactive npx executable on Windows and POSIX."""
    if os.name == "nt":
        return shutil.which("npx.cmd") or shutil.which("npx")
    return shutil.which("npx")


def _node_command() -> str | None:
    return shutil.which("node")


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value):
        return default
    return min(max(value, minimum), maximum)


def _package_name() -> str:
    package = os.environ.get("PA_AGENT_WESTOCK_PACKAGE", WESTOCK_NPM_PACKAGE).strip()
    if not package or any(ch.isspace() for ch in package):
        raise DataSourceTransientError("PA_AGENT_WESTOCK_PACKAGE 配置无效")
    return package


def _adjustment_arg() -> str | None:
    adjust = str(get_kline_adjust() or "qfq").strip().lower()
    if adjust == "none":
        # The project data-source document records that bfq is not accepted by
        # some STAR-board requests; omitting --fq is the compatible path there.
        return None
    if adjust not in {"qfq", "hfq"}:
        adjust = "qfq"
    return adjust


def build_westock_kline_command(
    npx: str,
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[str]:
    """Build the exact CLI argv used by :class:`WeStockSource`."""
    canonical_tf = normalize_westock_timeframe(timeframe)
    if not 1 <= int(limit) <= WESTOCK_MAX_BARS:
        raise ValueError(f"WeStock limit must be between 1 and {WESTOCK_MAX_BARS}")
    code = normalize_westock_symbol(symbol)
    if not code:
        raise ValueError(f"Invalid WeStock symbol: {symbol!r}")
    command = [
        npx,
        "-y",
        _package_name(),
        "kline",
        code,
        "--period",
        _PERIOD_BY_TIMEFRAME[canonical_tf],
        "--limit",
        str(int(limit)),
        "--raw",
    ]
    adjustment = _adjustment_arg()
    if adjustment is not None:
        command.extend(("--fq", adjustment))
    return command


def _json_payload(text: str) -> Any:
    """Decode JSON even when npx adds ANSI/log lines around the payload."""
    cleaned = _ANSI_RE.sub("", str(text or "")).lstrip("\ufeff \r\n\t")
    if not cleaned:
        raise DataSourceTransientError("WeStock 返回为空")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            return value
    raise DataSourceTransientError("WeStock 返回不是有效 JSON")


def _error_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("error", "message", "msg", "detail", "错误"):
            if key in value:
                detail = _error_text(value[key])
                if detail:
                    return detail
        return ""
    if isinstance(value, list):
        return "; ".join(item for item in (_error_text(v) for v in value) if item)
    return str(value or "").strip()


def _rows_from_payload(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 6:
        return []
    if isinstance(value, list):
        rows = [item for item in value if isinstance(item, dict)]
        if rows:
            return rows
        for item in value:
            rows = _rows_from_payload(item, depth=depth + 1)
            if rows:
                return rows
        return []
    if not isinstance(value, dict):
        return []
    if value.get("success") is False or value.get("ok") is False:
        detail = _error_text(value) or "未知错误"
        raise DataSourceTransientError(f"WeStock 查询失败：{detail[:300]}")

    lowered = {str(key).strip().lower() for key in value}
    if len(lowered & _PRICE_KEYS) >= 3:
        return [value]
    for key in ("data", "result", "rows", "items", "records", "list", "klines"):
        if key in value:
            rows = _rows_from_payload(value[key], depth=depth + 1)
            if rows:
                return rows
    return []


def _field(row: dict[str, Any], *names: str) -> Any:
    values = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in values:
            return values[name.lower()]
    return None


def _number(value: Any, *, required: bool = False) -> float | None:
    if value is None:
        if required:
            return None
        return 0.0
    if isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"null", "none", "-", "--", "nan"}:
        return None if required else 0.0
    try:
        number = float(text.rstrip("%"))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _market_timezone(symbol: str) -> ZoneInfo:
    if symbol.startswith("hk"):
        return _HK_TZ
    if symbol.startswith("us"):
        return _US_TZ
    return _CN_TZ


def _timestamp_ms(value: Any, *, symbol: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            return None
        if number >= 100_000_000_000:
            return int(number)
        if number >= 100_000_000:
            return int(number * 1000)
        value = str(int(number))

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        if len(text) == 8:
            try:
                parsed = datetime.strptime(text, "%Y%m%d")
            except ValueError:
                return None
            return int(parsed.replace(tzinfo=_market_timezone(symbol)).timestamp() * 1000)
        if len(text) in (10, 13):
            return int(ts_open_to_ms(float(text)))
    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_market_timezone(symbol))
    return int(parsed.timestamp() * 1000)


def _session_open(symbol: str, now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    if symbol.startswith("us") or symbol.startswith("hk"):
        return 9 * 60 + 30 <= minutes < 16 * 60
    return 9 * 60 + 30 <= minutes < 11 * 60 + 30 or 13 * 60 <= minutes < 15 * 60


def _past_daily_close(symbol: str, now: datetime) -> bool:
    """True after the market's final cash-session close on *now*'s day.

    Unlike :func:`_session_open` this ignores the A-share lunch break: a weekly
    bar is still forming during Friday's lunch break, only the post-close time
    ends the week.
    """
    minutes = now.hour * 60 + now.minute
    if symbol.startswith("us") or symbol.startswith("hk"):
        return minutes >= 16 * 60
    return minutes >= 15 * 60


def _is_forming_bar(symbol: str, timeframe: str, ts_open_ms: int) -> bool:
    """True when the newest bar's calendar period has not finished yet.

    A bar marked forming is dropped from the AI analysis frame, so this check
    must stay conservative: whenever unsure, prefer forming (the bar is then
    discarded) over closed (an unfinished bar would be analysed as K1).
    """
    zone = _market_timezone(symbol)
    now = datetime.now(tz=zone)
    return _is_forming_bar_at(symbol, timeframe, ts_open_ms, now)


def _is_forming_bar_at(symbol: str, timeframe: str, ts_open_ms: int, now: datetime) -> bool:
    bar_date = datetime.fromtimestamp(ts_open_ms / 1000, tz=now.tzinfo).date()
    today = now.date()
    if timeframe == "1d":
        return now.date() == bar_date and _session_open(symbol, now)
    if timeframe == "1w":
        # Same ISO week: forming until the week's last session has closed.
        if bar_date.isocalendar()[:2] != today.isocalendar()[:2]:
            return False
        if now.weekday() >= 5:
            return False
        if now.weekday() == 4 and _past_daily_close(symbol, now):
            return False
        return True
    if timeframe == "1M":
        return (bar_date.year, bar_date.month) == (today.year, today.month)
    if timeframe == "3M":
        return (bar_date.year, (bar_date.month - 1) // 3) == (
            today.year,
            (today.month - 1) // 3,
        )
    if timeframe == "1y":
        return bar_date.year == today.year
    return False


def _row_to_bar_data(row: dict[str, Any], *, symbol: str) -> dict[str, Any] | None:
    timestamp = _timestamp_ms(
        _field(row, "date", "datetime", "time", "timestamp", "ts"),
        symbol=symbol,
    )
    opening = _number(_field(row, "open", "opening", "开盘"), required=True)
    closing = _number(
        _field(row, "last", "close", "closeprice", "closing", "收盘"),
        required=True,
    )
    high = _number(_field(row, "high", "最高", "最高价"), required=True)
    low = _number(_field(row, "low", "最低", "最低价"), required=True)
    if timestamp is None or None in (opening, closing, high, low):
        return None
    pct_raw = _field(row, "pct_chg", "change_pct", "changepercent", "涨跌幅")
    pct_chg = None if pct_raw is None else _number(pct_raw)
    return {
        "ts_open": timestamp,
        "open": opening,
        "high": high,
        "low": low,
        "close": closing,
        "volume": _number(_field(row, "volume", "vol", "成交量")) or 0.0,
        "amount": _number(_field(row, "amount", "turnover", "成交额")) or 0.0,
        "pct_chg": pct_chg,
    }


def _rows_to_bars(
    rows: list[dict[str, Any]], *, symbol: str, timeframe: str, n: int
) -> list[KlineBar]:
    by_timestamp: dict[int, dict[str, Any]] = {}
    for row in rows:
        parsed = _row_to_bar_data(row, symbol=symbol)
        if parsed is not None:
            by_timestamp[int(parsed["ts_open"])] = parsed
    ordered = sorted(by_timestamp.values(), key=lambda item: item["ts_open"], reverse=True)
    bars: list[KlineBar] = []
    for index, row in enumerate(ordered[:n]):
        forming = index == 0 and _is_forming_bar(symbol, timeframe, int(row["ts_open"]))
        bars.append(
            normalize_kline_bar(
                KlineBar(
                    seq=index + 1,
                    ts_open=float(row["ts_open"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    amount=float(row["amount"]),
                    pct_chg=row["pct_chg"],
                    closed=not forming,
                )
            )
        )
    return bars


class WeStockSource(DataSource):
    """Polling K-line source backed by the user's WeStock npm package."""

    def __init__(self) -> None:
        self._symbol = ""
        self._timeframe = ""
        self._connected = False
        self._npx: str | None = None
        self._cache_bars: list[KlineBar] = []
        self._cache_key: tuple[str, str, str] | None = None
        self._cache_ts = 0.0

    def connect(self) -> None:
        node = _node_command()
        npx = _npx_command()
        if node is None or npx is None:
            raise DataSourceTransientError(
                "WeStock 需要 Node.js >= 18 和 npx，请先安装 Node.js"
            )
        try:
            result = subprocess.run(
                [node, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
            version_text = (result.stdout or "").strip().lstrip("v")
            major = int(version_text.split(".", 1)[0])
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise DataSourceTransientError("无法确认 Node.js 版本") from exc
        if major < 18:
            raise DataSourceTransientError(
                f"WeStock 需要 Node.js >= 18，当前为 v{version_text or 'unknown'}"
            )
        self._npx = npx
        self._connected = True
        logger.info("WeStockSource connected using %s", npx)

    def disconnect(self) -> None:
        self._connected = False
        self._npx = None
        self.unsubscribe()
        logger.info("WeStockSource disconnected")

    def list_symbols(self) -> list[str]:
        return list(_PRESET_SYMBOLS)

    def supported_timeframes(self) -> list[str]:
        return list(_SUPPORTED_TIMEFRAMES)

    def subscribe(self, symbol: str, timeframe: str) -> None:
        canonical_tf = normalize_westock_timeframe(timeframe)
        code = normalize_westock_symbol(symbol)
        if not code:
            raise ValueError(
                "WeStock 品种无效，请使用 A 股 6 位代码、sh/sz/bj 前缀、"
                "hk 五位代码或 us 股票代码"
            )
        self._symbol = code
        self._timeframe = canonical_tf
        self._clear_cache()
        logger.info("WeStockSource subscribed: %s %s", code, canonical_tf)

    def unsubscribe(self) -> None:
        self._symbol = ""
        self._timeframe = ""
        self._clear_cache()
        logger.info("WeStockSource unsubscribed")

    def is_symbol_available(self, symbol: str) -> bool:
        return bool(normalize_westock_symbol(symbol))

    def canonical_symbol(self, symbol: str) -> str:
        """Mirror what :meth:`subscribe` stores, so raw input can be compared
        against the subscription (a bare 6-digit code becomes ``sz002475``)."""
        return normalize_westock_symbol(symbol)

    def canonical_timeframe(self, timeframe: str) -> str:
        try:
            return normalize_westock_timeframe(timeframe)
        except ValueError:
            return (timeframe or "").strip()

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        if not self._connected:
            raise DataSourceTransientError("WeStock 未连接")
        if not self._symbol or not self._timeframe:
            raise DataSourceTransientError("WeStock 未订阅品种/周期")
        if n <= 0:
            return []
        if n > WESTOCK_MAX_BARS:
            raise DataSourceTransientError(
                f"WeStock 单次最多返回 {WESTOCK_MAX_BARS} 条 K 线"
            )

        adjust = str(get_kline_adjust() or "qfq").strip().lower()
        key = (self._symbol, self._timeframe, adjust)
        ttl = _env_float(
            "PA_AGENT_WESTOCK_CACHE_TTL_S", 3.0, minimum=0.0, maximum=60.0
        )
        now = time.monotonic()
        if (
            self._cache_key == key
            and len(self._cache_bars) >= n
            and now - self._cache_ts < ttl
        ):
            return list(self._cache_bars[:n])

        npx = self._npx or _npx_command()
        if npx is None:
            raise DataSourceTransientError("找不到 npx，请先安装 Node.js")
        command = build_westock_kline_command(npx, self._symbol, self._timeframe, n)
        timeout_s = _env_float(
            "PA_AGENT_WESTOCK_TIMEOUT_S", 30.0, minimum=1.0, maximum=300.0
        )
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DataSourceTransientError(
                f"WeStock 查询超时（>{timeout_s:g}s）"
            ) from exc
        except OSError as exc:
            raise DataSourceTransientError(f"WeStock CLI 启动失败：{exc}") from exc

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        try:
            payload = _json_payload(stdout)
        except DataSourceTransientError:
            if result.returncode != 0 and stderr.strip():
                raise DataSourceTransientError(
                    f"WeStock CLI 失败（退出码 {result.returncode}）：{stderr.strip()[:300]}"
                ) from None
            raise
        if result.returncode != 0:
            detail = _error_text(payload) or stderr.strip() or "未知错误"
            raise DataSourceTransientError(
                f"WeStock CLI 失败（退出码 {result.returncode}）：{detail[:300]}"
            )

        rows = _rows_from_payload(payload)
        bars = _rows_to_bars(
            rows, symbol=self._symbol, timeframe=self._timeframe, n=n
        )
        if not bars:
            raise DataSourceTransientError(
                f"WeStock 未返回有效 K 线：{self._symbol} {self._timeframe}"
            )
        self._cache_key = key
        self._cache_ts = time.monotonic()
        self._cache_bars = bars
        return list(bars)

    def _clear_cache(self) -> None:
        self._cache_bars = []
        self._cache_key = None
        self._cache_ts = 0.0
