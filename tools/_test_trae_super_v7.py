"""TRAE Work CN - 寻找能返回真实对话内容的 function_type。

v6 测试发现:
- function_type=recommend + user_query=[{"text":"..."}] → HTTP 200, 但返回 [] (推荐列表为空)
- recommend 是用于"建议下一个问题"的功能,不是真正的对话

测试其他 function_type (chat, ask, answer, complete, generate 等) 看哪个能返回真实模型回复。

用法:
    python tools/_test_trae_super_v7.py
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


def try_payload(url: str, headers: dict, payload: dict, label: str) -> tuple[str, str]:
    """测试一个 payload,返回 (content, model_used)。"""
    print(f"\n--- {label} ---")
    print(f"  payload: {json.dumps(payload, ensure_ascii=False)[:400]}")
    content_parts: list[str] = []
    model_used = ""
    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as resp:
            print(f"  HTTP {resp.status_code}")
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:300]
                print(f"  body: {body}")
                return "", ""
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
                if event_count <= 12:
                    preview = data_str[:300] if data_str else ""
                    print(f"    [#{event_count}] {event}: {preview}")
                data: object = data_str
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        pass
                if event == "meta" and isinstance(data, dict):
                    m = data.get("model")
                    if m and isinstance(m, str):
                        model_used = m
                elif event == "output":
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
        return "", ""

    content = "".join(content_parts)
    if content:
        print(f"  ★ model={model_used} content (len={len(content)}): {content[:500]}")
    return content, model_used


def main() -> int:
    print("=" * 60)
    print("TRAE super_completion_query - 寻找真实对话 function_type")
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
    user_query = json.dumps([{"text": q}], ensure_ascii=False)

    # 各种 function_type 尝试
    function_types = [
        "chat",
        "ask",
        "answer",
        "complete",
        "generate",
        "reply",
        "convert",
        "code_chat",
        "codebase_chat",
        "free_chat",
        "plain_chat",
        "raw_chat",
        "general_chat",
        "qa",
        "conversation",
    ]

    print(f"\n测试 {len(function_types)} 种 function_type (user_query=[{{text:...}}])...")

    successes: list[tuple[str, str, str]] = []  # (label, model, content)

    for ft in function_types:
        payload = {
            "function_type": ft,
            "user_query": user_query,
        }
        content, model = try_payload(url, headers, payload, f"function_type={ft}")
        if content and content != "[]":
            successes.append((ft, model, content))

    # 也尝试带 render_context 的 chat
    print("\n\n=== 带 render_context 的 chat ===")
    variables_str = json.dumps({}, ensure_ascii=False)
    payload = {
        "function_type": "chat",
        "user_query": user_query,
        "render_context": {"variables": variables_str},
    }
    content, model = try_payload(url, headers, payload, "chat + empty render_context")
    if content and content != "[]":
        successes.append(("chat+ctx", model, content))

    # 总结
    print("\n\n" + "=" * 60)
    if successes:
        print(f"✓ {len(successes)} 种 function_type 返回了真实对话内容:")
        for ft, model, content in successes:
            print(f"  - function_type={ft} (model={model}): {content[:200]}")
        return 0
    else:
        print("✗ 没有找到能返回真实对话内容的 function_type")
        return 1


if __name__ == "__main__":
    sys.exit(main())
