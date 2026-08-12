"""TRAE Work CN - 通过 TraeClient 类进行端到端集成测试。

直接调用 pa_agent.ai.trae_client.TraeClient.stream_chat,验证:
1. Token 提取
2. payload 构造 (messages + model_name)
3. SSE 流式响应解析 (output 事件 + response 字段)
4. 回调触发 (on_content_token / on_reasoning_token)
5. AIReply 返回

用法:
    python tools/_test_trae_client_e2e.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pa_agent.ai.trae_client import TraeClient
from pa_agent.ai.trae_connector import trae_cn_provider_settings


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN - TraeClient 端到端集成测试")
    print("=" * 60)

    # 1. 构造 settings (从 TRAE Work CN 本地安装自动提取)
    print("\n[1] 构造 AIProviderSettings ...")
    settings = trae_cn_provider_settings(model="openclaw_twc")
    if settings is None:
        print("  ✗ 无法构造 settings (TRAE Work CN 未安装或未登录)")
        return 1
    print(f"  ✓ model = {settings.model}")
    print(f"  ✓ base_url = {settings.base_url}")
    print(f"  ✓ api_key 长度 = {len(settings.api_key or '')}")

    # 2. 构造 TraeClient
    print("\n[2] 构造 TraeClient ...")
    client = TraeClient(settings)
    print(f"  ✓ {client.__class__.__name__}")

    # 3. 构造 OpenAI 风格 messages
    print("\n[3] 构造 messages ...")
    messages = [
        {"role": "system", "content": "你是一个简洁的助手,用中文回答。"},
        {"role": "user", "content": "用一句话回答: 1+1 等于几?"},
    ]
    print(f"  ✓ {len(messages)} 条消息")

    # 4. 流式调用
    print("\n[4] 发起 stream_chat ...")
    content_tokens: list[str] = []
    reasoning_tokens: list[str] = []

    t0 = time.monotonic()
    try:
        reply = client.stream_chat(
            messages,
            on_content_token=lambda t: content_tokens.append(t),
            on_reasoning_token=lambda t: reasoning_tokens.append(t),
            timeout_s=60.0,
        )
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        print(f"  ✗ 调用失败 (耗时 {elapsed_ms:.0f} ms): {exc}")
        return 1

    elapsed_ms = (time.monotonic() - t0) * 1000

    # 5. 结果汇总
    print(f"\n[5] 结果汇总 (耗时 {elapsed_ms:.0f} ms):")
    print(f"  content tokens: {len(content_tokens)} 次")
    print(f"  reasoning tokens: {len(reasoning_tokens)} 次")
    print(f"  reply.content 长度: {len(reply.content)} 字符")
    if reply.reasoning_content:
        print(f"  reply.reasoning_content 长度: {len(reply.reasoning_content)} 字符")
    if reply.usage:
        u = reply.usage
        print(
            f"  usage: prompt={u.prompt_tokens} completion={u.completion_tokens} "
            f"total={u.total_tokens} cached={u.cached_prompt_tokens}"
        )

    print("\n[模型回复]:")
    print(reply.content or "(空)")

    if reply.reasoning_content:
        print("\n[思考过程]:")
        print(reply.reasoning_content[:500])

    if reply.content:
        print("\n✓ TraeClient 端到端测试成功")
        return 0
    else:
        print("\n✗ 模型未返回 content")
        return 1


if __name__ == "__main__":
    sys.exit(main())
