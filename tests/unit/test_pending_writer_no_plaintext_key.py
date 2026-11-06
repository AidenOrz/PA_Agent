"""Tests covering PR6.1: PendingWriter never writes plaintext API key to disk.

Validates: Requirements PR6.1

Constructs AnalysisRecord instances that embed the plaintext API key in:
  - meta.ai_provider dict
  - a message string in stage1_messages

Then verifies that save_full() and save_partial() produce files that:
  - do NOT contain the plaintext key
  - DO contain the mask_secret() form of the key

append_followup() writes the user question and model answer verbatim, so it
takes the same masking path as save_full()/save_partial().
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pa_agent.records.pending_writer import PendingWriter
from pa_agent.records.schema import AnalysisRecord, FollowupTurn, RecordMeta
from pa_agent.util.mask_secret import clear_disk_secrets, mask_secret

# A realistic-looking API key long enough that mask_secret produces a meaningful
# masked form (all but last 4 chars become '*').
API_KEY = "sk-plaintext123456789abcdef"


@pytest.fixture(autouse=True)
def _isolated_disk_secret_registry():
    """The disk-secret registry is process-global; keep tests hermetic."""
    clear_disk_secrets()
    yield
    clear_disk_secrets()


def _make_record_with_key(api_key: str) -> AnalysisRecord:
    """Build an AnalysisRecord that embeds *api_key* in multiple places."""
    meta = RecordMeta(
        timestamp_local_iso="2026-05-18T14:00:00+08:00",
        timestamp_local_ms=1_700_000_000_000,
        symbol="XAUUSD",
        timeframe="1h",
        bar_count=200,
        # api_key embedded directly in the ai_provider dict
        ai_provider={"model": "deepseek", "api_key": api_key},
    )
    return AnalysisRecord(
        meta=meta,
        kline_data=[],
        htf_text="some htf context",
        # api_key embedded in a message content string
        stage1_messages=[{"role": "user", "content": f"Authorization: Bearer {api_key}"}],
        stage1_response=None,
        stage1_diagnosis=None,
        stage2_messages=[],
        stage2_response=None,
        stage2_decision=None,
        strategy_files_used=[],
        experience_loaded=[],
        exception=None,
        usage_total={"prompt_tokens": 0, "completion_tokens": 0},
    )


# ---------------------------------------------------------------------------
# save_full — no plaintext key in written file
# ---------------------------------------------------------------------------


class TestSaveFullNoPlaIntextKey:
    def test_plaintext_key_absent_from_file(self, tmp_path: Path) -> None:
        """save_full must not write the plaintext API key to disk."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_full(record)
        content = path.read_text(encoding="utf-8")

        assert API_KEY not in content, f"Plaintext API key found in {path.name}"

    def test_masked_key_present_in_file(self, tmp_path: Path) -> None:
        """save_full must replace the plaintext key with its masked form."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_full(record)
        content = path.read_text(encoding="utf-8")
        expected_mask = mask_secret(API_KEY)

        assert (
            expected_mask in content
        ), f"Expected masked key '{expected_mask}' not found in {path.name}"

    def test_key_sanitized_in_ai_provider_dict(self, tmp_path: Path) -> None:
        """The api_key field inside meta.ai_provider must be masked."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_full(record)
        data = json.loads(path.read_text(encoding="utf-8"))

        provider = data["meta"]["ai_provider"]
        assert provider["api_key"] == mask_secret(API_KEY)
        assert API_KEY not in provider["api_key"]

    def test_key_sanitized_in_stage1_messages(self, tmp_path: Path) -> None:
        """The API key embedded in stage1_messages content must be masked."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_full(record)
        data = json.loads(path.read_text(encoding="utf-8"))

        message_content = data["stage1_messages"][0]["content"]
        assert API_KEY not in message_content
        assert mask_secret(API_KEY) in message_content


# ---------------------------------------------------------------------------
# save_partial — no plaintext key in written file
# ---------------------------------------------------------------------------


class TestSavePartialNoPlaIntextKey:
    def test_plaintext_key_absent_from_file(self, tmp_path: Path) -> None:
        """save_partial must not write the plaintext API key to disk."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_partial(record, reason="test")
        content = path.read_text(encoding="utf-8")

        assert API_KEY not in content, f"Plaintext API key found in {path.name}"

    def test_masked_key_present_in_file(self, tmp_path: Path) -> None:
        """save_partial must replace the plaintext key with its masked form."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_partial(record, reason="test")
        content = path.read_text(encoding="utf-8")
        expected_mask = mask_secret(API_KEY)

        assert (
            expected_mask in content
        ), f"Expected masked key '{expected_mask}' not found in {path.name}"

    def test_partial_reason_preserved(self, tmp_path: Path) -> None:
        """save_partial must still write the _partial_reason field."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_partial(record, reason="test")
        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["_partial_reason"] == "test"

    def test_key_sanitized_in_ai_provider_dict(self, tmp_path: Path) -> None:
        """The api_key field inside meta.ai_provider must be masked in partial saves."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_partial(record, reason="test")
        data = json.loads(path.read_text(encoding="utf-8"))

        provider = data["meta"]["ai_provider"]
        assert provider["api_key"] == mask_secret(API_KEY)
        assert API_KEY not in provider["api_key"]

    def test_key_sanitized_in_stage1_messages(self, tmp_path: Path) -> None:
        """The API key embedded in stage1_messages content must be masked in partial saves."""
        record = _make_record_with_key(API_KEY)
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)

        path = writer.save_partial(record, reason="test")
        data = json.loads(path.read_text(encoding="utf-8"))

        message_content = data["stage1_messages"][0]["content"]
        assert API_KEY not in message_content
        assert mask_secret(API_KEY) in message_content


# ---------------------------------------------------------------------------
# Sanity check: mask_secret produces a meaningful masked form for our key
# ---------------------------------------------------------------------------


def test_mask_secret_produces_meaningful_mask() -> None:
    """Verify the test key is long enough for mask_secret to produce a real mask."""
    masked = mask_secret(API_KEY)
    # Should end with last 4 chars of the key
    assert masked.endswith(API_KEY[-4:])
    # Should have stars for all but the last 4 chars
    assert masked == "*" * (len(API_KEY) - 4) + API_KEY[-4:]
    # The masked form must differ from the plaintext
    assert masked != API_KEY


# ---------------------------------------------------------------------------
# append_followup — same no-plaintext guarantee
# ---------------------------------------------------------------------------


def _make_turn(*, user: str) -> FollowupTurn:
    return FollowupTurn(
        turn=1,
        ts_ms=1_700_000_000_000,
        user=user,
        ai_content="好的",
        ai_reasoning=None,
        usage={"prompt_tokens": 0, "completion_tokens": 0},
    )


class TestAppendFollowupNoPlaintextKey:
    def test_plaintext_key_absent_from_sidecar(self, tmp_path: Path) -> None:
        """A key pasted into the chat box must not land in the JSONL sidecar."""
        writer = PendingWriter(pending_dir=tmp_path, api_key=API_KEY)
        writer.append_followup(
            "2026-05-18_14-00-13_XAUUSD_1h",
            _make_turn(user=f"这是我跟你说过的 key：{API_KEY}"),
        )
        sidecar = tmp_path / "2026-05-18_14-00-13_XAUUSD_1h.followups.jsonl"
        content = sidecar.read_text(encoding="utf-8")
        assert API_KEY not in content
        assert mask_secret(API_KEY) in content

    def test_key_rotation_is_followed(self, tmp_path: Path) -> None:
        """set_api_key must re-target masking after the user edits the key."""
        writer = PendingWriter(pending_dir=tmp_path, api_key="old-key-0000000000")
        writer.set_api_key(API_KEY)
        writer.append_followup("rec", _make_turn(user=f"new key {API_KEY}"))
        content = (tmp_path / "rec.followups.jsonl").read_text(encoding="utf-8")
        assert API_KEY not in content
        assert mask_secret(API_KEY) in content
