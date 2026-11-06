"""Tests for validation retry policy and feedback."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pa_agent.ai.json_validator import ValidationError
from pa_agent.ai.retry_feedback import build_retry_feedback
from pa_agent.ai.retry_policy import detect_cheat, should_retry
from pa_agent.ai.stage2_normalizer import ensure_stage2_predictions
from pa_agent.gui.stage2_payload import prepare_stage2_for_ui
from pa_agent.orchestrator.validation_retry import (
    ValidationRetryError,
    validate_with_retry,
)


@dataclass
class _FakeErr:
    category: str
    message: str
    missing_fields: list[str]
    invalid_fields: list[str]
    parse_position: str | None = None
    raw_text: str = ""


class _Settings:
    retry_enabled = True
    retry_max = 2
    retry_max_semantic = 1
    retry_stage2 = True


def test_should_retry_format_errors():
    assert should_retry("b", [], ["gate_trace"], attempt=0, settings=_Settings())
    assert not should_retry("c", ["metrics:bad"], [], attempt=0, settings=_Settings())


def test_detect_cheat_immutable_direction():
    before = {"direction": "bullish", "cycle_position": "spike", "gate_result": "proceed"}
    after = {"direction": "bearish", "cycle_position": "spike", "gate_result": "proceed"}
    flags = detect_cheat("stage1", before, after)
    assert any("direction" in f for f in flags)


def test_parse_previous_for_cheat_survives_markdown_fences():
    """带 ```json 围栏的上一轮回复必须仍可解析：原样 json.loads 会静默关闭篡改检测。

    历史 fail-open：fenced 文本 -> parse_previous_for_cheat -> None ->
    detect_cheat 返回 []，模型在重试时反转 direction/gate_result 不会被拦截。
    """
    from pa_agent.ai.retry_feedback import parse_previous_for_cheat

    fenced = (
        "```json\n"
        '{"direction": "bullish", "cycle_position": "spike", "gate_result": "proceed"}\n'
        "```"
    )
    obj = parse_previous_for_cheat(fenced)
    assert obj is not None
    assert obj["direction"] == "bullish"

    before = {"direction": "bullish", "gate_result": "proceed"}
    after = {"direction": "bearish", "gate_result": "proceed"}
    flags = detect_cheat("stage1", before, after)
    assert any("direction" in f for f in flags)


def test_detect_cheat_no_false_positive_when_program_normalizes_direction():
    """Raw AI direction may differ from post-normalize value; compare normalized copies."""
    from pa_agent.ai.json_validator import JsonValidator
    from pa_agent.data.base import IndicatorBundle, KlineBar, KlineFrame

    bars = tuple(
        KlineBar(
            seq=i + 1,
            ts_open=float(1_000_000 - (i + 1) * 60_000),
            open=2000.0,
            high=2010.0,
            low=1990.0,
            close=2005.0,
            volume=1.0,
            closed=True,
        )
        for i in range(25)
    )
    frame = KlineFrame(
        symbol="TEST",
        timeframe="1h",
        bars=bars,
        snapshot_ts_local_ms=1,
        indicators=IndicatorBundle(
            ema20=tuple([2000.0] * 25),
            atr14=tuple([10.0] * 25),
        ),
    )
    validator = JsonValidator()
    raw = {
        "direction": "bearish",
        "cycle_position": "broad_channel",
        "gate_result": "proceed",
        "gate_trace": [],
    }
    before_norm = validator.normalize_parsed("stage1", raw, kline_frame=frame)
    after_norm = validator.normalize_parsed("stage1", dict(raw), kline_frame=frame)
    flags = detect_cheat("stage1", before_norm, after_norm)
    assert not flags


def test_build_retry_feedback_contains_stage():
    err = _FakeErr("b", "missing", ["next_bar_prediction"], [], None, "{}")
    text = build_retry_feedback(err, stage="stage2", attempt=1, max_attempts=2)
    assert "next_bar_prediction" in text
    assert "阶段二" in text


def test_ensure_stage2_predictions_for_old_record():
    s2 = {
        "decision": {"order_type": "不下单", "reasoning": "等待"},
        "diagnosis_summary": {"cycle_position": "broad_channel", "direction": "neutral"},
        "decision_trace": [],
        "terminal": {"node_id": "9.0", "outcome": "wait", "label": "x"},
    }
    assert ensure_stage2_predictions(s2) is True
    assert isinstance(s2.get("next_bar_prediction"), dict)
    assert isinstance(s2.get("next_cycle_prediction"), dict)


def test_prepare_stage2_for_ui_merges_predictions():
    s2 = {
        "decision": {"order_type": "不下单"},
        "diagnosis_summary": {"cycle_position": "broad_channel", "direction": "neutral"},
    }
    payload = prepare_stage2_for_ui(s2)
    assert "next_bar_prediction" in payload
    assert "next_cycle_prediction" in payload


def test_validation_retry_api_exception_keeps_feedback_state():
    class _Validator:
        def validate(self, stage, content, **kwargs):
            return ValidationError(
                category="b",
                stage=stage,
                raw_text=content,
                missing_fields=["gate_trace"],
            )

    class _Reply:
        content = "{}"
        reasoning_content = ""
        raw = {"content": "{}"}

    with pytest.raises(ValidationRetryError) as caught:
        validate_with_retry(
            stage="stage1",
            messages=[{"role": "user", "content": "prompt"}],
            reply=_Reply(),
            validator=_Validator(),
            validation_settings=_Settings(),
            validate_kwargs={},
            call_api=lambda _messages: (_ for _ in ()).throw(RuntimeError("retry API failed")),
        )

    error = caught.value
    assert error.stage == "stage1"
    assert error.attempts == 2
    assert error.reply.content == "{}"
    assert error.messages[-1]["role"] == "user"
    assert isinstance(error.cause, RuntimeError)


# ── retry_stage2 开关 / feedback_mentioned 接线 ────────────────────────────────


class _CountingValidator:
    """按顺序返回预设结果，并记录调用次数。"""

    def __init__(self, results: list[object]) -> None:
        self._results = list(results)
        self.calls = 0

    def validate(self, stage: str, content: str, **kwargs: object) -> object:
        self.calls += 1
        index = min(self.calls - 1, len(self._results) - 1)
        return self._results[index]

    def normalize_parsed(self, stage: str, obj: dict, **kwargs: object) -> dict:
        return obj


class _Reply:
    def __init__(self, content: str) -> None:
        self.content = content
        self.reasoning_content = ""
        self.raw = {"content": content}


def _settings(**overrides: object) -> _Settings:
    settings = _Settings()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def test_retry_stage2_disabled_never_calls_api():
    """retry_stage2=False 必须真正禁止阶段二重试（不能只改本地变量）。"""

    validator = _CountingValidator(
        [
            ValidationError(
                category="b",
                stage="stage2",
                raw_text="{}",
                missing_fields=["gate_trace"],
            )
        ]
    )
    calls: list[list[dict]] = []

    def _call_api(messages: list[dict]) -> object:
        calls.append(list(messages))
        return _Reply("{}")

    result = validate_with_retry(
        stage="stage2",
        messages=[{"role": "user", "content": "prompt"}],
        reply=_Reply("{}"),
        validator=validator,
        validation_settings=_settings(retry_stage2=False, retry_max=3),
        validate_kwargs={},
        call_api=_call_api,
    )

    assert calls == [], "retry_stage2=False 时不应发起重试 API 调用"
    assert result.attempts == 1
    assert isinstance(result.result, ValidationError)


def test_retry_stage1_still_retries_when_stage2_disabled():
    """关掉阶段二重试不能连坐阶段一。"""
    from pa_agent.ai.json_validator import Ok

    validator = _CountingValidator(
        [
            ValidationError(
                category="b",
                stage="stage1",
                raw_text="{}",
                missing_fields=["gate_trace"],
            ),
            Ok(obj={"direction": "bullish"}),
        ]
    )
    calls: list[list[dict]] = []

    def _call_api(messages: list[dict]) -> object:
        calls.append(list(messages))
        return _Reply('{"direction": "bullish"}')

    result = validate_with_retry(
        stage="stage1",
        messages=[{"role": "user", "content": "prompt"}],
        reply=_Reply("{}"),
        validator=validator,
        validation_settings=_settings(retry_stage2=False, retry_max=2),
        validate_kwargs={},
        call_api=_call_api,
    )

    assert len(calls) == 1
    assert result.attempts == 2
    assert isinstance(result.result, Ok)


_S1_BULLISH = '{"direction": "bullish", "cycle_position": "spike", "gate_result": "proceed"}'
_S1_BEARISH = '{"direction": "bearish", "cycle_position": "spike", "gate_result": "proceed"}'


def _run_cheat_case(invalid_fields: list[str]) -> object:
    """第一次校验失败（可重试的 c 类），重试后返回 Ok；返回结果对象。"""
    from pa_agent.ai.json_validator import Ok

    validator = _CountingValidator(
        [
            ValidationError(
                category="c",
                stage="stage1",
                raw_text=_S1_BULLISH,
                invalid_fields=invalid_fields,
            ),
            Ok(
                obj={
                    "direction": "bearish",
                    "cycle_position": "spike",
                    "gate_result": "proceed",
                }
            ),
        ]
    )
    return validate_with_retry(
        stage="stage1",
        messages=[{"role": "user", "content": "prompt"}],
        reply=_Reply(_S1_BULLISH),
        validator=validator,
        validation_settings=_settings(retry_max=2, retry_max_semantic=1),
        validate_kwargs={},
        call_api=lambda _messages: _Reply(_S1_BEARISH),
    )


def test_cheat_detection_exempts_field_requested_by_feedback():
    """反馈点名要求改 direction 时，重试后改 direction 不应判为篡改。"""
    from pa_agent.ai.json_validator import Ok

    result = _run_cheat_case(["s1:direction 与 K 线结构不符"])

    assert result.cheat_detected is False
    assert isinstance(result.result, Ok)
    assert result.attempts == 2


def test_cheat_detection_still_flags_unrequested_immutable_change():
    """反馈没点名 direction 时，重试后改 direction 仍应判为篡改。"""
    result = _run_cheat_case(["s1:gate_trace 无效"])

    assert result.cheat_detected is True
    assert isinstance(result.result, ValidationError)
    assert "direction" in (result.result.message or "")
