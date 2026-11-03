"""Local proxy discovery shared by every data source that needs it.

The TradingView WebSocket and the Binance REST calls both have to leave from
machines where the upstream host is blocked, and both need the same answers:
which local proxy is available, does it want credentials, and does the user
have an explicit override in settings.  Keeping that logic inside the
TradingView source (where it started) meant a second source would have to
copy it, and the copies would drift.
"""

from __future__ import annotations

import logging
import os
import urllib.parse

logger = logging.getLogger(__name__)

#: Clash / V2Ray / Shadowsocks defaults worth probing.
COMMON_PROXY_PORTS: tuple[int, ...] = (7890, 10808, 1080, 10809, 7897, 8888, 8080)


def parse_proxy_server(server: str) -> tuple[str, int] | None:
    """Parse a Windows ``ProxyServer`` value into ``(host, port)``.

    Accepts ``host:port`` or ``http=host:port;https=host:port`` style.
    Prefers the https entry.
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
    parsed = urllib.parse.urlparse(https_part if "://" in https_part else f"http://{https_part}")
    if not parsed.hostname:
        return None
    return parsed.hostname, parsed.port or 80


def proxy_url_for_server(server: str) -> str:
    """Windows ``ProxyServer`` value to a proxy URL, credentials included.

        ``http=user:pass@host:port;https=user:pass@host:port`` keeps the
    credentials inside the entry; rebuilding the URL must not drop them or an
    authenticated proxy answers 407.
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


def proxy_auth_tuple(proxy_url: str) -> tuple[str, str] | None:
    """Return ``(user, password)`` from a proxy URL, or None when it has none.

    websocket-client needs the pair separately (``http_proxy_auth``); requests
    accepts it inside the URL.  Both callers percent-decode first, because
    passwords routinely contain ``@`` or ``:``.
    """
    try:
        parsed = urllib.parse.urlparse(proxy_url or "")
    except ValueError:
        return None
    if not parsed.username:
        return None
    return urllib.parse.unquote(parsed.username), urllib.parse.unquote(parsed.password or "")


def tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def detect_proxy(override: str = "") -> tuple[str, str, int, str] | None:
    """Return ``(proxy_url, host, port, source)`` of the best available proxy.

    A non-empty *override* (e.g. from the settings UI) wins over every
    auto-detection method.  Auto-detect order: env vars, Windows system proxy,
    common local ports.
    """
    raw = (override or "").strip()
    if raw:
        normalized = raw if "://" in raw else f"http://{raw}"
        parsed = urllib.parse.urlparse(normalized)
        if parsed.hostname:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return normalized, parsed.hostname, port, "manual"
        logger.warning("手动代理地址无效（忽略并回退自动探测）：%r", raw)

    for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        env_raw = os.environ.get(key, "").strip()
        if not env_raw:
            continue
        normalized = env_raw if "://" in env_raw else f"http://{env_raw}"
        parsed = urllib.parse.urlparse(normalized)
        if parsed.hostname:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return normalized, parsed.hostname, port, "env"

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
                    host, port = parse_proxy_server(server) or (None, None)
                    proxy_url = proxy_url_for_server(server)
                    if host and port and proxy_url:
                        return proxy_url, host, port, "registry"
    except Exception:
        pass

    for port in COMMON_PROXY_PORTS:
        if tcp_open("127.0.0.1", port):
            return f"http://127.0.0.1:{port}", "127.0.0.1", port, "port-probe"

    return None


def requests_proxies(override: str = "") -> dict[str, str] | None:
    """``requests``-style proxy mapping, or None for a direct connection."""
    found = detect_proxy(override)
    if found is None:
        return None
    proxy_url = found[0]
    return {"http": proxy_url, "https": proxy_url}
