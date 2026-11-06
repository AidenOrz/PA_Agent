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
    assert ac.ensure_today_forming_daily_bar(rows, symbol="600519", now=_weekday_midday()) is False
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


def _ts(day: str, hour: int, minute: int = 0) -> int:
    d = datetime.fromisoformat(day)
    return int(d.replace(hour=hour, minute=minute, tzinfo=_CN).timestamp() * 1000)


def test_weekly_head_stays_forming_past_daily_close():
    """周三 20:00 周线仍在成形：旧逻辑走日内 session_open，15:00 后误标已收盘。"""
    # 2026-11-04 周三，2026-11-06 周五
    assert ac.ashare_head_bar_live("1w", datetime(2026, 11, 4, 20, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-02", 9, 30)) is True
    assert ac.ashare_head_bar_live("1w", datetime(2026, 11, 6, 14, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-02", 9, 30)) is True


def test_weekly_head_closes_at_friday_1500():
    assert ac.ashare_head_bar_live("1w", datetime(2026, 11, 6, 15, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-02", 9, 30)) is False
    assert ac.ashare_head_bar_live("1w", datetime(2026, 11, 7, 10, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-06", 9, 30)) is False


def test_weekly_stale_head_not_remarked_forming():
    """头行属于上一 ISO 周时即使还在周五 15:00 前也不能标 forming。"""
    # 2026-11-10 周二：头行是 11-06（上周五）→ 已收盘
    assert ac.ashare_head_bar_live("1w", datetime(2026, 11, 10, 10, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-06", 9, 30)) is False


def test_monthly_head_follows_period_end():
    """月线整个月内成形，月末 15:00 收；上月头行不得复活。"""
    assert ac.ashare_head_bar_live("1M", datetime(2026, 11, 20, 10, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-02", 9, 30)) is True
    assert ac.ashare_head_bar_live("1M", datetime(2026, 11, 30, 16, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-02", 9, 30)) is False
    assert ac.ashare_head_bar_live("1M", datetime(2026, 12, 1, 10, 0, tzinfo=_CN),
                                   head_ts_open_ms=_ts("2026-11-02", 9, 30)) is False


def test_daily_and_intraday_unchanged():
    assert ac.ashare_head_bar_live("1d", datetime(2026, 11, 4, 12, 0, tzinfo=_CN)) is True
    assert ac.ashare_head_bar_live("1d", datetime(2026, 11, 4, 20, 0, tzinfo=_CN)) is False
    assert ac.ashare_head_bar_live("15m", datetime(2026, 11, 4, 12, 0, tzinfo=_CN)) is False
