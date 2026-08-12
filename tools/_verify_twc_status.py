"""Quick verification: is openclaw_twc currently usable?

Checks:
1. TRAE Work CN installation detected?
2. Token extractable? Expired?
3. Live API call succeeds?
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure pa_agent is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pa_agent.ai.trae_connector import (
    detect_trae_cn,
    is_openclaw_twc_model,
    resolve_trae_cn_api_model,
    trae_cn_provider_settings,
    _extract_trae_cn_token,
    _is_jwt_expired,
    _TRAE_CN_DATA_DIR,
    _TRAE_DEFAULT_INTERNAL_MODEL,
)


def main() -> int:
    print("=" * 60)
    print("openclaw_twc 可用性检查")
    print("=" * 60)

    # 1. 检测安装
    print("\n[1] TRAE Work CN 安装检测")
    if not detect_trae_cn():
        print("  ✗ 未检测到 TRAE Work CN")
        return 1
    print(f"  ✓ 已安装 (data_dir={_TRAE_CN_DATA_DIR})")

    # 2. Token 提取
    print("\n[2] JWT Token 提取")
    token = _extract_trae_cn_token()
    if not token:
        print("  ✗ 无法提取 Token（storage.json 解密失败且日志无 JWT）")
        print("  解决：启动 TRAE Work CN 并登录，或在设置中重新保存")
        return 1
    print(f"  ✓ Token 已提取 (长度={len(token)})")
    print(f"  前 40 字符: {token[:40]}...")

    # 3. Token 是否过期
    print("\n[3] Token 过期检查")
    if _is_jwt_expired(token):
        print("  ✗ Token 已过期")
        print("  解决：在 TRAE Work CN 中重新登录，然后重新保存设置")
        return 1
    print("  ✓ Token 有效")

    # 4. 构造 settings
    print("\n[4] 构造 AIProviderSettings")
    settings = trae_cn_provider_settings(model="openclaw_twc")
    if settings is None:
        print("  ✗ 无法构造 settings")
        return 1
    print(f"  ✓ model      = {settings.model}")
    print(f"  ✓ base_url   = {settings.base_url}")
    print(f"  ✓ api_key    = (len={len(settings.api_key or '')})")
    print(f"  ✓ 内部模型    = {resolve_trae_cn_api_model(settings.model)}")

    # 5. 实际调用 API
    print("\n[5] 实际调用 TRAE API（发送一句话测试）")
    from pa_agent.ai.trae_client import TraeClient

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
            timeout_s=60.0,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  ✗ 调用失败 (耗时 {elapsed:.0f} ms): {exc}")
        return 1

    elapsed = (time.monotonic() - t0) * 1000
    print(f"  ✓ 调用成功 (耗时 {elapsed:.0f} ms)")
    print(f"  content tokens: {len(content_tokens)} 次")
    print(f"  reasoning tokens: {len(reasoning_tokens)} 次")
    print(f"  reply.content 长度: {len(reply.content)} 字符")
    if reply.usage:
        u = reply.usage
        print(
            f"  usage: prompt={u.prompt_tokens} completion={u.completion_tokens} "
            f"total={u.total_tokens}"
        )
    print(f"\n[模型回复]: {reply.content or '(空)'}")

    if reply.content:
        print("\n✓✓✓ openclaw_twc 当前可用 ✓✓✓")
        return 0
    print("\n✗ 模型未返回 content")
    return 1


if __name__ == "__main__":
    sys.exit(main())
