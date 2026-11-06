"""Tests for stage prompt .txt file list helpers."""

from __future__ import annotations

from pa_agent.ai.prompt_assembler import (
    COMMON_SYSTEM_STAGE1_TXT_FILES,
    COMMON_SYSTEM_STAGE2_TXT_FILES,
    STAGE1_TASK_PROMPT_TXT_FILES,
    STAGE2_BASE_PROMPT_TXT_FILES,
    STAGE2_FULL_STRATEGY_PROMPT_TXT_FILES,
    stage1_prompt_txt_files,
    stage2_prompt_txt_files,
    stage2_routed_txt_files,
    stage2_stable_txt_files,
    stage2_user_task_txt_files,
)


def test_stage1_txt_files() -> None:
    files = stage1_prompt_txt_files()
    assert files == [*COMMON_SYSTEM_STAGE1_TXT_FILES, *STAGE1_TASK_PROMPT_TXT_FILES]
    # Stage 1 now uses the full binary tree (same as Stage 2) for prefix caching
    assert "二元决策.txt" in files
    assert "二元决策_闸门.txt" not in files
    assert "文件13-窄通道与宽通道策略.txt" not in files


def test_stage2_routed_only_bullish() -> None:
    routed = ["震荡区间交易策略.txt", "上涨通道分析识别.txt"]
    files = stage2_user_task_txt_files(routed, direction="bullish")
    assert "上涨通道分析识别.txt" in files
    assert "下跌通道分析识别.txt" not in files
    assert "下跌通道交易策略.txt" not in files
    assert "文件17-止损和止盈与仓位管理.txt" in files
    for name in STAGE2_FULL_STRATEGY_PROMPT_TXT_FILES:
        if name.startswith("下跌") or name.startswith("极速下跌"):
            assert name not in files


def test_stage2_full_library_flag() -> None:
    routed = ["震荡区间交易策略.txt"]
    files = stage2_user_task_txt_files(
        routed,
        direction="bullish",
        load_full_strategy_library=True,
    )
    for name in STAGE2_FULL_STRATEGY_PROMPT_TXT_FILES:
        assert name in files


def test_stage2_txt_files_order() -> None:
    routed = ["震荡区间交易策略.txt", "震荡区间分析识别.txt"]
    files = stage2_prompt_txt_files(routed, direction="neutral")
    expected_user = stage2_user_task_txt_files(routed, direction="neutral")
    assert files == [*COMMON_SYSTEM_STAGE2_TXT_FILES, *expected_user]
    assert files[:2] == list(COMMON_SYSTEM_STAGE2_TXT_FILES)
    # Base files form the stable head of the user turn (KV prefix cache);
    # routed files follow in canonical library order, not router order.
    assert files[2:6] == list(STAGE2_BASE_PROMPT_TXT_FILES)
    assert files[6:] == ["震荡区间分析识别.txt", "震荡区间交易策略.txt"]
    assert routed[0] in files


def test_stage2_stable_and_routed_split() -> None:
    """Routed files must be separable: the router re-decides them every cycle."""
    routed = ["震荡区间交易策略.txt", "上涨通道分析识别.txt"]
    stable = stage2_stable_txt_files()
    assert stable == list(STAGE2_BASE_PROMPT_TXT_FILES)

    extra = stage2_routed_txt_files(routed, direction="bullish", stable=stable)
    assert extra == ["上涨通道分析识别.txt", "震荡区间交易策略.txt"]
    assert not set(extra) & set(stable)

    full_stable = stage2_stable_txt_files(load_full_strategy_library=True)
    assert set(STAGE2_FULL_STRATEGY_PROMPT_TXT_FILES) <= set(full_stable)
    # With the full library nothing is left over: the head no longer depends
    # on which subset the router happened to pick.
    assert stage2_routed_txt_files(routed, direction="bullish", stable=full_stable) == []
