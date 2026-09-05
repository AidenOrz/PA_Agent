from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pa_agent.ai import decision_continuity as continuity
from pa_agent.config import paths
from pa_agent.orchestrator.free_chat import FreeChatSession
from pa_agent.records import pending_writer as pending_module
from pa_agent.records import trade_logger
from pa_agent.records.pending_writer import PendingWriter
from pa_agent.records.schema import AnalysisRecord, FollowupTurn, RecordMeta


def _record(
    *,
    timestamp_ms: int = 1_700_000_000_123,
    symbol: str = "XAUUSD",
    timeframe: str = "1h",
) -> AnalysisRecord:
    return AnalysisRecord(
        meta=RecordMeta(
            timestamp_local_iso="2023-11-14T22:13:20.123",
            timestamp_local_ms=timestamp_ms,
            symbol=symbol,
            timeframe=timeframe,
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


def test_pending_filename_uses_minutes_milliseconds_and_safe_components(tmp_path: Path) -> None:
    timestamp_ms = 1_700_000_000_123
    record = _record(
        timestamp_ms=timestamp_ms,
        symbol="../escape\\nested",
        timeframe="1/5",
    )

    path = PendingWriter(pending_dir=tmp_path).save_full(record)
    expected_ts = pending_module._ms_to_local_datetime(timestamp_ms).strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    assert path.parent.resolve() == tmp_path.resolve()
    assert path.name.startswith(f"{expected_ts}-123_")
    assert ".." not in path.name
    assert "/" not in path.name
    assert "\\" not in path.name


def test_pending_records_in_same_second_do_not_overwrite(tmp_path: Path) -> None:
    writer = PendingWriter(pending_dir=tmp_path)
    first = writer.save_full(_record(timestamp_ms=1_700_000_000_100))
    second = writer.save_full(_record(timestamp_ms=1_700_000_000_900))

    assert first != second
    assert first.is_file()
    assert second.is_file()
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_pending_json_replace_failure_keeps_formal_file_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = PendingWriter(pending_dir=tmp_path)
    path = writer.save_full(_record())
    original_text = path.read_text(encoding="utf-8")

    def fail_replace(*_args: object) -> None:
        raise OSError("simulated replace interruption")

    monkeypatch.setattr(pending_module.os, "replace", fail_replace)
    writer._write_json(path, {"replacement": True})

    assert path.read_text(encoding="utf-8") == original_text
    assert json.loads(original_text)["meta"]["symbol"] == "XAUUSD"
    assert not list(tmp_path.glob(f".{path.name}.*.tmp"))


def test_followup_record_id_cannot_escape_pending_directory(tmp_path: Path) -> None:
    turn = FollowupTurn(
        turn=1,
        ts_ms=1,
        user="question",
        ai_content="answer",
        ai_reasoning=None,
        usage={},
    )

    PendingWriter(pending_dir=tmp_path).append_followup(r"..\..\outside", turn)
    files = list(tmp_path.glob("*.followups.jsonl"))

    assert len(files) == 1
    assert files[0].parent.resolve() == tmp_path.resolve()
    assert ".." not in files[0].name


def test_trade_records_path_is_project_anchored() -> None:
    expected = paths.PROJECT_ROOT / "trade_records"

    assert expected == paths.TRADE_RECORDS_DIR
    assert expected == trade_logger._TRADE_RECORDS_DIR
    assert expected == continuity._TRADE_RECORDS_DIR


def test_trade_csv_replace_failure_keeps_formal_file_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv_path = tmp_path / "trades.csv"
    trade_logger._atomic_write_csv(csv_path, [{"record_time": "old"}])
    original_text = csv_path.read_text(encoding="utf-8-sig")

    def fail_replace(*_args: object) -> None:
        raise OSError("simulated replace interruption")

    monkeypatch.setattr(trade_logger.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace interruption"):
        trade_logger._atomic_write_csv(csv_path, [{"record_time": "new"}])

    assert csv_path.read_text(encoding="utf-8-sig") == original_text
    assert not list(tmp_path.glob(f".{csv_path.name}.*.tmp"))


def test_free_chat_record_id_matches_pending_filename(tmp_path: Path) -> None:
    record = _record(symbol="../XAUUSD", timeframe="1/5")
    record_path = PendingWriter(pending_dir=tmp_path).save_full(record)

    session = FreeChatSession(
        base_record=record,
        client=MagicMock(),
        assembler=MagicMock(),
        pending_writer=MagicMock(),
        ledger=MagicMock(),
    )

    assert session.record_id == record_path.stem
