"""A 股交易日历守卫：休市工作日不得凭空补出一根日线。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pa_agent.data import ashare_common as ac

_CN = ZoneInfo("Asia/Shanghai")


def _weekday_midday() -> datetime:
    # 2026-10-09 是周五，11:00 在交易时段内。
    return datetime(2026, 10, 9, 11, 0, tzinfo=_CN)


def _rows(prev_close: float = 10.0) -> list[dict]:
    return [
        {
            "ts_open": int(datetime(2026, 10, 8, 9, 30, tzinfo=_CN).timestamp() * 1000),
            "open": prev_close,
            "high": prev_close,
            "low": prev_close,
            "close": prev_close,
        }
    ]


def test_closed_market_does_not_synthesize_daily_bar() -> None:
    """国庆等工作日休市：不能补 open=close=昨收、volume=0 的假 K 线。"""
    rows = _rows()
    added = ac.ensure_today_forming_daily_bar(
        rows,
        symbol="600519",
        now=_weekday_midday(),
        market_open_today=False,
    )
    assert added is False
    assert len(rows) == 1


def test_open_market_still_synthesizes_daily_bar() -> None:
    rows = _rows()
    added = ac.ensure_today_forming_daily_bar(
        rows,
        symbol="600519",
        now=_weekday_midday(),
        market_open_today=True,
    )
    assert added is True
    assert len(rows) == 2


def test_unknown_calendar_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """探测拿不准（返回 None）时按「不开市」处理，宁缺毋滥。"""
    monkeypatch.setattr(ac, "ashare_market_open_today", lambda now=None: False)
    rows = _rows()
    assert (
        ac.ensure_today_forming_daily_bar(
            rows, symbol="600519", now=_weekday_midday()
        )
        is False
    )
    assert len(rows) == 1


def test_market_open_requires_weekday_and_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ac, "ashare_trading_day", lambda now=None: True)
    monkeypatch.setattr(ac, "reference_index_traded_today", lambda now=None: None)
    assert ac.ashare_market_open_today(_weekday_midday()) is False
    monkeypatch.setattr(ac, "reference_index_traded_today", lambda now=None: True)
    assert ac.ashare_market_open_today(_weekday_midday()) is True


def test_market_open_false_on_weekend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ac, "ashare_trading_day", lambda now=None: False)
    monkeypatch.setattr(ac, "reference_index_traded_today", lambda now=None: True)
    assert ac.ashare_market_open_today(_weekday_midday()) is False