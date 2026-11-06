"""§1.3/§1.2 混乱闸门不变量：程序侧必须拦截「极端混乱却 proceed」。

历史问题：§1.3 方向曾写反（混乱反而放行），提示词修正后程序侧没有兜底——
gate_result=proceed 且模型自写 gate_trace §1.3=是 时照常进入阶段二。
该不变量必须无条件运行（生产默认关闭 coherence_checks）。
"""

from __future__ import annotations

from pa_agent.ai.decision_tree import validate_chaos_gate_invariant


def test_chaos_yes_with_proceed_is_rejected():
    stage1 = {
        "gate_result": "proceed",
        "gate_trace": [
            {"node_id": "1.2", "answer": "是", "branch": "normal_channel"},
            {"node_id": "1.3", "answer": "是", "reason": "极端混乱"},
        ],
    }
    errors = validate_chaos_gate_invariant(stage1)
    assert any("1.3" in e for e in errors)


def test_chaos_yes_with_wait_is_allowed():
    stage1 = {
        "gate_result": "wait",
        "gate_trace": [
            {"node_id": "1.2", "answer": "是"},
            {"node_id": "1.3", "answer": "是", "reason": "极端混乱"},
        ],
    }
    assert validate_chaos_gate_invariant(stage1) == []


def test_cycle_unrecognised_with_proceed_is_rejected():
    stage1 = {
        "gate_result": "proceed",
        "gate_trace": [
            {"node_id": "1.2", "answer": "否", "reason": "无法识别周期"},
            {"node_id": "1.3", "answer": "否"},
        ],
    }
    errors = validate_chaos_gate_invariant(stage1)
    assert any("1.2" in e for e in errors)


def test_normal_proceed_with_no_chaos_passes():
    stage1 = {
        "gate_result": "proceed",
        "gate_trace": [
            {"node_id": "1.2", "answer": "是"},
            {"node_id": "1.3", "answer": "否"},
        ],
    }
    assert validate_chaos_gate_invariant(stage1) == []


def test_missing_or_non_proceed_gate_short_circuits():
    assert validate_chaos_gate_invariant({}) == []
    assert validate_chaos_gate_invariant({"gate_result": "wait"}) == []
    assert validate_chaos_gate_invariant({"gate_result": "proceed"}) == []
    assert validate_chaos_gate_invariant(
        {"gate_result": "proceed", "gate_trace": "not-a-list"}
    ) == []


def test_invariant_runs_even_when_coherence_checks_disabled():
    """接线验证：coherence 关闭（生产默认）时 §1.3=是+proceed 仍被校验器拒绝。"""
    import json

    from pa_agent.ai.json_validator import JsonValidator, ValidationError
    from pa_agent.config.settings import ValidationSettings

    # 生产默认：全部一致性检查关闭
    validation = ValidationSettings(
        normalization_mode="lenient",
        stage1_coherence_checks=False,
        stage2_coherence_checks=False,
        trace_semantic_checks=False,
    )

    from tests.integration.conftest import VALID_STAGE1  # noqa: PLC0415

    payload = dict(VALID_STAGE1)
    payload["gate_trace"] = [
        {"node_id": "1.2", "answer": "是", "branch": "normal_channel"},
        {"node_id": "1.3", "answer": "是", "reason": "极端混乱"},
    ]
    validator = JsonValidator(validation=validation)
    result = validator.validate("stage1", json.dumps(payload, ensure_ascii=False))
    assert isinstance(result, ValidationError)
    assert any("1.3" in f for f in result.invalid_fields)
