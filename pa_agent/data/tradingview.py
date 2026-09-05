"""TradingView data source using tvdatafeed."""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.parse

from pa_agent.data.base import (
    DataSource,
    DataSourceTransientError,
    KlineBar,
    normalize_kline_bar,
)
from pa_agent.data.datetime_ts import datetime_to_ts_ms
from pa_agent.data.market_defaults import (
    is_tv_exchange_auto,
    resolve_tv_fetch_pair,
    tv_auto_probe_plan,
)
from pa_agent.data.tv_symbol_lookup import TvSymbolNotFoundError, is_tv_name_input
from pa_agent.data.tradingview_errors import format_tradingview_fetch_error

logger = logging.getLogger(__name__)

# One attempt per fetch cycle. Each tvDatafeed get_hist() that times out
# blocks for up to _TV_WS_TIMEOUT_S, so retrying here multiplies the worst-case
# wait the user sees on a slow/blocked connection. The RefreshLoop already does
# its own exponential backoff + retry across ticks, so a per-call retry only
# stacks latency without adding resilience.
_TV_FETCH_RETRIES = 1
_TV_FETCH_RETRY_SLEEP_S = 0.5

# Override tvDatafeed's hardcoded 15s WebSocket timeout. Once the socket leak
# (see _close_tv_socket) is fixed, healthy fetches complete in 1-3s, so this
# only bounds the worst case on a stalled connection.
_TV_WS_TIMEOUT_S = 10.0

# Name-mangled attribute tvDatafeed uses internally for its socket timeout.
_TV_WS_TIMEOUT_ATTR = "_TvDatafeed__ws_timeout"

# Map our timeframe strings to tvDatafeed Interval enum names
_TF_MAP: dict[str, str] = {
    "1m":  "in_1_minute",
    "3m":  "in_3_minute",
    "5m":  "in_5_minute",
    "15m": "in_15_minute",
    "30m": "in_30_minute",
    "45m": "in_45_minute",
    "1h":  "in_1_hour",
    "2h":  "in_2_hour",
    "3h":  "in_3_hour",
    "4h":  "in_4_hour",
    "1d":  "in_daily",
    "1w":  "in_weekly",
    "1M":  "in_monthly",
}

# Forex / spot gold and China A-share (tvDatafeed exchange ids)
TV_EXCHANGE_PRESETS: tuple[str, ...] = (
    "OANDA",
    "PEPPERSTONE",
    "FOREXCOM",
    "FX",
    "TVC",
    "CAPITALCOM",
    "SSE",
    "SZSE",
    "HKEX",
    "SP",
    "NYSE",
    "NASDAQ",
    "CBOT",
    "CME_MINI",
    "",
)


class TradingViewSource(DataSource):
    """Live K-line data from TradingView via tvdatafeed."""

    def __init__(self, username: str = "", password: str = "") -> None:
        self._username = username
        self._password = password
        self._tv = None          # tvDatafeed instance
        self._connected: bool = False
        self._symbol: str = ""
        self._timeframe: str = ""
        self._exchange: str = ""
        # Saved original websocket.create_connection while the proxy patch is
        # active (None when not patched).
        self._orig_create_connection = None
        # The patched wrapper we installed (None when not patched).
        self._patched_create_connection = None
        # Where the proxy came from: "env" / "registry" / "port-probe".
        self._proxy_source = ""
        # Mutex: tvDatafeed is NOT thread-safe — its get_hist() creates a
        # WebSocket and stores it on self.ws; concurrent calls clobber the
        # same socket and cause C++ segfaults.
        self._snapshot_lock = threading.Lock()
        # Callback for status updates during auto-probe: fn(symbol, exchange, label)
        self.on_probe_status = None

    @property
    def exchange(self) -> str:
        return self._exchange

    def set_exchange(self, exchange: str) -> None:
        """Set TradingView exchange id (e.g. ``BINANCE``); empty = auto-detect."""
        self._exchange = (exchange or "").strip().upper()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        try:
            self._patch_ws_proxy()
            from tvDatafeed import TvDatafeed  # type: ignore[import]
            if self._username and self._password:
                self._tv = TvDatafeed(self._username, self._password)
            else:
                self._tv = TvDatafeed()  # anonymous
            # Bound tvDatafeed's hardcoded 15s WebSocket timeout so a stalled
            # connection fails faster instead of freezing the UI.
            try:
                setattr(self._tv, _TV_WS_TIMEOUT_ATTR, _TV_WS_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                logger.debug("Could not override tvDatafeed ws timeout", exc_info=True)
            self._connected = True
            logger.info("TradingViewSource connected (anonymous=%s)", not self._username)
        except Exception as exc:
            self._connected = False
            raise DataSourceTransientError(
                f"TradingView 连接失败：{exc}（若未安装请执行 "
                "pip install git+https://github.com/rongardF/tvdatafeed.git）"
            ) from exc

    def disconnect(self) -> None:
        self._close_tv_socket()
        self._restore_ws_proxy()
        self._tv = None
        self._connected = False
        logger.info("TradingViewSource disconnected")

    # ── WebSocket proxy patch ─────────────────────────────────────────────────

    def _patch_ws_proxy(self) -> None:
        """Route tvDatafeed's WebSocket through a local proxy.

        tvDatafeed connects via ``websocket.create_connection()``, which does
        NOT honor HTTP_PROXY / HTTPS_PROXY env vars by default. On networks
        where ``data.tradingview.com`` is unreachable directly (e.g. mainland
        China), the WebSocket must go through a local proxy.

        Proxy detection order:
          1. HTTPS_PROXY / HTTP_PROXY env vars
          2. Windows system proxy (Internet Settings registry)
          3. Common local proxy ports (Clash 7890/10808, V2Ray 1080, …)

        We patch ``tvDatafeed.main.create_connection`` (the module-level name
        its ``__create_connection`` calls), not the ``websocket`` module
        attribute — tvDatafeed binds the function at import time.
        """
        if self._orig_create_connection is not None:
            return  # already patched
        proxy = self._detect_proxy()
        if proxy is None:
            logger.info("未检测到可用代理，TradingView 将直连（可能超时）")
            return
        proxy_url, host, port, proxy_source = proxy
        self._proxy_source = proxy_source
        # Respect NO_PROXY / ProxyOverride: skip patch when the target host
        # is whitelisted for direct connection.
        no_proxy = os.environ.get("NO_PROXY", "").lower()
        if "data.tradingview.com" in no_proxy or "tradingview.com" in no_proxy:
            logger.info("tradingview.com in NO_PROXY — skip proxy patch")
            return

        import tvDatafeed.main as tv_main  # type: ignore[import]

        original = tv_main.create_connection

        def _patched(url, timeout=None, class_=None, **options):
            # tvDatafeed calls create_connection() without class_ — the
            # original defaults it to websocket.WebSocket. Preserve that.
            if class_ is None:
                from websocket import WebSocket as _WebSocketDefault

                class_ = _WebSocketDefault
            options.setdefault("http_proxy_host", host)
            options.setdefault("http_proxy_port", port)
            return original(url, timeout=timeout, class_=class_, **options)

        tv_main.create_connection = _patched
        self._orig_create_connection = original
        self._patched_create_connection = _patched
        logger.info("Patched tvDatafeed WebSocket to use proxy %s (from %s)", proxy_url, self._proxy_source)

    @staticmethod
    def _detect_proxy() -> tuple[str, str, int, str] | None:
        """Return (proxy_url, host, port, source) of the best available proxy.

        Order: env vars → Windows system proxy → common local ports.
        """
        # 1. Environment variables
        for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            raw = os.environ.get(key, "").strip()
            if raw:
                parsed = urllib.parse.urlparse(raw if "://" in raw else f"http://{raw}")
                if parsed.hostname:
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    return raw, parsed.hostname, port, "env"

        # 2. Windows system proxy (registry) — GUI-launched apps inherit this
        # even when env vars are absent.
        try:
            import winreg  # Windows only

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as key:
                enable_val, _ = winreg.QueryValueEx(key, "ProxyEnable")
                if enable_val:
                    server, _ = winreg.QueryValueEx(key, "ProxyServer")
                    if server:
                        host, port = TradingViewSource._parse_proxy_server(server)
                        if host and port:
                            return f"http://{host}:{port}", host, port, "registry"
        except Exception:  # noqa: BLE001
            pass

        # 3. Common local proxy ports (Clash / V2Ray / Shadowsocks)
        for port in (7890, 10808, 1080, 10809, 7897, 8888, 8080):
            if TradingViewSource._tcp_open("127.0.0.1", port):
                return f"http://127.0.0.1:{port}", "127.0.0.1", port, "port-probe"

        return None

    @staticmethod
    def _parse_proxy_server(server: str) -> tuple[str, int] | None:
        """Parse a Windows ProxyServer value.

        Accepts ``host:port`` or ``http=host:port;https=host:port`` style.
        Prefers the https entry (WebSocket is wss://).
        """
        text = (server or "").strip()
        if not text:
            return None
        https_part = ""
        for part in text.split(";"):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                scheme, addr = part.split("=", 1)
                if scheme.strip().lower() == "https" and addr.strip():
                    https_part = addr.strip()
            elif not https_part:
                https_part = part
        if not https_part:
            return None
        parsed = urllib.parse.urlparse(
            https_part if "://" in https_part else f"http://{https_part}"
        )
        if not parsed.hostname:
            return None
        port = parsed.port or 80
        return parsed.hostname, port

    @staticmethod
    def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception:  # noqa: BLE001
            return False
        finally:
            s.close()

    def _restore_ws_proxy(self) -> None:
        if self._orig_create_connection is None:
            return
        try:
            import tvDatafeed.main as tv_main  # type: ignore[import]

            if tv_main.create_connection is self._patched_create_connection:
                # Our wrapper is still installed — safe to restore.
                tv_main.create_connection = self._orig_create_connection
                logger.info("Restored tvDatafeed WebSocket connection")
            else:
                # Someone else patched over us — don't clobber them, just
                # drop our saved references.
                logger.debug("tvDatafeed.create_connection changed by others; skip restore")
        finally:
            self._orig_create_connection = None
            self._patched_create_connection = None

    def _close_tv_socket(self) -> None:
        """Close the live tvDatafeed WebSocket, if any.

        tvDatafeed 2.x opens a brand-new socket on *every* ``get_hist()`` call
        and never closes the previous one — a leak that piles up half-open
        connections and trips TradingView's rate limiting. Closing the socket
        after each fetch fixes the leak, and closing it mid-flight is also the
        only way to abort a ``recv()`` that is blocked waiting on a stalled
        connection (e.g. when the user switches symbol/timeframe).

        Safe to call from another thread: ``socket.close()`` will raise inside
        the blocked ``recv()``, which tvDatafeed catches and turns into an
        empty result.
        """
        tv = self._tv
        if tv is None:
            return
        ws = getattr(tv, "ws", None)
        if ws is None:
            return
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            logger.debug("tvDatafeed socket close failed", exc_info=True)
        finally:
            try:
                tv.ws = None
            except Exception:  # noqa: BLE001
                pass

    # ── Discovery ─────────────────────────────────────────────────────────────

    def list_symbols(self) -> list[str]:
        return [
            "XAUUSD",
            "GOLD",
            "600519",
            "000001",
            "1810",
            "700",
            "小米集团",
            "腾讯控股",
            "EURUSD",
            "GBPUSD",
        ]

    def supported_timeframes(self) -> list[str]:
        return list(_TF_MAP.keys())

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, symbol: str, timeframe: str) -> None:
        if timeframe not in _TF_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe!r}. Use one of {list(_TF_MAP)}")
        self._timeframe = timeframe
        self._symbol = symbol.strip()
        # Abort any in-flight get_hist() blocked on a stalled connection so the
        # new symbol/timeframe takes effect immediately instead of waiting out
        # the previous request's timeout. Closing the socket raises inside the
        # worker thread's recv(); the next fetch transparently reconnects.
        self._close_tv_socket()
        logger.info(
            "TradingViewSource subscribed: %s %s exchange=%s",
            self._symbol,
            timeframe,
            self._exchange or "(auto)",
        )

    def unsubscribe(self) -> None:
        self._symbol = ""
        self._timeframe = ""
        logger.info("TradingViewSource unsubscribed")

    # ── Data fetch ────────────────────────────────────────────────────────────

    def _fetch_hist_with_retry(
        self,
        *,
        symbol: str,
        exchange: str,
        interval: object,
        n_bars: int,
    ):
        """Call tvDatafeed get_hist with retries (timeouts / empty are common)."""
        logger.debug(
            "TradingView get_hist: symbol=%s, exchange=%s, interval=%s, n_bars=%d",
            symbol, exchange, interval, n_bars,
        )
        last_exc: BaseException | None = None
        for attempt in range(1, _TV_FETCH_RETRIES + 1):
            try:
                df = self._tv.get_hist(
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval,
                    n_bars=n_bars,
                )
                if df is not None and not df.empty:
                    return df
                logger.warning(
                    "TradingView get_hist attempt %s/%s returned empty data: symbol=%s, exchange=%s, interval=%s",
                    attempt, _TV_FETCH_RETRIES, symbol, exchange, interval,
                )
                last_exc = None
            except Exception as exc:
                last_exc = exc
                logger.debug(
                    "TradingView get_hist attempt %s/%s failed: %s",
                    attempt,
                    _TV_FETCH_RETRIES,
                    exc,
                )
            finally:
                # tvDatafeed leaks the WebSocket it opens on every get_hist()
                # call. Close it here so half-open sockets don't accumulate and
                # trip TradingView rate limiting; the next call reconnects.
                self._close_tv_socket()
            if attempt < _TV_FETCH_RETRIES:
                time.sleep(_TV_FETCH_RETRY_SLEEP_S)
        if last_exc is not None:
            raise last_exc
        return None

    def _fetch_tv_auto_probe(
        self,
        *,
        symbol: str,
        plan: list[tuple[str, str]],
        interval: object,
        n_bars: int,
    ) -> tuple[object, str]:
        """Try each (exchange, symbol) in *plan* until one returns bars."""
        if not plan:
            raise DataSourceTransientError(
                f"TradingView 无法识别品种「{symbol}」；"
                "请用 A 股 6 位代码、港股代码（如 1810）、"
                "指数代码（如 SPX、NDX、VIX）、"
                "外汇/黄金代码或已支持的股票名称"
            )
        last_exc: BaseException | None = None
        tried: list[str] = []
        for exchange, code in plan:
            label = f"{exchange}:{code}"
            tried.append(label)
            # Notify GUI about current probe attempt
            if self.on_probe_status is not None:
                try:
                    self.on_probe_status(symbol, exchange, label)
                except Exception:  # noqa: BLE001
                    pass
            try:
                df = self._fetch_hist_with_retry(
                    symbol=code,
                    exchange=exchange,
                    interval=interval,
                    n_bars=n_bars,
                )
            except Exception as exc:
                last_exc = exc
                logger.info("TradingView auto probe %s failed: %s", label, exc)
                continue
            if df is not None and not df.empty:
                logger.info(
                    "TradingView auto probe picked %s (tried %s)",
                    label,
                    ", ".join(tried),
                )
                return df, exchange
        if last_exc is not None:
            raise last_exc
        raise DataSourceTransientError(
            f"TradingView 自动探测失败（{symbol}）：已尝试 {', '.join(tried)} 均无 K 线"
        )

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        """Return *n* bars newest-first; bars[0] is the forming (unclosed) bar.

        Thread-safety: serialized via ``_snapshot_lock`` because
        ``TvDatafeed.get_hist()`` is NOT thread-safe — it writes to
        ``self.ws`` on each call, and concurrent access clobbers the
        WebSocket, causing C++ segfaults.
        """
        with self._snapshot_lock:
            return self._latest_snapshot_inner(n)

    def _latest_snapshot_inner(self, n: int) -> list[KlineBar]:
        """Actual snapshot logic — caller holds ``_snapshot_lock``."""
        if self._tv is None:
            raise DataSourceTransientError("TradingView 未连接，请先选择数据来源 TradingView")
        if not self._symbol or not self._timeframe:
            raise DataSourceTransientError("TradingView 未订阅品种/周期")

        user_symbol = self._symbol
        req_exchange = self._exchange
        exchange = req_exchange or ""
        fetch_symbol = user_symbol
        auto_probe = is_tv_exchange_auto(req_exchange)
        probe_plan = tv_auto_probe_plan(user_symbol) if auto_probe else []
        try:
            from tvDatafeed import Interval  # type: ignore[import]
            interval = getattr(Interval, _TF_MAP[self._timeframe])
            if auto_probe and probe_plan:
                df, exchange = self._fetch_tv_auto_probe(
                    symbol=user_symbol,
                    plan=probe_plan,
                    interval=interval,
                    n_bars=n + 1,
                )
            else:
                try:
                    exchange, fetch_symbol = resolve_tv_fetch_pair(
                        req_exchange, user_symbol
                    )
                except TvSymbolNotFoundError as exc:
                    raise DataSourceTransientError(str(exc)) from exc
                df = self._fetch_hist_with_retry(
                    symbol=fetch_symbol,
                    exchange=exchange,
                    interval=interval,
                    n_bars=n + 1,
                )
        except DataSourceTransientError:
            raise
        except Exception as exc:
            msg = format_tradingview_fetch_error(
                user_symbol, exchange or req_exchange or "自动", cause=exc,
            )
            logger.warning("TradingView fetch failed: %s", exc)
            raise DataSourceTransientError(msg) from exc

        if df is None or df.empty:
            msg = format_tradingview_fetch_error(
                user_symbol, exchange or req_exchange or "自动", empty_data=True,
            )
            logger.debug(
                "TradingView empty data for %s exchange=%s",
                user_symbol,
                exchange or req_exchange or "(auto)",
            )
            raise DataSourceTransientError(msg)

        df = df.iloc[::-1].reset_index()

        bars: list[KlineBar] = []
        for i, row in enumerate(df.itertuples(index=False)):
            ts_ms = _row_ts_ms(row)
            bar = KlineBar(
                seq=i + 1,
                ts_open=ts_ms,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(getattr(row, "volume", 0.0)),
                closed=True,
            )
            if i == 0:
                # Determine whether the newest bar is still forming.
                # We must NOT pass bar.closed=True into is_bar_still_forming because
                # that function short-circuits on bar.closed and would always return
                # False — defeating the purpose of the check entirely.
                # Instead, use seconds_until_bar_closes which only looks at the
                # timestamp, and is robust to constant broker-time offsets.
                from pa_agent.data.bar_close_wait import seconds_until_bar_closes

                secs_left = seconds_until_bar_closes(
                    ts_ms, self._timeframe, now_ms=None
                )
                still_forming = secs_left is not None and secs_left > 0
                bar = KlineBar(
                    seq=bar.seq,
                    ts_open=bar.ts_open,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    closed=not still_forming,
                )
            bars.append(normalize_kline_bar(bar))
            if len(bars) >= n:
                break

        return bars


def _row_ts_ms(row) -> int:
    """Extract bar open time in milliseconds from a tvDatafeed DataFrame row."""
    return datetime_to_ts_ms(getattr(row, "datetime", None))
