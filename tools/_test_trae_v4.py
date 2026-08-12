"""TRAE Work CN - 用正确的 llm_raw_chat 请求体字段测试。

正确字段: messages + model_name + display_name + prompt_max_tokens + model_type + stream

用法:
    python tools/_test_trae_v4.py
"""

from __future__ import annotations

import json
import os
import sys
import time
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


def extract_content_fields(data: object) -> tuple[str, str]:
    if data is None:
        return "", ""
    if isinstance(data, str):
        return data, ""
    if not isinstance(data, dict):
        return "", ""
    for wrapper in ("delta", "message", "plan_item", "data"):
        inner = data.get(wrapper)
        if isinstance(inner, dict):
            data = inner
            break
    content = data.get("content") or data.get("text") or ""
    reasoning = (
        data.get("reasoning_content")
        or data.get("reasoning")
        or data.get("thinking")
        or ""
    )
    if not isinstance(content, str):
        content = str(content) if content else ""
    if not isinstance(reasoning, str):
        reasoning = str(reasoning) if reasoning else ""
    return content, reasoning


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN v4 (正确字段: messages + display_name + ...)")
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

    # 1. 获取模型列表
    print("\n[1] 获取 model_list?type=llm_raw_chat ...")
    url = f"{api_host}/api/ide/v1/model_list?type=llm_raw_chat"
    resp = httpx.get(url, headers=headers, timeout=15.0)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return 1
    data = resp.json()
    configs = data.get("model_configs", [])
    print(f"  共 {len(configs)} 个模型")

    # 2. 对每个模型用正确字段尝试聊天
    print("\n[2] 对每个模型用 messages + display_name + ... 尝试聊天")
    chat_url = f"{api_host}/api/ide/v1/llm_raw_chat"

    for i, cfg in enumerate(configs[:5]):
        name = cfg.get("name", "")
        display_name = cfg.get("display_name", "")
        prompt_max = cfg.get("prompt_max_tokens", 0)
        model_type = cfg.get("model_type", "")

        print(f"\n--- [{i}] name={name} display={display_name} type={model_type} max={prompt_max} ---")

        # 尝试多种 payload 格式
        payloads = [
            # 完整字段
            {
                "messages": [{"role": "user", "content": "用中文一句话回答: 1+1=?"}],
                "model_name": name,
                "display_name": display_name,
                "prompt_max_tokens": prompt_max,
                "model_type": model_type,
                "stream": True,
            },
            # messages + model_name + stream
            {
                "messages": [{"role": "user", "content": "1+1=?"}],
                "model_name": name,
                "stream": True,
            },
            # messages + model + stream
            {
                "messages": [{"role": "user", "content": "1+1=?"}],
                "model": name,
                "stream": True,
            },
        ]

        for j, payload in enumerate(payloads):
            label = ["完整字段", "messages+model_name+stream", "messages+model+stream"][j]
            print(f"  variant {j} ({label}): {json.dumps(payload, ensure_ascii=False)[:200]}")

            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            err_msg = ""

            try:
                with httpx.stream("POST", chat_url, headers=headers, json=payload, timeout=30.0) as r:
                    print(f"    HTTP {r.status_code}")
                    if r.status_code != 200:
                        body = r.read().decode("utf-8", errors="replace")[:300]
                        print(f"    body: {body}")
                        continue

                    sse_buffer = ""
                    event_count = 0
                    for raw_line in r.iter_lines():
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
                        if event in ("plan_item", "delta", "token", "message", "content"):
                            c, r = extract_content_fields(data)
                            if c:
                                content_parts.append(c)
                            if r:
                                reasoning_parts.append(r)
                        elif event == "done":
                            break
                        elif event in ("error", "fatal_error"):
                            if isinstance(data, dict):
                                err_msg = data.get("message") or data.get("error") or data_str
                            else:
                                err_msg = data_str
                            print(f"    ✗ 错误: {err_msg}")
                            break
            except httpx.HTTPError as exc:
                print(f"    网络错误: {exc}")
                continue

            content = "".join(content_parts)
            if content:
                print(f"\n  ★★★ 成功! variant {j} ({label}) model={name}")
                print(f"  content 长度: {len(content)}")
                print(f"  回复: {content[:300]}")
                if reasoning_parts:
                    print(f"  reasoning 长度: {len(''.join(reasoning_parts))}")
                print(f"\n✓ TRAE Work CN API 调用成功")
                return 0
            elif err_msg:
                print(f"    → 失败,继续尝试下一个 variant")
            else:
                print(f"    → 无 content 也无 error,继续尝试")

    print("\n✗ 所有组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
