"""主窗口缓存率分母的回归测试。

背景：底部 token 条曾把「轮缓存率」算成 S1+S2 的 prompt 之和作分母。
阶段二的 prompt 本身就包含阶段一的整轮对话，相加既重复计入共享部分，
又用一个必然冷启动的阶段一把数字稀释——实测同一轮 S1=0%、S2=50.3%，
合并后显示 33.5%，而计费实际发生在阶段二那一次请求上。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from pa_agent.gui import main_window as mw


class _Record:
    def __init__(self, s1=None, s2=None) -> None:
        self.stage1_response = s1
        self.stage2_response = s2


def _resp(prompt: int, cached: int) -> dict:
    return {
        "usage": {
            "prompt_tokens": prompt,
            "cached_prompt_tokens": cached,
            "completion_tokens": 100,
        }
    }


def test_last_stage_usage_prefers_stage2() -> None:
    record = _Record(_resp(60381, 0), _resp(119852, 60288))
    assert mw._last_stage_prompt_tokens(record) == 119852
    assert mw._last_stage_cached_tokens(record) == 60288


def test_last_stage_usage_falls_back_to_stage1() -> None:
    record = _Record(_resp(60381, 12000), None)
    assert mw._last_stage_prompt_tokens(record) == 60381
    assert mw._last_stage_cached_tokens(record) == 12000


def test_last_stage_usage_ignores_failed_stage_without_usage() -> None:
    """阶段二失败但阶段一成功时，仍应显示阶段一的真实数字。"""
    record = _Record(_resp(60381, 0), {"usage": {}})
    assert mw._last_stage_usage(record) == (60381, 0)


def test_last_stage_usage_handles_missing_record_fields() -> None:
    assert mw._last_stage_usage(_Record()) == (0, 0)
    assert mw._last_stage_usage(object()) == (0, 0)


def test_cached_tokens_cannot_exceed_prompt_tokens() -> None:
    """防御异常 provider 返回，避免算出 >100% 的命中率。"""
    record = _Record(None, _resp(1000, 5000))
    assert mw._last_stage_cached_tokens(record) == 1000
