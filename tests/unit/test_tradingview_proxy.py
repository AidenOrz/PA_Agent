"""Manual proxy override for TradingViewSource (settings UI field).

Covers:
- ``_detect_proxy(override)``: manual address parsing wins over auto-detection.
- ``_patch_ws_proxy``: a manual proxy is applied even when ``NO_PROXY``
  whitelists tradingview.com; auto-detected proxies still respect NO_PROXY.
- ``create_data_source("tradingview")`` forwards ``general.tradingview_proxy``.
"""
from __future__ import annotations

import sys
import types

import pytest

from pa_agent.data.tradingview import TradingViewSource


@pytest.fixture()
def fake_tvdatafeed(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Inject fake ``tvDatafeed.main`` + ``websocket`` modules and record calls."""
    saved: dict = {}

    def fake_create_connection(url, timeout=None, class_=None, **opts):
        saved["opts"] = opts
        saved["class"] = class_
        return "SOCKET"

    fake_main = types.ModuleType("tvDatafeed.main")
    fake_main.create_connection = fake_create_connection
    fake_pkg = types.ModuleType("tvDatafeed")
    fake_pkg.main = fake_main

    fake_ws = types.ModuleType("websocket")

    class WebSocket:
        pass

    fake_ws.WebSocket = WebSocket
    fake_ws.create_connection = fake_create_connection

    monkeypatch.setitem(sys.modules, "tvDatafeed", fake_pkg)
    monkeypatch.setitem(sys.modules, "tvDatafeed.main", fake_main)
    monkeypatch.setitem(sys.modules, "websocket", fake_ws)
    saved["WebSocket"] = WebSocket
    return saved


class TestDetectProxyOverride:
    def test_manual_with_scheme(self) -> None:
        result = TradingViewSource._detect_proxy("http://127.0.0.1:7890")
        assert result == ("http://127.0.0.1:7890", "127.0.0.1", 7890, "manual")

    def test_manual_without_scheme(self) -> None:
        result = TradingViewSource._detect_proxy("127.0.0.1:7897")
        assert result == ("http://127.0.0.1:7897", "127.0.0.1", 7897, "manual")

    def test_manual_https_default_port(self) -> None:
        result = TradingViewSource._detect_proxy("https://proxy.example.com")
        assert result == (
            "https://proxy.example.com",
            "proxy.example.com",
            443,
            "manual",
        )

    def test_manual_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:8118")
        result = TradingViewSource._detect_proxy("http://127.0.0.1:7890")
        assert result is not None
        assert result[3] == "manual"

    def test_blank_override_falls_through_to_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:8118")
        result = TradingViewSource._detect_proxy("   ")
        assert result is not None
        assert result[3] == "env"


class TestPatchWsProxyOverride:
    def test_manual_proxy_beats_no_proxy(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_tvdatafeed: dict,
    ) -> None:
        monkeypatch.setenv("NO_PROXY", "tradingview.com")
        src = TradingViewSource(proxy_override="127.0.0.1:7890")
        src._patch_ws_proxy()

        assert src._proxy_source == "manual"
        assert src._patched_create_connection is not None

        # The patched wrapper injects proxy options and preserves the default class.
        assert src._patched_create_connection("wss://data.tradingview.com/x") == "SOCKET"
        assert fake_tvdatafeed["opts"]["http_proxy_host"] == "127.0.0.1"
        assert fake_tvdatafeed["opts"]["http_proxy_port"] == 7890
        assert fake_tvdatafeed["class"] is fake_tvdatafeed["WebSocket"]

        src._restore_ws_proxy()
        assert src._orig_create_connection is None

    def test_auto_proxy_still_respects_no_proxy(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_tvdatafeed: dict,
    ) -> None:
        monkeypatch.setenv("NO_PROXY", "tradingview.com")
        monkeypatch.setenv("HTTPS_PROXY", "http://10.0.0.1:8118")
        src = TradingViewSource()
        src._patch_ws_proxy()

        assert src._orig_create_connection is None
        assert src._proxy_source == ""


class TestFactoryForwardsProxy:
    def test_create_data_source_passes_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pa_agent.config.settings import Settings
        from pa_agent.data.factory import create_data_source

        def fake_load_settings(path=None):
            settings = Settings()
            settings.general.tradingview_proxy = "127.0.0.1:7890"
            return settings

        # factory imports load_settings at call time from this module.
        monkeypatch.setattr(
            "pa_agent.config.settings.load_settings", fake_load_settings
        )
        source = create_data_source("tradingview")

        assert isinstance(source, TradingViewSource)
        assert source._proxy_override == "127.0.0.1:7890"
