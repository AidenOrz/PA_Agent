"""Unit tests for AkShare data source helpers (no network)."""

from __future__ import annotations

from pa_agent.data.akshare_source import (
    _akshare_adjust,
    is_index_symbol,
    normalize_ashare_symbol,
)


def test_normalize_ashare_symbol_stock():
    assert normalize_ashare_symbol("600519") == "600519"
    assert normalize_ashare_symbol("sh600519") == "600519"


def test_normalize_ashare_symbol_index():
    assert normalize_ashare_symbol("sh000300") == "sh000300"
    assert normalize_ashare_symbol("000300") == "000300"


def test_is_index_symbol():
    assert is_index_symbol("000300") is True
    assert is_index_symbol("600519") is False
    assert is_index_symbol("000001") is False


def _hour_ts(day: str, hour: int) -> int:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    cn = ZoneInfo("Asia/Shanghai")
    d = datetime.fromisoformat(day)
    return int(d.replace(hour=hour, minute=0, tzinfo=cn).timestamp() * 1000)


def test_resample_60m_to_4h():
    """A股每天恰好 4 根 1h → 4h 桶以交易日为锚，一天一个桶。"""
    from pa_agent.data.ashare_common import resample_rows_to_4h as _shared

    rows = [
        {
            "ts_open": _hour_ts(day, hour),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1.0,
        }
        for day in ("2026-11-02", "2026-11-03")
        for hour in (10, 11, 14, 15)
    ]
    out = _shared(rows)
    assert len(out) == 2
    assert out[0]["open"] == 10.0
    assert out[0]["close"] == rows[3]["close"]
    assert out[0]["volume"] == 4.0


def test_resample_4h_buckets_stay_inside_one_trading_day():
    """盘中尾取 n*4+8 根后重采样：桶不得把第 k 日下午拼到第 k+1 日开盘上。

    历史 bug：按位置每 4 根切桶无交易日锚点，盘中（当日只有 1~3 根）尾部
    切片起点落在某天中间，所有历史桶的收盘价属于下一天。
    """
    from pa_agent.data.ashare_common import resample_rows_to_4h

    days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
    rows = []
    price = 10.0
    for day in days:
        for hour in (10, 11, 14, 15):  # 4 根 1h（10:30/11:30/14:00/15:00 简化为整点）
            rows.append(
                {
                    "ts_open": _hour_ts(day, hour),
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price + 0.5,
                    "volume": 1.0,
                }
            )
            price += 0.5

    # 模拟盘中尾取（最后一天只到 11:00，尾切片落在 11-06 中间）
    intraday_rows = rows[:-2]
    out = resample_rows_to_4h(intraday_rows)

    # 桶数 = 完整 4 天 + 当天半截桶
    assert len(out) == 5
    # 第 k 个桶 = 第 k 日：ts_open 是当日首根，close 是当日最后一根
    # （而不是第 k+1 日首根的 close）
    for i, bucket in enumerate(out[:4]):
        assert bucket["ts_open"] == rows[i * 4]["ts_open"]
        assert bucket["close"] == rows[i * 4 + 3]["close"]
    # 半截桶：11-06 只剩 10:00/11:00 两根
    assert out[4]["ts_open"] == rows[16]["ts_open"]
    assert out[4]["close"] == intraday_rows[-1]["close"]


def test_akshare_adjust_follows_shared_setting(monkeypatch):
    monkeypatch.setattr("pa_agent.data.akshare_source.get_kline_adjust", lambda: "hfq")
    assert _akshare_adjust() == "hfq"

    monkeypatch.setattr("pa_agent.data.akshare_source.get_kline_adjust", lambda: "none")
    assert _akshare_adjust() == ""
