"""TRAE Work CN - user_query 需要 UserQuerySnippet 数组格式。

错误信息:
- "cannot unmarshal string into Go value of type util_entity.UserQuery"
- "cannot unmarshal string into Go value of type util_entity.UserQuerySnippet"

说明 user_query 是数组,元素是 UserQuerySnippet 对象。

用法:
    python tools/_test_trae_super_v5.py
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
    print(f"\n--- {label} ---")
    payload_str = json.dumps(payload, ensure_ascii=False)
    print(f"  payload (len={len(payload_str)}): {payload_str[:400]}")
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
                if event_count <= 15:
                    preview = data_str[:250] if data_str else ""
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
        print(f"  ★ content: {content[:300]}")
    return content


def main() -> int:
    print("=" * 60)
    print("TRAE super_completion_query - UserQuerySnippet 格式")
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

    # user_query 应该是数组,元素是 UserQuerySnippet 对象
    # 尝试各种字段名组合
    snippet_variants = [
        {"text": q},
        {"content": q},
        {"query": q},
        {"input": q},
        {"message": q},
        {"user_input": q},
        {"q": q},
        {"text": q, "type": "text"},
        {"content": q, "type": "text"},
        {"data": q},
        {"body": q},
        {"value": q},
    ]

    for snippet in snippet_variants:
        uq = json.dumps([snippet], ensure_ascii=False)
        payload = {
            "function_type": "chat",
            "user_query": uq,
        }
        content = try_payload(url, headers, payload, f"chat + user_query=[{list(snippet.keys())[0]}]")
        if content:
            print(f"\n★★★ 成功!")
            print(f"snippet 格式: {snippet}")
            return 0

    # 也尝试 user_query 是单个对象(不是数组)
    for snippet in snippet_variants[:6]:
        uq = json.dumps(snippet, ensure_ascii=False)
        payload = {
            "function_type": "chat",
            "user_query": uq,
        }
        content = try_payload(url, headers, payload, f"chat + user_query=单对象{list(snippet.keys())[0]}")
        if content:
            print(f"\n★★★ 成功!")
            print(f"snippet 格式: {snippet}")
            return 0

    print("\n✗ 所有组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
