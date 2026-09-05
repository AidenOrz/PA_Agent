from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pa_agent.ai import decision_continuity as continuity
from pa_agent.records import trade_logger
from pa_agent.records.analysis_history import find_latest_successful_record
from pa_agent.records.schema import AnalysisRecord, RecordMeta


def _record() -> AnalysisRecord:
    return AnalysisRecord(
        meta=RecordMeta(
            timestamp_local_iso="2026-08-04T12:34:56.000",
            timestamp_local_ms=1_754_300_096_000,
            symbol="AAPL",
            timeframe="1d",
            bar_count=1,
            ai_provider={"model": "test"},
        ),
        kline_data=[
            {
                "seq": 1,
                "ts_open": 1,
                "open": 1,
                "high": 2,
                "low": 0,
                "close": 1,
                "volume": 1,
                "closed": True,
            }
        ],
        htf_text="",
        stage1_messages=[],
        stage1_response=None,
        stage1_diagnosis={"cycle_position": "test"},
        stage2_messages=[],
        stage2_response=None,
        stage2_decision={"decision": {"order_type": "no-order"}},
        strategy_files_used=[],
        experience_loaded=[],
        exception=None,
        usage_total={},
    )


def _save_trade_row(index: int) -> None:
    trade_logger._save_trade_record_impl(
        decision_inner={
            "order_direction": "long",
            "order_type": "limit",
            "entry_price": str(index),
        },
        stage2_full={},
        stage1_diagnosis=None,
        frame=None,
        meta_symbol="AAPL",
        meta_timeframe="1d",
        decision_stance="balanced",
        model_name="test",
    )


def test_concurrent_trade_writes_keep_all_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(trade_logger, "_TRADE_RECORDS_DIR", tmp_path)
    monkeypatch.setattr(continuity, "_TRADE_RECORDS_DIR", tmp_path)

    total = 24
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_save_trade_row, range(total)))

    csv_path = tmp_path / "AAPL_1d.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == total
    assert {row["entry_price"] for row in rows} == {str(i) for i in range(total)}


def test_trade_path_components_cannot_escape_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(trade_logger, "_TRADE_RECORDS_DIR", tmp_path)
    monkeypatch.setattr(continuity, "_TRADE_RECORDS_DIR", tmp_path)

    trade_logger._save_trade_record_impl(
        decision_inner={"order_type": "limit", "entry_price": "1"},
        stage2_full={},
        stage1_diagnosis=None,
        frame=None,
        meta_symbol=r"..\..\outside",
        meta_timeframe="../1d",
        decision_stance="balanced",
        model_name="test",
    )

    csv_files = list(tmp_path.glob("*.csv"))
    assert len(csv_files) == 1
    assert csv_files[0].parent.resolve() == tmp_path.resolve()
    assert ".." not in csv_files[0].name


def test_history_finds_legacy_filename_by_record_content(tmp_path: Path) -> None:
    record = _record()
    legacy_path = tmp_path / "2026-08-04_12-08-05_AAPL_1d.json"
    legacy_path.write_text(
        json.dumps(record.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = find_latest_successful_record(
        symbol="AAPL",
        timeframe="1d",
        directory=tmp_path,
    )

    assert loaded == record
