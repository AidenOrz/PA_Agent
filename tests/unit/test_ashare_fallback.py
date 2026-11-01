"""A 股免费替补源（ashare_fallback）与东财降级接线测试。

覆盖：
- _tencent_code / _zzshare_code 的代码映射（沪/深/指数）。
- fallback_* 链式降级的短路与跳过语义。
- eastmoney_client 四个接入点（日线/分钟/盘口/现价）在东财失败或返回空时改走替补源。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pa_agent.data import ashare_fallback as fb
from pa_agent.data import eastmoney_client as em


# --------------------------------------------------------------------------- #
# 代码映射
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("600519", "sh600519"),
        ("000001", "sz000001"),
        ("sh600519", "sh600519"),
        ("sz000001", "sz000001"),
        ("510300", "sh510300"),
        ("900901", "sh900901"),
        ("000300", "sh000300"),
        ("12345", None),
        ("", None),
    ],
)
def test_tencent_code_mapping(symbol: str, expected: str | None) -> None:
    assert fb._tencent_code(symbol) == expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("600519", "600519.SH"),
        ("000001", "000001.SZ"),
        ("600519.SH", "600519.SH"),
        ("sz000001", "000001.SZ"),
        ("000905", "000905.SH"),
        ("12345", None),
    ],
)
def test_zzshare_code_mapping(symbol: str, expected: str | None) -> None:
    assert fb._zzshare_code(symbol) == expected


# --------------------------------------------------------------------------- #
# 链式降级
# --------------------------------------------------------------------------- #
def test_fallback_spot_quote_skips_failing_source(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(symbol: str):
        raise RuntimeError("tencent down")

    monkeypatch.setattr(fb, "tencent_spot_quote", boom)
    monkeypatch.setattr(fb, "zzshare_spot_quote", lambda s: {"code": s, "name": "X", "price": 1.0})
    assert fb.fallback_spot_quote("600519") == {"code": "600519", "name": "X", "price": 1.0}


def test_fallback_spot_quote_returns_none_when_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fb, "tencent_spot_quote", lambda s: None)
    monkeypatch.setattr(fb, "zzshare_spot_quote", lambda s: None)
    monkeypatch.setattr(fb, "sina_spot_quote", lambda s: None)
    assert fb.fallback_spot_quote("600519") is None


def test_fallback_daily_falls_through_to_zzshare(monkeypatch: pytest.MonkeyPatch) -> None:
    bar = {"time": datetime(2026, 10, 23), "open": 1.0, "close": 1.0, "high": 1.0, "low": 1.0}
    monkeypatch.setattr(fb, "tencent_daily", lambda *a, **k: [])
    monkeypatch.setattr(fb, "zzshare_daily", lambda *a, **k: [bar])
    rows = fb.fallback_daily("600519", start_date="2026-10-01", end_date="2026-10-31")
    assert rows == [bar]


def test_fallback_minute_returns_empty_when_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fb, "tencent_minute", lambda *a, **k: [])
    monkeypatch.setattr(fb, "zzshare_minute", lambda *a, **k: [])
    assert fb.fallback_minute("600519", period="5", start_date="x", end_date="y") == []


# --------------------------------------------------------------------------- #
# eastmoney_client 接线：日线
# --------------------------------------------------------------------------- #
def _bar(day: int) -> dict:
    return {"time": datetime(2026, 10, day), "open": 1.0, "close": 1.0, "high": 1.0, "low": 1.0}


def test_fetch_stock_daily_uses_fallback_on_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(params):
        raise em.EastMoneyTransientError("down")

    monkeypatch.setattr(em, "_fetch_kline", boom)
    monkeypatch.setattr(fb, "fallback_daily", lambda *a, **k: [_bar(23)])
    rows = em.fetch_stock_daily("600519", start_date="2026-10-01", end_date="2026-10-31")
    assert [r["time"].day for r in rows] == [23]


def test_fetch_stock_daily_reraises_when_fallback_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(params):
        raise em.EastMoneyTransientError("down")

    monkeypatch.setattr(em, "_fetch_kline", boom)
    monkeypatch.setattr(fb, "fallback_daily", lambda *a, **k: [])
    with pytest.raises(em.EastMoneyTransientError):
        em.fetch_stock_daily("600519", start_date="2026-10-01", end_date="2026-10-31")


def test_fetch_stock_daily_uses_fallback_on_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(em, "_fetch_kline", lambda params: [])
    monkeypatch.setattr(fb, "fallback_daily", lambda *a, **k: [_bar(23)])
    rows = em.fetch_stock_daily("600519", start_date="2026-10-01", end_date="2026-10-31")
    assert len(rows) == 1


def test_fetch_stock_daily_prefers_primary_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(em, "_fetch_kline", lambda params: [_bar(22)])
    monkeypatch.setattr(fb, "fallback_daily", lambda *a, **k: [_bar(23)])
    rows = em.fetch_stock_daily("600519", start_date="2026-10-01", end_date="2026-10-31")
    assert [r["time"].day for r in rows] == [22]


# --------------------------------------------------------------------------- #
# eastmoney_client 接线：分钟线
# --------------------------------------------------------------------------- #
def _minute_bar(hour: int) -> dict:
    return {
        "time": datetime(2026, 10, 23, hour, 0),
        "open": 1.0,
        "close": 1.0,
        "high": 1.0,
        "low": 1.0,
    }


def test_fetch_stock_minute_uses_fallback_on_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(params):
        raise em.EastMoneyTransientError("down")

    monkeypatch.setattr(em, "_fetch_kline", boom)
    monkeypatch.setattr(fb, "fallback_minute", lambda *a, **k: [_minute_bar(10)])
    rows = em.fetch_stock_minute(
        "600519", period="5", start_date="2026-10-23 09:30:00", end_date="2026-10-23 15:00:00"
    )
    assert rows[0]["time"].hour == 10


def test_fetch_stock_minute_uses_fallback_when_window_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(em, "_fetch_kline", lambda params: [_minute_bar(8)])
    monkeypatch.setattr(fb, "fallback_minute", lambda *a, **k: [_minute_bar(11)])
    rows = em.fetch_stock_minute(
        "600519", period="5", start_date="2026-10-23 09:30:00", end_date="2026-10-23 15:00:00"
    )
    assert rows[0]["time"].hour == 11


def test_fetch_stock_minute_keeps_in_window_primary_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(em, "_fetch_kline", lambda params: [_minute_bar(10), _minute_bar(8)])
    monkeypatch.setattr(fb, "fallback_minute", lambda *a, **k: [_minute_bar(11)])
    rows = em.fetch_stock_minute(
        "600519", period="5", start_date="2026-10-23 09:30:00", end_date="2026-10-23 15:00:00"
    )
    assert [r["time"].hour for r in rows] == [10]


# --------------------------------------------------------------------------- #
# eastmoney_client 接线：盘口与现价
# --------------------------------------------------------------------------- #
def test_fetch_stock_order_book_uses_fallback_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(em, "fetch_stock_ten_depth_payload", lambda s: {})
    monkeypatch.setattr(em, "fetch_stock_quote_payload", lambda s: {})
    sentinel = object()
    monkeypatch.setattr(fb, "fallback_order_book", lambda s: sentinel)
    assert em.fetch_stock_order_book("600519") is sentinel


def test_fetch_stock_order_book_returns_none_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(em, "fetch_stock_ten_depth_payload", lambda s: {})
    monkeypatch.setattr(em, "fetch_stock_quote_payload", lambda s: {})
    monkeypatch.setattr(fb, "fallback_order_book", lambda s: None)
    assert em.fetch_stock_order_book("600519") is None


def test_fetch_stock_quote_uses_fallback_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(em, "fetch_stock_quote_payload", lambda s: {})
    monkeypatch.setattr(
        fb, "fallback_spot_quote", lambda s: {"code": s, "name": "贵州茅台", "price": 1500.0}
    )
    assert em.fetch_stock_quote("600519")["price"] == 1500.0


def test_fetch_stock_quote_returns_none_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(em, "fetch_stock_quote_payload", lambda s: {})
    monkeypatch.setattr(fb, "fallback_spot_quote", lambda s: None)
    assert em.fetch_stock_quote("600519") is None
