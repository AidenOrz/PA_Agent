"""Offline tests for the WeStock CLI data source."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pa_agent.data.base import DataSourceTransientError
from pa_agent.data.market_defaults import migrate_general_gold_defaults
from pa_agent.data.westock_source import (
    WeStockSource,
    _is_forming_bar_at,
    _rows_to_bars,
    build_westock_kline_command,
    normalize_westock_symbol,
    normalize_westock_timeframe,
)

_CN = ZoneInfo("Asia/Shanghai")


def _ts_ms(date_str: str) -> int:
    return int(datetime.fromisoformat(date_str).replace(tzinfo=_CN).timestamp() * 1000)


def _source() -> WeStockSource:
    source = WeStockSource()
    source._connected = True
    source._npx = "npx-mock"
    return source


def _completed(stdout: str, *, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["npx-mock"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_normalize_symbols_and_timeframes() -> None:
    assert normalize_westock_symbol("600519") == "sh600519"
    assert normalize_westock_symbol("000001") == "sz000001"
    assert normalize_westock_symbol("bj430047") == "bj430047"
    assert normalize_westock_symbol("hk700") == "hk00700"
    assert normalize_westock_symbol("usAAPL") == "usAAPL"
    assert normalize_westock_symbol("XAUUSD") == ""
    assert normalize_westock_timeframe("day") == "1d"
    assert normalize_westock_timeframe("month") == "1M"
    assert normalize_westock_timeframe("1M") == "1M"
    with pytest.raises(ValueError):
        normalize_westock_timeframe("15m")


def test_legacy_gold_symbol_migrates_to_westock_default() -> None:
    general = {
        "last_data_source": "westock",
        "last_symbol": "XAUUSDm",
        "last_tradingview_exchange": "OANDA",
    }
    migrate_general_gold_defaults(general)
    assert general["last_symbol"] == "000001"


def test_command_maps_period_and_adjustment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pa_agent.data.westock_source.get_kline_adjust", lambda: "hfq")
    command = build_westock_kline_command("npx", "600519", "1d", 20)
    assert command == [
        "npx",
        "-y",
        "westock-data-skillhub@1.0.5",
        "kline",
        "sh600519",
        "--period",
        "day",
        "--limit",
        "20",
        "--raw",
        "--fq",
        "hfq",
    ]

    monkeypatch.setattr("pa_agent.data.westock_source.get_kline_adjust", lambda: "none")
    command = build_westock_kline_command("npx", "sh688981", "1M", 2)
    assert "--fq" not in command
    assert command[5:7] == ["--period", "month"]
    with pytest.raises(ValueError, match="Invalid WeStock symbol"):
        build_westock_kline_command("npx", "XAUUSDm", "1d", 1)


def test_connect_checks_node_runtime_but_does_not_run_npx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = WeStockSource()
    calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        return f"{name}-mock"

    def fake_run(command, **_kwargs):
        calls.append(command)
        return _completed("v24.18.0")

    monkeypatch.setattr("pa_agent.data.westock_source.shutil.which", fake_which)
    monkeypatch.setattr("pa_agent.data.westock_source.subprocess.run", fake_run)
    source.connect()

    assert source._connected is True
    assert calls == [["node-mock", "--version"]]


def test_latest_snapshot_parses_wrapped_json_and_orders_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    source.subscribe("600519", "day")
    payload = (
        "npx info\n"
        '{"success":true,"data":{"rows":['
        '{"date":"2026-08-04","open":"10","last":"10.5",'
        '"high":"11","low":"9.5","volume":"1,200","amount":"5000",'
        '"changePercent":"5.2"},'
        '{"date":"2026-08-05","open":11,"close":12,"high":12.5,"low":10.8,'
        '"volume":1300,"amount":6000}'
        ']}}\n'
    )
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return _completed(payload)

    monkeypatch.setattr("pa_agent.data.westock_source.subprocess.run", fake_run)
    bars = source.latest_snapshot(2)

    assert [bar.close for bar in bars] == [12.0, 10.5]
    assert bars[0].seq == 1
    assert bars[1].seq == 2
    assert bars[1].volume == 1200.0
    assert bars[1].amount == 5000.0
    assert bars[1].pct_chg == 5.2
    assert calls[0][4] == "sh600519"
    assert calls[0][6] == "day"


def test_latest_snapshot_skips_rows_without_complete_ohlc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    source.subscribe("sh600519", "1d")
    payload = {
        "success": True,
        "data": [
            {"date": "2026-08-05", "open": 10, "high": 11, "low": 9},
            {"date": "2026-08-04", "open": 9, "close": 10, "high": 10.5, "low": 8.5},
        ],
    }
    monkeypatch.setattr(
        "pa_agent.data.westock_source.subprocess.run",
        lambda *_args, **_kwargs: _completed(json.dumps(payload)),
    )
    bars = source.latest_snapshot(5)
    assert len(bars) == 1
    assert bars[0].close == 10


def test_cli_failure_and_timeout_are_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    source.subscribe("sh600519", "1d")

    monkeypatch.setattr(
        "pa_agent.data.westock_source.subprocess.run",
        lambda *_args, **_kwargs: _completed(
            '{"success":false,"error":{"message":"rate limited"}}',
            returncode=1,
        ),
    )
    with pytest.raises(DataSourceTransientError, match="rate limited"):
        source.latest_snapshot(1)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("npx-mock", 30)

    monkeypatch.setattr("pa_agent.data.westock_source.subprocess.run", timeout)
    with pytest.raises(DataSourceTransientError, match="超时"):
        source.latest_snapshot(1)


def test_snapshot_cache_avoids_repeated_cli_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    source.subscribe("sh600519", "1d")
    payload = (
        '{"success":true,"data":[{"date":"2026-08-04","open":10,'
        '"last":11,"high":12,"low":9}]}'
    )
    calls = 0

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _completed(payload)

    monkeypatch.setattr("pa_agent.data.westock_source.subprocess.run", fake_run)
    assert source.latest_snapshot(1)[0].close == 11
    assert source.latest_snapshot(1)[0].close == 11
    assert calls == 1


def test_disconnect_clears_subscription() -> None:
    source = _source()
    source.subscribe("600519", "1d")
    source.disconnect()
    with pytest.raises(DataSourceTransientError, match="未连接"):
        source.latest_snapshot(1)
    assert source._symbol == ""
    assert source._timeframe == ""


def test_forming_daily_bar_during_session_and_after_close() -> None:
    # 2026-09-02 是周三
    now = datetime(2026, 9, 2, 10, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1d", _ts_ms("2026-09-02"), now) is True
    # 收盘后当日 bar 已完成
    now = datetime(2026, 9, 2, 15, 30, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1d", _ts_ms("2026-09-02"), now) is False
    # 前一交易日的 bar 永远已收盘
    now = datetime(2026, 9, 2, 10, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1d", _ts_ms("2026-09-01"), now) is False


def test_forming_weekly_bar_across_week() -> None:
    # 本周从 2026-08-31（周一）开始
    # 周三盘后：本周 bar 仍在形成
    now = datetime(2026, 9, 2, 20, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1w", _ts_ms("2026-08-31"), now) is True
    # 周五（2026-09-04）收盘后本周结束
    now = datetime(2026, 9, 4, 15, 30, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1w", _ts_ms("2026-08-31"), now) is False
    # 周五午休：本周 bar 仍在形成（午休不算收盘）
    now = datetime(2026, 9, 4, 12, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1w", _ts_ms("2026-08-31"), now) is True
    # 周末：本周已完成
    now = datetime(2026, 9, 5, 10, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1w", _ts_ms("2026-08-31"), now) is False
    # 上周（2026-08-24 起）的 bar 已结束
    now = datetime(2026, 9, 2, 10, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1w", _ts_ms("2026-08-24"), now) is False


def test_forming_monthly_quarterly_and_yearly_bars() -> None:
    now = datetime(2026, 9, 3, 20, 0, tzinfo=_CN)
    assert _is_forming_bar_at("sh600519", "1M", _ts_ms("2026-09-01"), now) is True
    assert _is_forming_bar_at("sh600519", "1M", _ts_ms("2026-08-01"), now) is False
    assert _is_forming_bar_at("sh600519", "1y", _ts_ms("2026-01-01"), now) is True
    assert _is_forming_bar_at("sh600519", "1y", _ts_ms("2025-01-01"), now) is False
    # Q3（7-9 月）未结束；Q2 的 bar 已结束
    assert _is_forming_bar_at("sh600519", "3M", _ts_ms("2026-07-01"), now) is True
    assert _is_forming_bar_at("sh600519", "3M", _ts_ms("2026-04-01"), now) is False


def test_rows_to_bars_marks_newest_weekly_bar_forming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 最新一根周线属于仍在形成的周期 → closed=False；其余 → closed=True
    forming_ts = _ts_ms("2026-08-31")

    def fake_forming(symbol: str, timeframe: str, ts_open_ms: int) -> bool:
        return timeframe == "1w" and ts_open_ms == forming_ts

    monkeypatch.setattr("pa_agent.data.westock_source._is_forming_bar", fake_forming)
    rows = [
        {"date": "2026-08-24", "open": 10, "close": 11, "high": 12, "low": 9},
        {"date": "2026-08-31", "open": 11, "close": 12, "high": 13, "low": 10},
    ]
    bars = _rows_to_bars(rows, symbol="sh600519", timeframe="1w", n=5)
    assert bars[0].closed is False
    assert bars[1].closed is True
