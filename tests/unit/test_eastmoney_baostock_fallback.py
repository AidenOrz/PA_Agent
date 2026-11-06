"""East Money 的 Baostock 兜底：成交量必须是「手」而非 Baostock 原始「股」。

历史 bug（P0）：``fetch_daily_history_baostock`` / ``fetch_minute_history_baostock``
原样返回 Baostock volume（股），而独立 ``BaostockSource`` 做了 ÷100。东财日线
默认 qfq 走 Baostock 兜底、分钟线超滚动窗口也切 Baostock → 同一张图的成交量
单位随路径在 手/股 之间翻转（差 100 倍），送入 LLM 的放量判断全部失真。
"""

from __future__ import annotations

import sys
import types
from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

import pytest

from pa_agent.data import eastmoney_baostock as ebm

_CN = ZoneInfo("Asia/Shanghai")


class _FakeRS:
    error_code = "0"
    error_msg = ""

    def __init__(self, rows: list[list[str]]) -> None:
        self._rows = rows
        self._i = 0

    def next(self) -> bool:
        self._i += 1
        return self._i <= len(self._rows)

    def get_row_data(self) -> list[str]:
        return self._rows[self._i - 1]


class _Capture:
    """Records the last query so tests can assert code/frequency wiring."""

    frequency: ClassVar[str] = ""
    fields: ClassVar[str] = ""
    rows: ClassVar[list[list[str]]] = []


@pytest.fixture()
def fake_baostock(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    capture = type("Capture", (_Capture,), {})
    capture.frequency = ""
    capture.fields = ""
    capture.rows = []

    def fake_query(code, fields, start_date, end_date, frequency, adjustflag):
        capture.frequency = frequency
        capture.fields = fields
        return _FakeRS(capture.rows)

    mod = types.ModuleType("baostock")
    mod.query_history_k_data_plus = fake_query
    monkeypatch.setitem(sys.modules, "baostock", mod)
    # Bypass the locked session (login/logout); hand the query straight through.
    monkeypatch.setattr(ebm._BaostockSession, "execute", classmethod(lambda cls, label, fn: fn()))
    monkeypatch.setattr(ebm, "_cn_now", lambda: datetime(2026, 11, 3, 20, 0, tzinfo=_CN))
    return capture


def test_daily_fallback_volume_is_lots_not_shares(fake_baostock) -> None:
    """8_269_122 股 = 82_691.22 手，与东财口径一致（见 test_baostock_source 同类断言）。"""
    fake_baostock.rows = [
        ["2026-11-02", "sz002475", "10", "11", "9.5", "10.5", "8269122"],
    ]
    rows = ebm.fetch_daily_history_baostock("002475", 5)
    assert rows, "daily fallback returned no rows"
    assert rows[-1]["volume"] == pytest.approx(82691.22)


def test_minute_fallback_volume_is_lots_not_shares(fake_baostock) -> None:
    fake_baostock.rows = [
        [
            "2026-11-02",
            "20261102103000000",
            "sz002475",
            "10",
            "11",
            "9.5",
            "10.5",
            "82691",
        ],
    ]
    rows = ebm.fetch_minute_history_baostock("002475", "1h", 5)
    assert rows, "minute fallback returned no rows"
    assert rows[-1]["volume"] == pytest.approx(826.91)


def test_fallback_volume_helper_rejects_nan_and_garbage() -> None:
    """`float('nan') or 0.0` 不拦 NaN：换算 helper 必须自带 NaN 防御。"""
    assert ebm._shares_to_lots(float("nan")) == 0.0
    assert ebm._shares_to_lots(None) == 0.0  # type: ignore[arg-type]
    assert ebm._shares_to_lots(-5) == 0.0
    assert ebm._shares_to_lots(100.0) == 1.0
