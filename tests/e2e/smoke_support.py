"""Shared wiring for the end-to-end smoke tests.

Every smoke test used to build ``AppContext()`` by hand and then touch
``window._ctx.settings.general``, which is ``None`` on a bare AppContext: the
test died with AttributeError.  Even with settings patched in, the submit path
short-circuited on "数据源未连接" and the pipeline never ran, so the assertion
failed for an unrelated reason.  One helper keeps the wiring in a single place.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pa_agent.ai.router import route_strategy_files
from pa_agent.app_context import AppContext
from pa_agent.config.settings import Settings
from pa_agent.data.base import DataSource, KlineBar
from tests.fixtures.validators import schema_test_validator

TEST_API_KEY = "sk-e2e-smoke-key-000000"

#: Matches ``Settings().general.last_symbol`` so the submit path does not
#: treat the window as "user switched symbol" and restart a refresh instead.
DEFAULT_SYMBOL = "XAUUSDm"
DEFAULT_TIMEFRAME = "15m"


class SmokeDataSource(DataSource):
    """Connected, offline data source returning a fixed newest-first snapshot."""

    def __init__(
        self,
        bars: list[KlineBar] | None = None,
        *,
        symbol: str = DEFAULT_SYMBOL,
        timeframe: str = DEFAULT_TIMEFRAME,
    ) -> None:
        self._bars: list[KlineBar] = list(bars or [])
        self._symbol = symbol
        self._timeframe = timeframe
        self._connected = True

    def set_bars(self, bars: list[KlineBar]) -> None:
        self._bars = list(bars)

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def list_symbols(self) -> list[str]:
        return [self._symbol] if self._symbol else []

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "1h", "4h", "1d"]

    def subscribe(self, symbol: str, timeframe: str) -> None:
        self._symbol = symbol
        self._timeframe = timeframe

    def unsubscribe(self) -> None:
        self._symbol = ""
        self._timeframe = ""

    def latest_snapshot(self, n: int) -> list[KlineBar]:
        return list(self._bars[: max(0, int(n))])


def make_trend_bars(
    n: int = 40,
    *,
    step: float = 2.0,
    with_forming: bool = True,
) -> list[KlineBar]:
    """Newest-first bullish trend bars (index 0 = newest, seq=1).

    ``make_newest_first_bars`` produces a perfectly flat series, so the
    program direction judge reads "neutral" and the continuity guard turns any
    directional plan into 不下单.  A trending series is what a "happy path"
    market actually looks like.
    """
    from pa_agent.data.base import KlineBar as _Bar

    bars: list[_Bar] = []
    start = 2 if with_forming else 1
    total = n + (1 if with_forming else 0)
    # Two-decimal prices: the program infers one tick from the snapshot decimals,
    # and integer-only prices would infer tick=1.0 and snap entry/stop to whole
    # numbers, silently destroying the risk/reward geometry under test.
    base = 2000.0
    for idx in range(total):
        # index 0 is the newest (highest) price; older bars sit lower.
        level = (total - 1 - idx) * step
        seq = idx + 1
        bars.append(
            _Bar(
                seq=seq,
                ts_open=1_700_000_000.0 - idx * 900.0,
                open=round(base + level + 0.37, 2),
                high=round(base + level + 6.83, 2),
                low=round(base + level - 2.11, 2),
                close=round(base + level + 4.29, 2),
                volume=100.0,
                closed=not (with_forming and idx == 0),
            )
        )
    return bars


def make_smoke_ctx(data_source: object | None = None) -> AppContext:
    """Build an AppContext that the submit path will actually accept."""
    ctx = AppContext()
    ctx.settings = Settings()
    ctx.settings.provider.api_key = TEST_API_KEY
    ctx.settings.general.analysis_bar_count = 5
    ctx.settings.general.alert_on_order_opportunity = False
    ctx.settings.general.last_symbol = DEFAULT_SYMBOL
    ctx.settings.general.last_timeframe = DEFAULT_TIMEFRAME
    ctx.data_source = data_source if data_source is not None else SmokeDataSource()
    ctx.router = route_strategy_files
    ctx.validator = schema_test_validator()
    ctx.pending_writer = MagicMock()
    ctx.exp_reader = MagicMock()
    ctx.exp_reader.read_top5.return_value = []
    ctx.exp_reader.read_for_stage2.return_value = []
    return ctx
