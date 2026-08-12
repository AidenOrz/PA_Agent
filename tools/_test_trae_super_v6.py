"""TRAE Work CN - recommend 模式 + 正确 user_query 格式。

之前发现:
- function_type=chat + user_query=[{"text":"..."}] → 成功,但用 S-CodeFusionContext-Query 模型
- function_type=recommend + user_query → model=gemini-3-flash (更适合对话)

测试 recommend 模式 + render_context.variables。

用法:
    python tools/_test_trae_super_v6.py
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
    print(f"  payload (len={len(payload_str)}): {payload_str[:500]}")
    content_parts: list[str] = []
    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as resp:
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
    print("TRAE super_completion_query - recommend 模式测试")
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

    # 正确的 user_query 格式: JSON 字符串 [{"text": "..."}]
    user_query = json.dumps([{"text": q}], ensure_ascii=False)

    # render_context.variables 也需要是 JSON 字符串
    # 尝试不同的 variables 结构
    variables_variants = [
        # 1. 空 variables
        {},
        # 2. d 函数的完整 variables
        {
            "user_input_history": json.dumps([q], ensure_ascii=False),
            "last_assistant_response": json.dumps([], ensure_ascii=False),
            "active_file_content": "",
            "symbol_infos": json.dumps([]),
            "user_additional_actions": "",
        },
        # 3. 只有 user_input_history
        {
            "user_input_history": json.dumps([q], ensure_ascii=False),
        },
        # 4. 空字符串 variables
        "",
    ]

    for i, vars_obj in enumerate(variables_variants):
        if isinstance(vars_obj, str):
            variables_str = vars_obj
        else:
            variables_str = json.dumps(vars_obj, ensure_ascii=False)

        payload = {
            "function_type": "recommend",
            "target_language": "",
            "user_query": user_query,
            "history_queries": "",
            "render_context": {"variables": variables_str},
        }
        content = try_payload(url, headers, payload, f"recommend + variables_variant_{i}")
        if content:
            print(f"\n★★★ 成功! variables_variant_{i}")
            print(f"variables: {variables_str}")
            return 0

    # 也测试不带 render_context 的 recommend
    payload = {
        "function_type": "recommend",
        "user_query": user_query,
    }
    content = try_payload(url, headers, payload, "recommend 无 render_context")
    if content:
        print(f"\n★★★ 成功!")
        return 0

    # 测试其他 function_type
    for ft in ["ask", "complete", "generate", "answer", "reply", "convert"]:
        payload = {
            "function_type": ft,
            "user_query": user_query,
        }
        content = try_payload(url, headers, payload, f"function_type={ft}")
        if content:
            print(f"\n★★★ 成功! function_type={ft}")
            return 0

    print("\n✗ 所有组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
