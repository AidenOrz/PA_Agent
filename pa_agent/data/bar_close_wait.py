"""Helpers for waiting until the current forming bar closes."""
from __future__ import annotations

import math
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pa_agent.data.base import KlineBar

_TIMEFRAME_SECONDS_RE = re.compile(r"^(\d+)([mhdw])$", re.IGNORECASE)
_CN_TZ = ZoneInfo("Asia/Shanghai")

# Month uses uppercase M in MT5; UI combos use lowercase units only.
_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}


def timeframe_to_seconds(timeframe: str) -> int | None:
    """Map timeframe string (e.g. ``5m``, ``1h``) to bar duration in seconds."""
    tf = str(timeframe or "").strip()
    if not tf:
        return None
    # MT5 and the A-share sources use an uppercase M for a calendar month;
    # it must never be treated as the case-insensitive spelling of minute.
    if tf.endswith("M"):
        return None
    if tf in _TIMEFRAME_SECONDS:
        return _TIMEFRAME_SECONDS[tf]
    m = _TIMEFRAME_SECONDS_RE.match(tf)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 3600
    if unit == "d":
        return n * 86400
    if unit == "w":
        return n * 7 * 86400
    return None


def _calendar_month_close_ms(ts_open_ms: int | float) -> int:
    """Return the next calendar-month boundary for a monthly bar."""
    opened = datetime.fromtimestamp(float(ts_open_ms) / 1000.0, tz=_CN_TZ)
    if opened.month == 12:
        year, month = opened.year + 1, 1
    else:
        year, month = opened.year, opened.month + 1
    close = datetime(year, month, 1, tzinfo=_CN_TZ)
    return int(close.timestamp() * 1000)


def _calendar_week_close_ms(ts_open_ms: int | float) -> int:
    """Return the end of the ISO week the bar opened in (Saturday 00:00 CN).

    A weekly bar opens on Monday and stops changing when the market closes on
    Friday; the weekend is not part of the bar.  Using ``7 * 86400`` would keep
    the bar "forming" for two extra days and drop a finished weekly bar from
    the analysis frame.
    """
    opened = datetime.fromtimestamp(float(ts_open_ms) / 1000.0, tz=_CN_TZ)
    # Friday (weekday 4) 15:00 CN is the last moment the weekly bar can change.
    days_to_friday = 4 - opened.weekday()
    if days_to_friday < 0:
        days_to_friday += 7
    friday = (opened + timedelta(days=days_to_friday)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    return int(friday.timestamp() * 1000)


def _bar_close_ms(ts_open_ms: int | float, timeframe: str) -> int | None:
    """Wall-clock close of the bar that opened at ``ts_open_ms`` (None if unknown)."""
    tf = str(timeframe or "").strip()
    if tf == "1M":
        return _calendar_month_close_ms(ts_open_ms)
    if tf.lower() == "1w":
        return _calendar_week_close_ms(ts_open_ms)
    duration_s = timeframe_to_seconds(tf)
    if duration_s is None:
        return None
    return int(ts_open_ms) + duration_s * 1000


def seconds_until_bar_closes(
    ts_open_ms: int,
    timeframe: str,
    *,
    now_ms: int | None = None,
) -> int | None:
    """Whole seconds until the bar that opened at ``ts_open_ms`` closes."""
    tf = str(timeframe or "").strip()
    if tf == "1M" or tf.lower() == "1w":
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        close_ms = _bar_close_ms(ts_open_ms, tf)
        if close_ms is None:
            return None
        remaining_ms = close_ms - int(now_ms)
        return max(0, int(math.ceil(remaining_ms / 1000)))
    duration_s = timeframe_to_seconds(timeframe)
    if duration_s is None:
        return None
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    # NOTE:
    # Some data sources provide ``ts_open`` with a fixed timezone/base offset.
    # Using absolute ``close_ms = ts_open + duration`` would then make the
    # countdown drift by that whole offset (e.g. ~8h).
    # Instead, compute remaining time within the duration window by taking
    # elapsed % duration. This is robust to constant offsets.
    duration_ms = duration_s * 1000
    elapsed_ms = int(now_ms) - int(ts_open_ms)
    if elapsed_ms == 0:
        return duration_s

    # remainder in [0, duration_ms)
    remainder_ms = elapsed_ms % duration_ms
    if remainder_ms == 0:
        # now exactly on a boundary:
        # - elapsed > 0 → bar already closed
        # - elapsed < 0 → bar "would close" a full duration away (offset case)
        return 0 if elapsed_ms > 0 else duration_s

    remaining_ms = duration_ms - remainder_ms
    return int(math.ceil(remaining_ms / 1000))


def reference_now_ms(
    *,
    now_ms: int | None = None,
    data_source: object | None = None,
) -> int:
    """Wall-clock for forming-bar checks: broker/server time when available, else local.

    When the broker server time lags significantly behind local wall-clock time
    (e.g. over 60 seconds), it means the broker is not sending new ticks
    (market halted / weekend). In that case, fall back to local time so that
    ``is_bar_still_forming`` correctly returns False for stale forming bars.
    """
    if now_ms is not None:
        return int(now_ms)
    local_ms = int(time.time() * 1000)
    if data_source is not None:
        server_time_ms = getattr(data_source, "server_time_ms", None)
        if callable(server_time_ms):
            t = server_time_ms()
            if t is not None:
                server_ms = int(t)
                # If broker time is more than 60 s behind local time, the broker
                # is not sending ticks (weekend / halt). Use local time so that
                # expired bars are not mistakenly treated as still forming.
                if local_ms - server_ms < 60_000:
                    return server_ms
                # Broker time is stale — fall through to local time
    return local_ms


def _looks_like_ashare_symbol(symbol: str | None) -> bool:
    from pa_agent.data.market_defaults import normalize_ashare_tv_code

    code = normalize_ashare_tv_code(symbol or "")
    return len(code) == 6 and code.isdigit()


def is_bar_still_forming(
    bar: KlineBar,
    timeframe: str,
    *,
    now_ms: int | None = None,
    symbol: str | None = None,
) -> bool:
    """True when the newest bar period has not ended (wall-clock + A-share daily session)."""
    if bar.closed:
        return False
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    tf = str(timeframe or "").strip()
    tf_lower = tf.lower()
    if _looks_like_ashare_symbol(symbol):
        # Daily/weekly/monthly A-share bars stay forming through the lunch
        # break; intraday bars only during the continuous sessions.  Sharing
        # one predicate with the data sources keeps a 11:30-13:00 snapshot
        # from being handed to the AI as a closed bar.
        from pa_agent.data.ashare_common import ashare_is_forming_bar, cn_now

        probe_tf = "1d" if (tf_lower == "1d" or tf == "1M" or tf_lower == "1w") else tf
        session_now = datetime.fromtimestamp(int(now_ms) / 1000.0, tz=cn_now().tzinfo)
        if not ashare_is_forming_bar(probe_tf, session_now):
            return False
    from pa_agent.data.datetime_ts import ts_open_to_ms

    ts_open = int(ts_open_to_ms(bar.ts_open))
    close_ms = _bar_close_ms(ts_open, tf)
    if close_ms is None:
        return True

    # Primary check: use the provided now_ms (broker or local time).
    if int(now_ms) >= close_ms:
        return False

    # Safety net for daily/weekly/monthly bars: broker server time may be stale
    # (no ticks during weekend / halt), causing now_ms to lag behind real time.
    # If local wall-clock time is more than 6 h past the close, the bar has
    # definitely closed regardless of broker time.
    if tf_lower in ("1d", "1w") or tf == "1M":
        local_ms = int(time.time() * 1000)
        # 6 h safety margin covers all known broker UTC offsets (UTC-5 to UTC+5).
        safety_ms = 6 * 3600 * 1000
        if local_ms >= close_ms + safety_ms:
            return False

    return True


def has_forming_bar_at_head(
    bars_newest_first: list[KlineBar],
    timeframe: str | None = None,
    *,
    now_ms: int | None = None,
    symbol: str | None = None,
) -> bool:
    """True when index 0 is a real forming bar (not a stale unclosed flag after halt)."""
    if not bars_newest_first:
        return False
    if not timeframe:
        return not bars_newest_first[0].closed
    return is_bar_still_forming(
        bars_newest_first[0],
        timeframe,
        now_ms=now_ms,
        symbol=symbol,
    )


def current_forming_ts(
    bars_newest_first: list[KlineBar],
    timeframe: str | None = None,
    *,
    symbol: str | None = None,
    now_ms: int | None = None,
) -> int | None:
    """Return ts_open of the newest forming bar, or None if head bar is already closed."""
    if not has_forming_bar_at_head(
        bars_newest_first, timeframe, now_ms=now_ms, symbol=symbol
    ):
        return None
    return int(bars_newest_first[0].ts_open)


def forming_bar_has_closed(
    waited_ts_open: int,
    bars_newest_first: list[KlineBar],
    timeframe: str | None = None,
    *,
    symbol: str | None = None,
    now_ms: int | None = None,
) -> bool:
    """True when the waited bar finished (new bar appeared or head is no longer forming)."""
    if not bars_newest_first:
        return False
    if not has_forming_bar_at_head(
        bars_newest_first, timeframe, now_ms=now_ms, symbol=symbol
    ):
        return True
    return int(bars_newest_first[0].ts_open) != int(waited_ts_open)
