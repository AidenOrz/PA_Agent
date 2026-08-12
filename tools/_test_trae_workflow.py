"""TRAE Work CN - 测试 workflow/start 端点 (实际聊天端点)。

从日志发现:
- api/agent/v3/workflow/start - 实际的聊天/工作流端点
- api/agent/v3/llm_utils_chat - 生成会话标题等工具调用
- api/ide/v1/super_completion_query - 代码补全

workflow/start 可能是真正的聊天端点。

用法:
    python tools/_test_trae_workflow.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_trae_standalone import (
    _TRAE_APP_ID,
    extract_token,
    find_data_dir,
    get_api_host,
    read_device_info,
)


def build_headers(token: str, device_id: str, machine_id: str, auth_scheme: str = "x-ide-token") -> dict[str, str]:
    trace_id = uuid.uuid4().hex
    request_id = str(uuid.uuid4())
    h = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-app-id": _TRAE_APP_ID,
        "x-app-version": "default",
        "x-app-version-code": "20260630",
        "x-ide-version": "3.3.76",
        "x-ide-version-code": "20260630",
        "x-ide-version-type": "stable",
        "x-custom-trace-id": trace_id,
        "x-flow-traceparent": f"04-{trace_id}-{uuid.uuid4().hex[:16]}-01",
        "x-device-id": device_id,
        "x-machine-id": machine_id,
        "x-device-brand": "PA-Agent",
        "x-device-cpu": "Intel",
        "x-device-type": "windows",
        "x-os-version": "Windows",
        "request-traffic-type": "prod",
        "x-request-id": request_id,
        "x-trae-request-id": request_id,
    }
    if auth_scheme == "x-ide-token":
        h["x-ide-token"] = token
    elif auth_scheme == "cloud-ide-jwt":
        h["Authorization"] = f"Cloud-IDE-JWT {token}"
    elif auth_scheme == "bearer":
        h["Authorization"] = f"Bearer {token}"
    return h


def parse_sse_event(raw_block: str) -> tuple[str, str]:
    event = ""
    data_parts: list[str] = []
    for line in raw_block.splitlines():
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_parts.append(line[len("data:"):].lstrip())
    return event, "\n".join(data_parts)


def try_payload(url: str, headers: dict, payload: dict, label: str) -> str:
    print(f"\n--- {label} ---")
    payload_str = json.dumps(payload, ensure_ascii=False)
    print(f"  payload (len={len(payload_str)}): {payload_str[:500]}")
    content_parts: list[str] = []
    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as resp:
            print(f"  HTTP {resp.status_code}")
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                print(f"  body: {body}")
                return ""
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
                event, data_str = parse_sse_event(sse_buffer)
                sse_buffer = ""
                if not event:
                    continue
                event_count += 1
                if event_count <= 20:
                    preview = data_str[:300] if data_str else ""
                    print(f"    [#{event_count}] {event}: {preview}")
                data: object = data_str
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        pass
                if event == "output":
                    if isinstance(data, dict):
                        choices = data.get("choices") or []
                        for ch in choices:
                            if isinstance(ch, dict):
                                text = ch.get("text") or ""
                                if text:
                                    content_parts.append(text)
                elif event == "plan_item":
                    if isinstance(data, dict):
                        c = data.get("content") or ""
                        if c:
                            content_parts.append(c)
                elif event == "done":
                    break
                elif event in ("error", "fatal_error"):
                    if isinstance(data, dict):
                        msg = data.get("message") or data.get("error") or data_str
                    else:
                        msg = data_str
                    print(f"    ✗ 错误: {msg}")
                    break
    except httpx.HTTPError as exc:
        print(f"  网络错误: {exc}")
        return ""

    content = "".join(content_parts)
    if content:
        print(f"  ★ content (len={len(content)}): {content[:500]}")
    return content


def main() -> int:
    print("=" * 60)
    print("TRAE workflow/start 端点测试")
    print("=" * 60)

    data_dir = find_data_dir()
    if data_dir is None:
        return 1
    token = extract_token(data_dir)
    if not token:
        return 1
    device_info = read_device_info(data_dir)
    device_id = device_info.get("device_id", "") or "unknown"
    machine_id = device_info.get("machine_id", "") or "unknown"
    api_host = get_api_host(data_dir)

    q = "用中文一句话回答: 1+1=?"

    # 测试 workflow/start 端点
    url = f"{api_host}/api/agent/v3/workflow/start"
    print(f"\n端点: {url}")

    # 尝试不同的认证方式
    for auth_scheme in ["x-ide-token", "cloud-ide-jwt", "bearer"]:
        headers = build_headers(token, device_id, machine_id, auth_scheme)

        # 尝试不同的 payload 格式
        payloads = [
            ("简单 user_input", {
                "user_input": q,
                "model_name": "glm-5.2",
            }),
            ("messages 格式", {
                "messages": [{"role": "user", "content": q}],
                "model": "glm-5.2",
            }),
            ("user_query 格式", {
                "user_query": json.dumps([{"text": q}], ensure_ascii=False),
                "function_type": "chat",
            }),
            ("query + model", {
                "query": q,
                "model": "glm-5.2",
                "function": "chat",
            }),
        ]

        for label, payload in payloads:
            content = try_payload(url, headers, payload, f"{auth_scheme} + {label}")
            if content:
                print(f"\n★★★ 成功! auth={auth_scheme}, {label}")
                return 0

    # 也测试 llm_utils_chat 用不同认证方式
    print("\n\n=== 测试 llm_utils_chat 用 cloud-ide-jwt ===")
    url2 = f"{api_host}/api/agent/v3/llm_utils_chat"
    headers2 = build_headers(token, device_id, machine_id, "cloud-ide-jwt")
    payload2 = {
        "user_input": q,
        "model_name": "glm-5.2",
        "intent_name": "chat",
        "function": "utils",
        "chat_history": [],
    }
    content = try_payload(url2, headers2, payload2, "llm_utils_chat + cloud-ide-jwt")
    if content:
        print(f"\n★★★ 成功!")
        return 0

    print("\n✗ 所有组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
