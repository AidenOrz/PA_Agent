"""§14 prohibition-scan gate: clause-aware reason parsing."""
from __future__ import annotations

from pa_agent.ai.section14 import (
    section14_reason_denies_violation,
    section14_violated,
)


def test_plain_denial_counts_as_clean() -> None:
    assert section14_reason_denies_violation("未触犯任何禁止项")
    assert section14_reason_denies_violation("无违规")
    assert section14_reason_denies_violation("不存在触犯")


def test_plain_violation_is_not_a_denial() -> None:
    assert not section14_reason_denies_violation("触犯了追高禁止")
    assert not section14_reason_denies_violation("本次交易违反§14.2 重仓规则")


def test_denial_in_one_clause_does_not_cover_violation_in_another() -> None:
    """The old substring test returned "clean" here and let the order through."""
    reason = "未触发§14.1，但触发了追高禁止"
    assert not section14_reason_denies_violation(reason)
    assert section14_violated([{"node_id": "14", "answer": "是", "reason": reason}])


def test_scan_summary_with_negated_items_is_clean() -> None:
    reason = "扫描§14：未触犯任何禁止项。①追高 ②报复性交易 均未触发"
    assert section14_reason_denies_violation(reason)


def test_ambiguous_reason_is_treated_as_violation() -> None:
    """Fail safe: a safety gate must not wave through text it cannot parse."""
    assert not section14_reason_denies_violation("")
    assert not section14_reason_denies_violation("已检查完成")


def test_colon_verdict_is_read() -> None:
    assert section14_reason_denies_violation("触犯判定：无")
    assert not section14_reason_denies_violation("触犯判定：是")


def test_violated_requires_answer_yes() -> None:
    assert not section14_violated([{"node_id": "14", "answer": "否", "reason": "触犯追高"}])
    assert section14_violated([{"node_id": "14.1", "answer": "是", "reason": "触犯追高"}])
    assert not section14_violated([])
    assert not section14_violated(None)


def test_violated_ignores_non_dict_items() -> None:
    assert not section14_violated(["junk", None, 3])