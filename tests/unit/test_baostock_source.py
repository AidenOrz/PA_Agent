"""Baostock data source: symbol mapping, bar assembly and forming flags."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

import pytest

from pa_agent.data import baostock_source as bs_mod
from pa_agent.data.baostock_source import (
    BaostockSource,
    _query_code,
    head_bar_still_forming,
    normalize_baostock_symbol,
)
from pa_agent.data.base import DataSourceTransientError

_CN = ZoneInfo("Asia/Shanghai")


class _FakeSession:
    """Stands in for the locked Baostock session; records the last query."""

    calls: ClassVar[list[str]] = []
    rows: ClassVar[list[list[str]]] = []
    logged_out: ClassVar[bool] = False

    @classmethod
    def execute(cls, label, fn):
        cls.calls.append(label)
        return cls.rows

    @classmethod
    def logout(cls):
        cls.logged_out = True


@pytest.fixture()
def fake_session(monkeypatch):
    fake = type("Session", (_FakeSession,), {})
    fake.calls = []
    fake.rows = []
    fake.logged_out = False
    monkeypatch.setattr(bs_mod, "BaostockSession", fake)
    return fake


def test_symbol_normalization_keeps_six_digit_codes():
    assert normalize_baostock_symbol("600519") == "600519"
    assert normalize_baostock_symbol("sh600519") == "600519"
    assert normalize_baostock_symbol("sz000001") == "000001"
    assert normalize_baostock_symbol("  ") == ""


def test_query_code_prefixes_stock_and_index():
    assert _query_code("600519") == "sh.600519"
    assert _query_code("000001") == "sz.000001"
    assert _query_code("000300") == "sh.000300"
    assert _query_code("sz399006") == "sz.399006"


def test_supported_timeframes_come_from_the_registry():
    source = BaostockSource()
    assert source.supported_timeframes() == [
        "1d",
        "1w",
        "1M",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
    ]
    assert "1m" not in source.supported_timeframes()


def test_subscribe_rejects_unknown_timeframe():
    source = BaostockSource()
    with pytest.raises(ValueError, match="不支持周期"):
        source.subscribe("600519", "1m")


def test_connect_and_snapshot_require_a_subscription(fake_session):
    source = BaostockSource()
    with pytest.raises(DataSourceTransientError):
        source.latest_snapshot(10)
    source.connect()
    with pytest.raises(DataSourceTransientError):
        source.latest_snapshot(10)


def test_daily_snapshot_is_newest_first_and_flags_the_forming_head(fake_session, monkeypatch):
    # 2026-11-03 is a Monday; 14:00 CN is inside the cash session, so the
    # 2026-11-03 row is the bar still being filled.
    monkeypatch.setattr(bs_mod, "cn_now", lambda: datetime(2026, 11, 3, 14, 0, tzinfo=_CN))
    fake_session.rows = [
        [
            "2026-10-30",
            "sh.600519",
            "1500.00",
            "1510.00",
            "1490.00",
            "1505.00",
            "100",
            "150500",
            "1.2",
        ],
        [
            "2026-11-02",
            "sh.600519",
            "1506.00",
            "1520.00",
            "1500.00",
            "1515.00",
            "120",
            "181800",
            "0.66",
        ],
        [
            "2026-11-03",
            "sh.600519",
            "1516.00",
            "1530.00",
            "1510.00",
            "1522.00",
            "80",
            "121760",
            "0.46",
        ],
    ]
    source = BaostockSource()
    source.connect()
    source.subscribe("600519", "1d")
    bars = source.latest_snapshot(3)

    assert [bar.seq for bar in bars] == [1, 2, 3]
    assert bars[0].close == pytest.approx(1522.0)
    assert bars[-1].close == pytest.approx(1505.0)
    assert bars[0].closed is False
    assert all(bar.closed for bar in bars[1:])
    assert bars[0].pct_chg == pytest.approx(0.46)
    assert fake_session.calls == ["1d K线"]


def test_daily_snapshot_after_close_marks_head_closed(fake_session, monkeypatch):
    monkeypatch.setattr(bs_mod, "cn_now", lambda: datetime(2026, 11, 3, 16, 0, tzinfo=_CN))
    fake_session.rows = [
        ["2026-11-02", "sh.600519", "1", "1", "1", "10", "1", "10", "0"],
        ["2026-11-03", "sh.600519", "1", "1", "1", "11", "1", "11", "0"],
    ]
    source = BaostockSource()
    source.connect()
    source.subscribe("600519", "1d")
    bars = source.latest_snapshot(2)
    assert bars[0].closed is True


def test_snapshot_caches_within_the_ttl(fake_session, monkeypatch):
    monkeypatch.setattr(bs_mod, "cn_now", lambda: datetime(2026, 11, 3, 20, 0, tzinfo=_CN))
    fake_session.rows = [["2026-11-03", "sh.600519", "1", "1", "1", "11", "1", "11", "0"]]
    source = BaostockSource()
    source.connect()
    source.subscribe("600519", "1d")
    source.latest_snapshot(1)
    source.latest_snapshot(1)
    assert fake_session.calls == ["1d K线"]


def test_minute_rows_use_the_baostock_timestamp_format(fake_session, monkeypatch):
    monkeypatch.setattr(bs_mod, "cn_now", lambda: datetime(2026, 11, 3, 20, 0, tzinfo=_CN))
    fake_session.rows = [
        ["2026-11-03", "20261103103000000", "sh.600519", "1", "2", "1", "2", "1", "2"],
        ["2026-11-03", "20261103104500000", "sh.600519", "2", "3", "2", "3", "1", "3"],
    ]
    source = BaostockSource()
    source.connect()
    source.subscribe("600519", "15m")
    bars = source.latest_snapshot(2)
    assert len(bars) == 2
    # newest first: the later stamp is bars[0]
    assert bars[0].ts_open > bars[1].ts_open
    assert bars[0].close == pytest.approx(3.0)


def test_index_minute_bars_are_rejected(fake_session):
    source = BaostockSource()
    source.connect()
    source.subscribe("000300", "15m")
    with pytest.raises(DataSourceTransientError, match="指数"):
        source.latest_snapshot(5)


def test_empty_rows_raise_a_transient_error(fake_session, monkeypatch):
    monkeypatch.setattr(bs_mod, "cn_now", lambda: datetime(2026, 11, 3, 20, 0, tzinfo=_CN))
    fake_session.rows = []
    source = BaostockSource()
    source.connect()
    source.subscribe("600519", "1d")
    with pytest.raises(DataSourceTransientError, match="未返回"):
        source.latest_snapshot(5)


def test_disconnect_logs_out_and_clears_the_cache(fake_session):
    source = BaostockSource()
    source.connect()
    source.subscribe("600519", "1d")
    source.disconnect()
    assert fake_session.logged_out is True
    assert source.is_connected is False


def test_weekly_bar_stays_forming_through_friday(monkeypatch):
    # Weekly bars are stamped with the last trading day of the week (Monday
    # here), so "same date as today" is the wrong test for them.
    monday = int(datetime(2026, 11, 2, 9, 30, tzinfo=_CN).timestamp() * 1000)
    assert head_bar_still_forming(monday, "1w", datetime(2026, 11, 5, 10, 0, tzinfo=_CN))
    assert not head_bar_still_forming(monday, "1w", datetime(2026, 11, 7, 10, 0, tzinfo=_CN))
    # A weekly bar from a previous week is never forming.
    assert not head_bar_still_forming(monday, "1w", datetime(2026, 11, 12, 10, 0, tzinfo=_CN))


def test_monthly_bar_stays_forming_until_month_end():
    first = int(datetime(2026, 11, 2, 9, 30, tzinfo=_CN).timestamp() * 1000)
    assert head_bar_still_forming(first, "1M", datetime(2026, 11, 20, 10, 0, tzinfo=_CN))
    assert not head_bar_still_forming(first, "1M", datetime(2026, 12, 1, 10, 0, tzinfo=_CN))


def test_intraday_bar_outside_the_session_is_closed():
    opened = int(datetime(2026, 11, 3, 10, 0, tzinfo=_CN).timestamp() * 1000)
    assert head_bar_still_forming(opened, "15m", datetime(2026, 11, 3, 10, 5, tzinfo=_CN))
    assert not head_bar_still_forming(opened, "15m", datetime(2026, 11, 3, 12, 0, tzinfo=_CN))
