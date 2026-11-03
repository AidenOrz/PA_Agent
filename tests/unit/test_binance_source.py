"""Binance data source: symbol/interval mapping, forming flag, REST errors."""

from __future__ import annotations

import json

import pytest

from pa_agent.data import binance_source as bn
from pa_agent.data.base import DataSourceTransientError
from pa_agent.data.binance_source import (
    BinanceSource,
    head_bar_still_forming,
    is_binance_pair,
    normalize_binance_symbol,
)


def _kline(ts_ms: int, close: float = 100.0) -> list:
    return [
        ts_ms,
        "100.0",
        "110.0",
        "90.0",
        str(close),
        "12.5",
        ts_ms + 60_000,
        "1250.0",
        "10",
        "0",
        "0",
        "0",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BTCUSDT", "BTCUSDT"),
        ("btc/usdt", "BTCUSDT"),
        ("BTC-USDT", "BTCUSDT"),
        ("BINANCE:btcusdt", "BTCUSDT"),
        ("  ethusdt  ", "ETHUSDT"),
        ("BTCUSDT.P", "BTCUSDT"),
    ],
)
def test_symbol_forms_are_normalized(raw, expected):
    assert normalize_binance_symbol(raw) == expected


def test_pair_detection_accepts_quoted_pairs_only():
    assert is_binance_pair("BTCUSDT")
    assert is_binance_pair("ETHBTC")
    assert is_binance_pair("BTCEUR")
    assert not is_binance_pair("XAUUSDm")
    assert not is_binance_pair("600519")


def test_head_bar_forming_uses_the_interval_table(monkeypatch):
    opened = 1_700_000_000_000
    assert head_bar_still_forming(opened, "1h", opened + 3_599_999)
    assert not head_bar_still_forming(opened, "1h", opened + 3_600_000)
    assert head_bar_still_forming(opened, "1m", opened + 59_999)
    # A month is calendar-based, not a fixed 30 days.
    from datetime import UTC, datetime

    month_open = int(datetime(2026, 11, 1, tzinfo=UTC).timestamp() * 1000)
    assert head_bar_still_forming(month_open, "1M", month_open + 20 * 86_400_000)
    assert not head_bar_still_forming(
        month_open, "1M", int(datetime(2026, 12, 1, tzinfo=UTC).timestamp() * 1000)
    )


def test_supported_timeframes_come_from_the_registry():
    source = BinanceSource()
    assert source.supported_timeframes() == [
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
        "1d",
        "1w",
        "1M",
    ]


def test_subscribe_rejects_non_pair_symbols():
    source = BinanceSource()
    with pytest.raises(ValueError, match="交易对"):
        source.subscribe("XAUUSDm", "15m")
    with pytest.raises(ValueError, match="周期"):
        source.subscribe("BTCUSDT", "3m")


def test_snapshot_marks_only_the_head_bar_forming(monkeypatch):
    now_ms = 1_700_000_000_000 + 120_000
    monkeypatch.setattr(bn.time, "time", lambda: now_ms / 1000.0)
    rows = [
        _kline(now_ms - 120_000, close=99.0),
        _kline(now_ms - 60_000, close=101.0),
        _kline(now_ms - 60_000 + 60_000, close=102.0),
    ]
    source = BinanceSource()
    monkeypatch.setattr(source, "_fetch_klines", lambda *a, **k: rows)
    source.connect()
    source.subscribe("btc/usdt", "1m")
    bars = source.latest_snapshot(3)
    assert [bar.seq for bar in bars] == [1, 2, 3]
    assert bars[0].close == pytest.approx(102.0)
    assert bars[-1].close == pytest.approx(99.0)
    assert bars[0].closed is False
    assert all(bar.closed for bar in bars[1:])


def test_snapshot_requires_connection_and_subscription():
    source = BinanceSource()
    with pytest.raises(DataSourceTransientError):
        source.latest_snapshot(5)
    source.connect()
    with pytest.raises(DataSourceTransientError):
        source.latest_snapshot(5)


def test_snapshot_rejects_oversized_requests(monkeypatch):
    source = BinanceSource()
    source.connect()
    source.subscribe("BTCUSDT", "15m")
    with pytest.raises(DataSourceTransientError, match="最多"):
        source.latest_snapshot(bn.BINANCE_MAX_BARS + 1)


def test_http_error_becomes_a_transient_error(monkeypatch):
    import urllib.error

    def _boom(*args, **kwargs):
        raise urllib.error.HTTPError("http://x", 451, "Unavailable For Legal Reasons", {}, None)

    monkeypatch.setattr(bn.urllib.request.OpenerDirector, "open", _boom, raising=False)
    source = BinanceSource()
    source.connect()
    source.subscribe("BTCUSDT", "15m")
    with pytest.raises(DataSourceTransientError, match="451"):
        source.latest_snapshot(5)


def test_network_error_message_mentions_the_proxy(monkeypatch):
    import urllib.error

    def _boom(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(bn.urllib.request.OpenerDirector, "open", _boom, raising=False)
    source = BinanceSource()
    source.connect()
    source.subscribe("BTCUSDT", "15m")
    with pytest.raises(DataSourceTransientError, match="代理"):
        source.latest_snapshot(5)


def test_non_json_payload_is_rejected(monkeypatch):
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"<html>blocked</html>"

    monkeypatch.setattr(
        bn.urllib.request.OpenerDirector, "open", lambda *a, **k: _FakeResponse(), raising=False
    )
    source = BinanceSource()
    source.connect()
    source.subscribe("BTCUSDT", "15m")
    with pytest.raises(DataSourceTransientError):
        source.latest_snapshot(5)


def test_request_json_passes_the_proxy_from_settings(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps([_kline(1_700_000_000_000)]).encode()

    def _fake_open(self, request, timeout=None):
        captured["proxies"] = self.handlers
        captured["url"] = request.full_url
        return _FakeResponse()

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    monkeypatch.setattr(bn.urllib.request.OpenerDirector, "open", _fake_open, raising=False)
    payload = bn._request_json("https://api.binance.com/api/v3/klines?x=1", timeout_s=1.0)
    assert payload
    assert "klines" in captured["url"]
    proxy_handlers = [h for h in captured["proxies"] if type(h).__name__ == "ProxyHandler"]
    assert proxy_handlers and "127.0.0.1:7897" in str(proxy_handlers[0].proxies)


def test_canonical_symbol_matches_the_subscription():
    source = BinanceSource()
    source.connect()
    source.subscribe("btc/usdt", "15m")
    assert source.symbol == "BTCUSDT"
    assert source.canonical_symbol("btc-usdt") == source.symbol
