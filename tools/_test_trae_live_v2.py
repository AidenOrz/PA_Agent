"""实际调用 TRAE Work CN API 测试脚本。

用法:
    python tools/_test_trae_live_v2.py

会从 storage.json 解密 JWT,然后调用 /api/agent/v3/llm_utils_chat 端点,
发送一个最简单的请求验证可用性。
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

# 让脚本能 import pa_agent 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pa_agent.ai.trae_connector import (
    _TRAE_API_CHAT_PATH,
    _TRAE_APP_ID,
    _extract_trae_cn_token,
    _get_api_host,
    _is_jwt_expired,
    _read_device_info,
    resolve_trae_cn_api_model,
)
from pa_agent.ai.trae_client import _build_trae_headers, _parse_sse_event, _extract_content_fields


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN 实际调用测试")
    print("=" * 60)

    # 1. 提取 Token
    print("\n[1] 提取 JWT Token ...")
    token = _extract_trae_cn_token()
    if not token:
        print("  ✗ 无法提取 Token")
        return 1
    print(f"  ✓ Token 提取成功 (长度 {len(token)}, 前 40 字符: {token[:40]}...)")

    # 2. 检查过期
    print("\n[2] 检查 Token 是否过期 ...")
    if _is_jwt_expired(token):
        print("  ✗ Token 已过期")
        return 1
    print("  ✓ Token 未过期")

    # 3. 读取 device 信息
    print("\n[3] 读取 device 信息 ...")
    device_info = _read_device_info()
    device_id = device_info.get("device_id", "")
    machine_id = device_info.get("machine_id", "")
    print(f"  device_id = {device_id or '(空)'}")
    print(f"  machine_id = {machine_id or '(空)'}")

    # 4. 构造请求
    print("\n[4] 构造请求 ...")
    api_host = _get_api_host()
    base_url = f"{api_host}{_TRAE_API_CHAT_PATH}"
    api_model = resolve_trae_cn_api_model("openclaw_twc")
    print(f"  base_url = {base_url}")
    print(f"  api_model = {api_model}")

    headers = _build_trae_headers(
        token=token,
        device_id=device_id or "unknown",
        machine_id=machine_id or "unknown",
    )

    payload = {
        "user_input": "用中文回答: 1+1 等于几?",
        "model_name": api_model,
        "intent_name": "chat",
        "function": "utils",
        "chat_history": [],
    }
    print(f"  payload.user_input = {payload['user_input']!r}")

    # 5. 发起调用
    print("\n[5] 发起 HTTP 调用 ...")
    try:
        import httpx
    except ImportError:
        print("  ✗ httpx 未安装,请运行: pip install httpx")
        return 1

    t0 = time.monotonic()
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    final_status = None
    final_body_snippet = ""

    try:
        with httpx.stream(
            "POST",
            base_url,
            headers=headers,
            json=payload,
            timeout=60.0,
        ) as resp:
            final_status = resp.status_code
            print(f"  HTTP 状态码: {resp.status_code}")
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                final_body_snippet = body
                print(f"  响应体: {body}")
                return 1

            print("\n[6] 流式响应事件:")
            print("-" * 60)
            sse_buffer = ""
            event_count = 0
            for raw_line in resp.iter_lines():
                if raw_line is None:
                    continue
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode("utf-8", errors="replace")

                if raw_line:
                    sse_buffer += raw_line + "\n"
                    continue

                if not sse_buffer.strip():
                    sse_buffer = ""
                    continue

                event, data_str = _parse_sse_event(sse_buffer)
                sse_buffer = ""

                if not event:
                    continue

                event_count += 1
                # 只打印前几个事件和重要事件
                data_preview = data_str[:200] if data_str else ""
                print(f"  [event #{event_count}] {event}: {data_preview}")

                data: object = data_str
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        pass

                if event == "plan_item":
                    c_delta, r_delta = _extract_content_fields(data)
                    if r_delta:
                        reasoning_parts.append(r_delta)
                    if c_delta:
                        content_parts.append(c_delta)
                elif event == "done":
                    print("  [done] 流式结束")
                    break

    except httpx.HTTPError as exc:
        print(f"  ✗ 网络错误: {exc}")
        return 1

    elapsed_ms = (time.monotonic() - t0) * 1000
    print("-" * 60)
    print(f"\n[7] 结果汇总 (耗时 {elapsed_ms:.0f} ms):")
    print(f"  content 长度: {len(''.join(content_parts))} 字符")
    print(f"  reasoning 长度: {len(''.join(reasoning_parts))} 字符")
    full_content = "".join(content_parts)
    if full_content:
        print(f"\n[模型回复 content]:")
        print(full_content[:2000])
    else:
        print("\n  ✗ 模型未返回任何 content")
        return 1

    print("\n✓ TRAE Work CN API 调用成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
