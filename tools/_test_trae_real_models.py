"""TRAE Work CN - 用真实模型名测试 llm_raw_chat。

从 model_list?type=llm_raw_chat 获取的真实模型名:
- seed_m8
- Doubao_1_5_thinking_pro
- deepseek-R1
- deepseek-V3
- deepseek-V3-0324

用法:
    python tools/_test_trae_real_models.py
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


def parse_sse(resp) -> tuple[str, list[str]]:
    """读取流式响应,返回 (full_content, event_lines)。"""
    content_parts: list[str] = []
    event_lines: list[str] = []
    sse_buffer = ""
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
        # 解析 SSE 块
        event = ""
        data_parts: list[str] = []
        for line in sse_buffer.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_parts.append(line[len("data:"):].lstrip())
        sse_buffer = ""
        data_str = "\n".join(data_parts)
        event_lines.append(f"[{event}] {data_str[:300]}")
        data: object = data_str
        if data_str:
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                pass
        if event == "output" or event == "plan_item":
            if isinstance(data, dict):
                choices = data.get("choices") or []
                for ch in choices:
                    if isinstance(ch, dict):
                        text = ch.get("text") or ""
                        if text:
                            content_parts.append(text)
                content = data.get("content") or ""
                if content:
                    content_parts.append(content)
        elif event == "done":
            break
        elif event in ("error", "fatal_error"):
            if isinstance(data, dict):
                msg = data.get("message") or data.get("error") or data_str
            else:
                msg = data_str
            event_lines.append(f"[ERROR] {msg}")
            break
    return "".join(content_parts), event_lines


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN - 用真实模型名测试 llm_raw_chat")
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
    models = ["seed_m8", "Doubao_1_5_thinking_pro", "deepseek-R1", "deepseek-V3", "deepseek-V3-0324"]

    # 1. 测试 llm_raw_chat
    print("\n[1] 测试 /api/ide/v1/llm_raw_chat ...")
    url = f"{api_host}/api/ide/v1/llm_raw_chat"
    for auth_scheme in ["cloud-ide-jwt", "x-ide-token"]:
        for model in models:
            headers = build_headers(token, device_id, machine_id, auth_scheme)
            payloads = [
                ("messages+model", {
                    "messages": [{"role": "user", "content": [{"type": "text", "text": q}]}],
                    "model": model,
                }),
                ("messages+model_name", {
                    "messages": [{"role": "user", "content": [{"type": "text", "text": q}]}],
                    "model_name": model,
                }),
            ]
            for label, payload in payloads:
                print(f"\n--- {auth_scheme} + {model} + {label} ---")
                try:
                    with httpx.stream("POST", url, headers=headers, json=payload, timeout=30.0) as resp:
                        if resp.status_code != 200:
                            body = resp.read().decode("utf-8", errors="replace")[:300]
                            print(f"  HTTP {resp.status_code}: {body}")
                            continue
                        content, events = parse_sse(resp)
                        for e in events[:5]:
                            print(f"  {e}")
                        if content and content != "[]":
                            print(f"  ★ content: {content[:500]}")
                            print(f"\n★★★ 成功! auth={auth_scheme} model={model} {label}")
                            return 0
                        else:
                            print(f"  (无 content)")
                except Exception as exc:
                    print(f"  ✗ {exc}")

    # 2. 测试 llm_utils_chat 用真实模型名
    print("\n\n[2] 测试 /api/agent/v3/llm_utils_chat 用真实模型名 ...")
    url2 = f"{api_host}/api/agent/v3/llm_utils_chat"
    for auth_scheme in ["cloud-ide-jwt", "x-ide-token"]:
        for model in models:
            headers = build_headers(token, device_id, machine_id, auth_scheme)
            payload = {
                "user_input": q,
                "model_name": model,
                "intent_name": "chat",
                "function": "utils",
                "chat_history": [],
            }
            print(f"\n--- {auth_scheme} + {model} ---")
            try:
                with httpx.stream("POST", url2, headers=headers, json=payload, timeout=30.0) as resp:
                    if resp.status_code != 200:
                        body = resp.read().decode("utf-8", errors="replace")[:300]
                        print(f"  HTTP {resp.status_code}: {body}")
                        continue
                    content, events = parse_sse(resp)
                    for e in events[:5]:
                        print(f"  {e}")
                    if content and content != "[]":
                        print(f"  ★ content: {content[:500]}")
                        print(f"\n★★★ 成功! auth={auth_scheme} model={model}")
                        return 0
                    else:
                        print(f"  (无 content)")
            except Exception as exc:
                print(f"  ✗ {exc}")

    print("\n✗ 所有组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
