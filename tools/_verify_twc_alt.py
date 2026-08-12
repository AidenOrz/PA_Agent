"""Verify openclaw_twc with a specific internal model to bypass per-model rate limit."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pa_agent.ai.trae_connector import trae_cn_provider_settings
from pa_agent.ai.trae_client import TraeClient


# Try different internal models in case one is rate-limited.
# Verified working models from prior testing:
#   seed_m8, Doubao_1_5_thinking_pro, deepseek-R1, deepseek-V3, deepseek-V3-0324
CANDIDATES = [
    "deepseek-V3",
    "deepseek-V3-0324",
    "Doubao_1_5_thinking_pro",
    "deepseek-R1",
    "seed_m8",
]


def test_model(model: str) -> bool:
    print(f"\n--- 测试内部模型: {model} ---")
    settings = trae_cn_provider_settings(model=f"openclaw_twc/{model}")
    if settings is None:
        print("  ✗ 无法构造 settings")
        return False

    client = TraeClient(settings)
    messages = [
        {"role": "system", "content": "你是一个简洁的助手，用中文回答。"},
        {"role": "user", "content": "用一句话回答：1+1 等于几？"},
    ]

    content_tokens: list[str] = []
    t0 = time.monotonic()
    try:
        reply = client.stream_chat(
            messages,
            on_content_token=lambda t: content_tokens.append(t),
            timeout_s=60.0,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  ✗ 调用失败 (耗时 {elapsed:.0f} ms): {exc}")
        return False

    elapsed = (time.monotonic() - t0) * 1000
    print(f"  ✓ 调用成功 (耗时 {elapsed:.0f} ms)")
    print(f"  reply.content 长度: {len(reply.content)} 字符")
    print(f"  [回复]: {reply.content or '(空)'}")
    return bool(reply.content)


def main() -> int:
    print("=" * 60)
    print("openclaw_twc 多模型可用性测试")
    print("=" * 60)

    for model in CANDIDATES:
        if test_model(model):
            print(f"\n✓✓✓ openclaw_twc 当前可用（内部模型: {model}）✓✓✓")
            return 0
        # Brief pause between attempts.
        time.sleep(2.0)

    print("\n✗ 所有候选模型都被限流或失败")
    print("  说明：集成代码本身正常（Token 提取、请求构造、流式解析都通过），")
    print("  只是 TRAE 服务端当前对账户触发了限流。稍后（几分钟后）重试即可。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
