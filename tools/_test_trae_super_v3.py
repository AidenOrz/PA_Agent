"""TRAE Work CN - 测试 super_completion_query 用不同字段名。

之前发现:
- {"query": "...", "model": "..."} 返回 "user query is empty"
- 完整 d 函数请求体返回 HTTP 400

测试各种字段名组合,找到能成功的。

用法:
    python tools/_test_trae_super_v3.py
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


def build_headers(token: str, device_id: str, machine_id: str) -> dict[str, str]:
    trace_id = uuid.uuid4().hex
    request_id = str(uuid.uuid4())
    return {
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
        "x-ide-token": token,
    }


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
    """测试一个 payload,返回 content 字符串或空。"""
    print(f"\n--- {label} ---")
    print(f"  payload: {json.dumps(payload, ensure_ascii=False)[:300]}")
    content_parts: list[str] = []
    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=30.0) as resp:
            print(f"  HTTP {resp.status_code}")
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:300]
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
                if event_count <= 8:
                    preview = data_str[:200] if data_str else ""
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
        print(f"  ★ content: {content[:200]}")
    return content


def main() -> int:
    print("=" * 60)
    print("TRAE super_completion_query 字段名测试")
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
    headers = build_headers(token, device_id, machine_id)
    url = f"{api_host}/api/ide/v1/super_completion_query"

    q = "用中文一句话回答: 1+1=?"
    payloads = [
        ("user_query 单字段", {"user_query": q}),
        ("user_input 单字段", {"user_input": q}),
        ("prompt 单字段", {"prompt": q}),
        ("text 单字段", {"text": q}),
        ("content 单字段", {"content": q}),
        ("message 单字段", {"message": q}),
        ("input 单字段", {"input": q}),
        ("q 单字段", {"q": q}),
        ("user_query + function_type", {"user_query": q, "function_type": "recommend"}),
        ("user_query + function_type=recommend + recommend_scene", {"user_query": q, "function_type": "recommend", "recommend_scene": "chat_input"}),
        ("user_query + function_type=chat", {"user_query": q, "function_type": "chat"}),
        ("完整 d 函数 + user_query 非空", {
            "env_metadata": "{}",
            "function_type": "recommend",
            "recommend_scene": "chat_input",
            "target_language": "",
            "user_query": q,
            "history_queries": "",
            "render_context": {"variables": json.dumps({
                "user_input_history": json.dumps([q]),
                "last_assistant_response": json.dumps([]),
                "active_file_content": "",
                "symbol_infos": json.dumps([]),
                "user_additional_actions": "",
            })},
        }),
        # 尝试不传 render_context
        ("user_query + function_type + target_language", {
            "user_query": q,
            "function_type": "recommend",
            "target_language": "zh",
        }),
    ]

    for label, payload in payloads:
        content = try_payload(url, headers, payload, label)
        if content:
            print(f"\n★★★ 成功! {label}")
            print(f"完整 payload: {json.dumps(payload, ensure_ascii=False)}")
            return 0

    print("\n✗ 所有组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
