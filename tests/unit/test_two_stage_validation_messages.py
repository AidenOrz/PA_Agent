"""Stage 1 / Stage 2 校验提示文案的共用实现与阶段差异（行为等价回归）。"""

from __future__ import annotations

from types import SimpleNamespace

from pa_agent.ai.json_validator import ValidationError
from pa_agent.ai.provider_errors import PROVIDER_QUOTA_USER_MESSAGE
from pa_agent.orchestrator.two_stage import (
    _enrich_stage1_validation_message,
    _enrich_stage2_validation_message,
)


def _err(**overrides) -> ValidationError:
    fields = {
        "category": "c",
        "stage": "stage1",
        "raw_text": "{}",
        "missing_fields": [],
        "invalid_fields": [],
        "message": "无效字段",
    }
    fields.update(overrides)
    return ValidationError(**fields)  # type: ignore[arg-type]


def _reply(content: str = "", reasoning: str = "", completion: int = 0):
    return SimpleNamespace(
        content=content,
        reasoning_content=reasoning,
        usage=SimpleNamespace(completion_tokens=completion),
    )


def test_truncated_json_message_is_identical_for_both_stages():
    """语法错误 + 未闭合 JSON：截断提示不含阶段文案，两阶段完全一致（等价性回归）。"""
    truncated = '{"direction": "bullish", "cycle_position": "spi'
    err = _err(category="a", raw_text=truncated, message="JSON 语法错误")
    reply = _reply(content=truncated, completion=900)

    s1 = _enrich_stage1_validation_message(err, reply)
    s2 = _enrich_stage2_validation_message(err, reply)

    assert "阶段 JSON 正文约" in s1
    assert "completion_tokens≈900" in s1
    assert "思考区约 0 字" in s1
    assert s1 == s2


def test_empty_content_without_json_in_reasoning_mentions_stage_name():
    """content 为空且思考区没有 JSON：提示必须是阶段特有的文案。"""
    err = _err(category="d", raw_text="", message="未输出 JSON")
    reply = _reply(content="", reasoning="我先看看结构……", completion=300)

    s1 = _enrich_stage1_validation_message(err, reply)
    s2 = _enrich_stage2_validation_message(err, reply)

    assert "扩展思考已输出约" in s1 and "扩展思考已输出约" in s2
    assert "思考占满输出额度后被截断" in s1
    assert "网关提前结束流" in s2
    assert "思考占满输出额度后被截断" not in s2


def test_empty_content_with_reasoning_asks_for_stage_specific_json():
    """思考区里已有 JSON：提示把该阶段 JSON 写进正文。"""
    err = _err(category="d", raw_text="", message="未输出 JSON")
    reply = _reply(content="", reasoning='{"direction": "bullish"}')

    assert "阶段一 JSON" in _enrich_stage1_validation_message(err, reply)
    assert "阶段二 JSON" in _enrich_stage2_validation_message(err, reply)


def test_provider_quota_short_circuits_both_stages():
    """category=e 直接返回配额文案，两阶段一致。"""
    err = _err(category="e", raw_text="", message="")
    reply = _reply()

    assert _enrich_stage1_validation_message(err, reply) == PROVIDER_QUOTA_USER_MESSAGE
    assert _enrich_stage2_validation_message(err, reply) == PROVIDER_QUOTA_USER_MESSAGE


def test_non_empty_content_appends_field_detail():
    """普通校验失败：message + 字段明细，两阶段格式一致。"""
    err = _err(
        category="c",
        raw_text='{"direction": "bullish"}',
        invalid_fields=["direction: 非法值"],
        message="字段值不符合规则",
    )
    reply = _reply(content='{"direction": "bullish"}')

    s1 = _enrich_stage1_validation_message(err, reply)
    s2 = _enrich_stage2_validation_message(err, reply)

    assert s1.startswith("字段值不符合规则")
    assert s1 == s2
    assert "direction" in s1
