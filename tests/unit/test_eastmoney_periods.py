"""Unit tests for East Money period parameters (no network)."""
from __future__ import annotations

from pa_agent.data import eastmoney_client


def test_index_period_uses_requested_klt(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_fetch(params: dict, **kwargs):
        captured.append(params)
        return []

    monkeypatch.setattr(eastmoney_client, "_fetch_kline", fake_fetch)

    eastmoney_client.fetch_index_daily(
        "000300", start_date="20240101", end_date="20240131", timeframe="1w"
    )
    eastmoney_client.fetch_index_daily(
        "000300", start_date="20240101", end_date="20240131", timeframe="1M"
    )

    assert [params["klt"] for params in captured] == ["102", "103"]
    assert all(params["fqt"] == "0" for params in captured)
