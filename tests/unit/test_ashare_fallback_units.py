"""zzshare 兜底路径：复权参数、限流熔断、成交量单位。"""

from __future__ import annotations

from typing import Any

import pytest

from pa_agent.data import ashare_fallback as fb


class _FakeApi:
    """最小 zzshare api 替身：记录 daily/adj 调用。"""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.daily_calls: list[dict[str, Any]] = []

    def daily(self, **kwargs: Any):
        self.daily_calls.append(kwargs)
        return _FakeFrame(self.rows)

    def stk_mins(self, **kwargs: Any):
        self.daily_calls.append(kwargs)
        return _FakeFrame(self.rows)


class _FakeFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, row


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("qfq", "qfq"),
        ("hfq", "hfq"),
        ("none", "none"),
        ("", "qfq"),
        (None, "qfq"),
        ("  QFQ ", "qfq"),
        ("bogus", "qfq"),
    ],
)
def test_normalize_daily_adjust(given: str | None, expected: str) -> None:
    assert fb.normalize_daily_adjust(given) == expected


def test_zzshare_daily_forwards_adjust(monkeypatch: pytest.MonkeyPatch) -> None:
    """兜底日线必须按 adjust 取复权数据，不能永远返回不复权价。"""
    api = _FakeApi(
        [
            {
                "trade_date": "20261023",
                "open": 1.0,
                "close": 1.1,
                "high": 1.2,
                "low": 0.9,
                "vol": 1200.0,
                "amount": 5000.0,
                "pct_chg": 1.5,
            }
        ]
    )
    monkeypatch.setattr(fb, "_zzshare_api", lambda: api)
    rows = fb.zzshare_daily("600519", start_date="2026-10-01", end_date="2026-10-31", adjust="hfq")
    assert api.daily_calls[0]["adj"] == "hfq"
    assert rows and rows[0]["volume"] == 1200.0


def test_zzshare_daily_volume_unit_matches_main_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """成交量单位是「手」：原先多除一次 100，量比主路径小两个数量级。"""
    api = _FakeApi(
        [
            {
                "trade_date": "20261023",
                "open": 1.0,
                "close": 1.0,
                "high": 1.0,
                "low": 1.0,
                "vol": 1000.0,
                "amount": 1.0,
            }
        ]
    )
    monkeypatch.setattr(fb, "_zzshare_api", lambda: api)
    rows = fb.zzshare_daily("600519", start_date="2026-10-01", end_date="2026-10-31")
    assert rows[0]["volume"] == 1000.0


def test_cooling_source_short_circuits_without_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """熔断期内不发请求：返回占位 429，调用方按限流处理。"""
    fb._trip_rate_limit("tencent")
    try:
        calls: list[str] = []

        class _Http:
            def get(self, url, **_kwargs):
                calls.append(url)
                raise AssertionError("should not request while cooling")

        monkeypatch.setattr(fb, "_http", lambda: _Http())
        resp = fb._get_with_rate_limit("tencent", "https://example.invalid/x")
        assert resp.status_code == 429
        assert calls == []
    finally:
        fb._tencent_cooldown_until = 0.0


def test_429_trips_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    fb._tencent_cooldown_until = 0.0
    fb._fallback_last_request.clear()

    class _Resp:
        status_code = 429
        text = ""

    class _Http:
        def get(self, url, **_kwargs):
            return _Resp()

    monkeypatch.setattr(fb, "_http", lambda: _Http())
    fb._get_with_rate_limit("tencent", "https://example.invalid/x")
    assert fb._source_cooling("tencent") is True
    fb._tencent_cooldown_until = 0.0
