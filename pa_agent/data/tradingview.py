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
    sanitize_tv_exchange_for_symbol,
    tv_auto_probe_plan,
)
from pa_agent.data.tradingview_errors import format_tradingview_fetch_error
from pa_agent.data.tv_symbol_lookup import TvSymbolNotFoundError

logger = logging.getLogger(__name__)

# One attempt per fetch cycle. Each tvDatafeed get_hist() that times out
# blocks for up to _TV_WS_TIMEOUT_S, so retrying here multiplies the worst-case
# wait the user sees on a slow/blocked connection. The RefreshLoop already does
# its own exponential backoff + retry across ticks, so a per-call retry only
# stacks latency without adding resilience.
_TV_FETCH_RETRIES = 1
_TV_FETCH_RETRY_SLEEP_S = 0.5

# Override tvDatafeed's WebSocket timeout (upstream default: 5s, see
# tvDatafeed/main.py __ws_timeout). Healthy fetches complete in 0.4-0.6s, so a
# short bound costs nothing when the venue is right. It matters a lot when it
# is wrong: a bad pair (000001 on NASDAQ, 600519 on OANDA) gets critical_error
# and no bars, and tvDatafeed then drains ~5 socket reads before giving up, so
# one failed fetch costs about 5x this value. 3s keeps that worst case near 15s
# instead of the ~50s a 10s timeout produced.
_TV_WS_TIMEOUT_S = 3.0

# Name-mangled attribute tvDatafeed uses internally for its socket timeout.
_TV_WS_TIMEOUT_ATTR = "_TvDatafeed__ws_timeout"

# Map our timeframe strings to tvDatafeed Interval enum names
_TF_MAP: dict[str, str] = {
    "1m": "in_1_minute",
    "3m": "in_3_minute",
    "5m": "in_5_minute",
    "15m": "in_15_minute",
    "30m": "in_30_minute",
    "45m": "in_45_minute",
    "1h": "in_1_hour",
    "2h": "in_2_hour",
    "3h": "in_3_hour",
    "4h": "in_4_hour",
    "1d": "in_daily",
    "1w": "in_weekly",
    "1M": "in_monthly",
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

    def __init__(
        self,
        username: str = "",
        password: str = "",
        proxy_override: str = "",
    ) -> None:
        self._username = username
        self._password = password
        # Manual proxy override (e.g. from the settings UI); empty = auto-detect.
        self._proxy_override = (proxy_override or "").strip()
        self._tv = None  # tvDatafeed instance
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

    def set_proxy_override(self, proxy: str) -> None:
        """Set a manual proxy (e.g. ``http://127.0.0.1:7890``); empty = auto-detect.

        Must be called before :meth:`connect` — the patch is installed there.
        """
        self._proxy_override = (proxy or "").strip()

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
            except Exception:
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
        proxy = self._detect_proxy(self._proxy_override)
        if proxy is None:
            logger.info("未检测到可用代理，TradingView 将直连（可能超时）")
            return
        proxy_url, host, port, proxy_source = proxy
        proxy_auth = self._proxy_auth_tuple(proxy_url)
        # Respect NO_PROXY / ProxyOverride for auto-detected proxies only —
        # a manually configured proxy is an explicit user choice and wins.
        if proxy_source != "manual":
            no_proxy = os.environ.get("NO_PROXY", "").lower()
            if "data.tradingview.com" in no_proxy or "tradingview.com" in no_proxy:
                logger.info("tradingview.com in NO_PROXY — skip proxy patch")
                return
        self._proxy_source = proxy_source

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
            if proxy_auth is not None:
                # 需要认证的代理：websocket-client 收 (user, password) 二元组；
                # 不传就会在 407 上被拒，表现为连接静默失败。
                options.setdefault("http_proxy_auth", proxy_auth)
            return original(url, timeout=timeout, class_=class_, **options)

        tv_main.create_connection = _patched
        self._orig_create_connection = original
        self._patched_create_connection = _patched
        # 日志里不能出现明文密码：只报 host:port 与是否带认证。
        logger.info(
            "Patched tvDatafeed WebSocket to use proxy %s:%s (from %s, auth=%s)",
            host,
            port,
            self._proxy_source,
            "yes" if proxy_auth is not None else "no",
        )

    @staticmethod
    def _proxy_auth_tuple(proxy_url: str) -> tuple[str, str] | None:
        """从代理 URL 里取 ``(user, password)``；没有认证信息返回 None。

        ``http://user:pass@host:port`` 形式的代理需要把凭据单独交给
        websocket-client（``http_proxy_auth``），否则请求会静默 407。
        用户名/密码按 URL 规则先做百分号解码（密码里常有 ``@`` / ``:``）。
        """
        try:
            parsed = urllib.parse.urlparse(proxy_url or "")
        except ValueError:
            return None
        if not parsed.username:
            return None
        user = urllib.parse.unquote(parsed.username)
        password = urllib.parse.unquote(parsed.password or "")
        return user, password

    @staticmethod
    def _detect_proxy(override: str = "") -> tuple[str, str, int, str] | None:
        """Return (proxy_url, host, port, source) of the best available proxy.

        A non-empty *override* (e.g. from the settings UI) wins over every
        auto-detection method. Auto-detect order: env vars → Windows system
        proxy → common local ports.
        """
        # 0. Manual override from the settings UI (highest priority)
        raw = (override or "").strip()
        if raw:
            normalized = raw if "://" in raw else f"http://{raw}"
            parsed = urllib.parse.urlparse(normalized)
            if parsed.hostname:
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                return normalized, parsed.hostname, port, "manual"
            logger.warning("手动代理地址无效（忽略并回退自动探测）：%r", raw)

        # 1. Environment variables
        for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            raw = os.environ.get(key, "").strip()
            if raw:
                normalized = raw if "://" in raw else f"http://{raw}"
                parsed = urllib.parse.urlparse(normalized)
                if parsed.hostname:
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    # 归一化后返回：``user:pass@host:port`` 缺协议时也要带上 scheme，
                    # 否则调用方无法从中解析出代理认证信息。
                    return normalized, parsed.hostname, port, "env"

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
                        proxy_url = TradingViewSource._proxy_url_for_server(server)
                        if host and port and proxy_url:
                            return proxy_url, host, port, "registry"
        except Exception:
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
    def _proxy_url_for_server(server: str) -> str:
        """Windows ``ProxyServer`` 值 -> 带 host:port 的代理 URL（保留认证信息）。

        ``http=user:pass@host:port;https=user:pass@host:port`` 这种形式里，
        认证信息只写在条目里；重建 URL 时不能丢掉，否则需要认证的代理会 407。
        """
        text = (server or "").strip()
        if not text:
            return ""
        entry = ""
        plain = ""
        for part in text.split(";"):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                scheme, addr = part.split("=", 1)
                if scheme.strip().lower() == "https" and addr.strip():
                    entry = addr.strip()
            elif not plain:
                plain = part
        chosen = entry or plain
        if not chosen:
            return ""
        return chosen if "://" in chosen else f"http://{chosen}"

    @staticmethod
    def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception:
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
        except Exception:
            logger.debug("tvDatafeed socket close failed", exc_info=True)
        finally:
            try:
                tv.ws = None
            except Exception:
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
            symbol,
            exchange,
            interval,
            n_bars,
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
                    attempt,
                    _TV_FETCH_RETRIES,
                    symbol,
                    exchange,
                    interval,
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
                except Exception:
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
        raw_exchange = (self._exchange or "").strip().upper()
        # A venue that cannot serve this symbol (000001 on NASDAQ, 600519 on
        # OANDA) answers with critical_error and no bars, and each attempt
        # costs a full socket timeout. Downgrade such a pair to auto-probe so
        # the request is routed to a venue that actually lists the symbol.
        req_exchange = sanitize_tv_exchange_for_symbol(raw_exchange, user_symbol)
        if raw_exchange and not is_tv_exchange_auto(raw_exchange) and req_exchange != raw_exchange:
            logger.info(
                "TradingView exchange %s cannot serve %s; using auto-probe",
                raw_exchange,
                user_symbol,
            )
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
                    exchange, fetch_symbol = resolve_tv_fetch_pair(req_exchange, user_symbol)
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
                user_symbol,
                exchange or req_exchange or "自动",
                cause=exc,
            )
            logger.warning("TradingView fetch failed: %s", exc)
            raise DataSourceTransientError(msg) from exc

        if df is None or df.empty:
            msg = format_tradingview_fetch_error(
                user_symbol,
                exchange or req_exchange or "自动",
                empty_data=True,
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

                secs_left = seconds_until_bar_closes(ts_ms, self._timeframe, now_ms=None)
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
