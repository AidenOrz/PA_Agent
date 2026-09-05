"""TradingView outbound connectivity probe."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pandas as pd

from pa_agent.data.tradingview_connectivity import (
    _probe_once,
    check_tradingview_connectivity,
)


def _mock_tv_ok() -> tuple[MagicMock, MagicMock]:
    mock_df = pd.DataFrame(
        [
            {
                "datetime": "2024-01-03 10:01:00",
                "open": 10.0,
                "high": 10.8,
                "low": 9.9,
                "close": 10.5,
                "volume": 100.0,
            },
            {
                "datetime": "2024-01-03 10:00:00",
                "open": 9.0,
                "high": 9.8,
                "low": 8.9,
                "close": 9.5,
                "volume": 90.0,
            },
        ]
    )
    mock_interval = MagicMock()
    mock_interval.in_1_minute = object()
    return mock_interval, mock_df


def test_check_tradingview_connectivity_ok() -> None:
    mock_interval, mock_df = _mock_tv_ok()
    with (
        patch("tvDatafeed.Interval", mock_interval),
        patch("tvDatafeed.TvDatafeed") as tv_cls,
    ):
        tv_cls.return_value.get_hist.return_value = mock_df
        ok, detail = check_tradingview_connectivity(
            timeout_s=5.0, max_attempts=3, retry_delay_s=0.0
        )
    assert ok is True
    assert detail is None


def test_check_tradingview_connectivity_empty_data() -> None:
    mock_df = MagicMock()
    mock_df.empty = True
    mock_interval = MagicMock()
    mock_interval.in_1_minute = object()
    with (
        patch("tvDatafeed.Interval", mock_interval),
        patch("tvDatafeed.TvDatafeed") as tv_cls,
    ):
        tv_cls.return_value.get_hist.return_value = mock_df
        ok, detail = check_tradingview_connectivity(
            timeout_s=5.0, max_attempts=1, retry_delay_s=0.0
        )
    assert ok is False
    assert detail


def test_check_tradingview_connectivity_retries_then_succeeds() -> None:
    mock_interval, mock_df = _mock_tv_ok()
    side_effects = [RuntimeError("transient"), mock_df]
    with (
        patch("tvDatafeed.Interval", mock_interval),
        patch("tvDatafeed.TvDatafeed") as tv_cls,
        patch("pa_agent.data.tradingview_connectivity.time.sleep"),
    ):
        tv_cls.return_value.get_hist.side_effect = side_effects
        ok, detail = check_tradingview_connectivity(
            timeout_s=5.0, max_attempts=3, retry_delay_s=0.0
        )
    assert ok is True
    assert detail is None
    assert tv_cls.return_value.get_hist.call_count == 2


def test_check_tradingview_connectivity_exhausts_retries() -> None:
    mock_interval = MagicMock()
    mock_interval.in_1_minute = object()
    with (
        patch("tvDatafeed.Interval", mock_interval),
        patch("tvDatafeed.TvDatafeed") as tv_cls,
        patch("pa_agent.data.tradingview_connectivity.time.sleep"),
    ):
        tv_cls.return_value.get_hist.side_effect = RuntimeError("still down")
        ok, detail = check_tradingview_connectivity(
            timeout_s=5.0, max_attempts=3, retry_delay_s=0.0
        )
    assert ok is False
    assert detail is not None
    assert "已自动重试 3 次" in detail
    assert tv_cls.return_value.get_hist.call_count == 3


def test_probe_timeout_does_not_wait_for_stuck_worker() -> None:
    release = threading.Event()

    class _StuckSource:
        def set_exchange(self, _exchange: str) -> None:
            pass

        def subscribe(self, _symbol: str, _timeframe: str) -> None:
            pass

        def connect(self) -> None:
            pass

        def latest_snapshot(self, _n: int) -> list:
            release.wait(2.0)
            return [object()]

        def disconnect(self) -> None:
            pass

    started = time.monotonic()
    with patch("pa_agent.data.tradingview.TradingViewSource", _StuckSource):
        ok, detail, retryable = _probe_once(timeout_s=0.01)
    elapsed = time.monotonic() - started
    release.set()

    assert ok is False
    assert detail == "连接超时"
    assert retryable is True
    assert elapsed < 0.5
