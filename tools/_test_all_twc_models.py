"""Test all TRAE Work CN models with conservative rate-limit handling.

Strategy:
1. Wait an initial cool-down period.
2. Test models one at a time with long pauses between.
3. On rate limit, wait progressively longer before retrying.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pa_agent.ai.trae_connector import trae_cn_provider_settings
from pa_agent.ai.trae_client import TraeClient


MODELS: list[str | None] = [
    None,                           # 默认 → seed_m8
    "glm-5.2",
    "deepseek-V3",
    "deepseek-R1",
    "Doubao_1_5_thinking_pro",
    "kimi-k2.7-code",
]


def test_once(model: str | None) -> dict:
    """Single attempt to test a model."""
    label = model or "(default seed_m8)"
    route = "openclaw_twc" if model is None else f"openclaw_twc/{model}"

    settings = trae_cn_provider_settings(model=route)
    if settings is None:
        return {"label": label, "ok": False, "error": "无法构造 settings", "rate_limited": False}

    client = TraeClient(settings)
    messages = [
        {"role": "system", "content": "你是一个简洁的助手，用中文回答。"},
        {"role": "user", "content": "用一句话回答：1+1 等于几？"},
    ]

    content_tokens: list[str] = []
    reasoning_tokens: list[str] = []
    t0 = time.monotonic()

    try:
        reply = client.stream_chat(
            messages,
            on_content_token=lambda t: content_tokens.append(t),
            on_reasoning_token=lambda t: reasoning_tokens.append(t),
            timeout_s=90.0,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        err_msg = str(exc)
        return {
            "label": label,
            "ok": False,
            "error": err_msg,
            "elapsed_ms": elapsed,
            "rate_limited": "rate" in err_msg.lower() or "429" in err_msg,
        }

    elapsed = (time.monotonic() - t0) * 1000
    content = reply.content or ""
    reasoning = reply.reasoning_content or ""

    return {
        "label": label,
        "ok": bool(content),
        "content": content,
        "has_reasoning": bool(reasoning),
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        "elapsed_ms": elapsed,
        "usage": reply.usage.__dict__ if reply.usage else None,
        "rate_limited": False,
    }


def test_with_retry(model: str | None, max_attempts: int = 4) -> dict:
    """Test a model with exponential backoff on rate limit."""
    label = model or "(default seed_m8)"
    print(f"\n{'─' * 60}")
    print(f"测试模型: {label}")

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            wait = 60 * (attempt - 1)  # 60s, 120s, 180s
            print(f"  ⏳ 等待 {wait} 秒后第 {attempt} 次尝试...")
            time.sleep(wait)

        print(f"  [{attempt}/{max_attempts}] 调用中...")
        result = test_once(model)

        if result.get("ok"):
            print(f"  ✓ 成功 (耗时 {result['elapsed_ms']:.0f} ms)")
            print(f"    回复长度: {result['content_len']} 字符")
            if result["has_reasoning"]:
                print(f"    思考长度: {result['reasoning_len']} 字符")
            if result.get("usage"):
                u = result["usage"]
                print(f"    usage: prompt={u.get('prompt_tokens', 0)} completion={u.get('completion_tokens', 0)} total={u.get('total_tokens', 0)}")
            print(f"    [回复]: {result['content']}")
            if result["has_reasoning"]:
                preview = result.get("content", "")[:0]  # placeholder
            return result

        # Failed.
        err = result.get("error", "")[:200]
        if result.get("rate_limited") and attempt < max_attempts:
            print(f"  ✗ 限流，将重试: {err[:100]}")
            continue
        # Non-rate-limit error or last attempt.
        print(f"  ✗ 失败: {err}")
        return result

    return result


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN — 全模型可用性测试")
    print(f"  共 {len(MODELS)} 个模型")
    print(f"  策略: 模型间间隔 15 秒，限流时退避 60-180 秒")
    print("=" * 60)

    results: list[dict] = []
    for i, model in enumerate(MODELS, 1):
        print(f"\n========== [{i}/{len(MODELS)}] ==========")
        result = test_with_retry(model, max_attempts=4)
        results.append(result)

        # Pause between models.
        if i < len(MODELS):
            print(f"  ⏳ 模型间间隔 15 秒...")
            time.sleep(15)

    # Summary.
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    header = f"{'模型':<32} {'状态':<6} {'耗时(ms)':<10} {'回复长度':<10} {'思考':<6}"
    print(header)
    print("-" * 75)
    for r in results:
        label = r["label"]
        status = "✓" if r.get("ok") else "✗"
        elapsed = f"{r.get('elapsed_ms', 0):.0f}" if r.get("elapsed_ms") else "-"
        content_len = str(r.get("content_len", 0)) if r.get("ok") else "-"
        has_reasoning = "✓" if r.get("has_reasoning") else "-"
        print(f"{label:<32} {status:<6} {elapsed:<10} {content_len:<10} {has_reasoning:<6}")

    failed = [r for r in results if not r.get("ok")]
    if failed:
        print(f"\n失败模型 ({len(failed)} 个):")
        for r in failed:
            print(f"  • {r['label']}: {r.get('error', '未知')[:150]}")

    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"\n总计: {ok_count}/{len(results)} 个模型可用")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
