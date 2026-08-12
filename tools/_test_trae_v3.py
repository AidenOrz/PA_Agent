"""TRAE Work CN - 通过 model_list?type=llm_raw_chat 获取模型列表并聊天。

用法:
    python tools/_test_trae_v3.py
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
    print("TRAE Work CN v3 测试 (model_list?type= + 真实聊天)")
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

    # 1. 获取模型列表 (带 type 参数)
    print("\n[1] 获取 model_list?type=llm_raw_chat ...")
    url = f"{api_host}/api/ide/v1/model_list?type=llm_raw_chat"
    print(f"  GET {url}")
    resp = httpx.get(url, headers=headers, timeout=15.0)
    print(f"  HTTP {resp.status_code}")
    print(f"  响应: {resp.text[:1500]}")
    if resp.status_code != 200:
        return 1

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print("  ✗ 响应不是 JSON")
        return 1

    # 提取模型名
    model_names: list[str] = []
    if isinstance(data, dict):
        # 尝试不同字段
        for key in ("model_configs", "models", "data", "list"):
            v = data.get(key)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        for mk in ("model", "id", "name", "model_name", "model_id"):
                            mv = item.get(mk)
                            if mv and isinstance(mv, str):
                                model_names.append(mv)
                                break
                    elif isinstance(item, str):
                        model_names.append(item)
                break

    # 去重保序
    seen = set()
    unique_models = []
    for m in model_names:
        if m not in seen:
            seen.add(m)
            unique_models.append(m)

    print(f"\n  发现 {len(unique_models)} 个模型:")
    for i, m in enumerate(unique_models[:30]):
        print(f"    [{i}] {m}")
    if len(unique_models) > 30:
        print(f"    ... (共 {len(unique_models)} 个)")

    if not unique_models:
        print("\n✗ 未找到模型")
        return 1

    # 2. 对前几个模型实际发起聊天
    print("\n[2] 对每个模型实际聊天测试 (用 llm_raw_chat + x-ide-token) ...")
    chat_url = f"{api_host}/api/ide/v1/llm_raw_chat"
    success_models: list[str] = []

    test_models = unique_models[:15]  # 前 15 个
    for model in test_models:
        payload = {
            "user_input": "用中文一句话回答: 1+1=?",
            "model_name": model,
        }
        print(f"\n--- model={model} ---")
        print(f"  POST {chat_url}")
        print(f"  payload: {json.dumps(payload, ensure_ascii=False)}")

        content_parts: list[str] = []
        try:
            with httpx.stream("POST", chat_url, headers=headers, json=payload, timeout=30.0) as r:
                print(f"  HTTP {r.status_code}")
                if r.status_code != 200:
                    body = r.read().decode("utf-8", errors="replace")[:300]
                    print(f"  body: {body}")
                    continue

                sse_buffer = ""
                event_count = 0
                err_msg = ""
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
                    if event_count <= 5:
                        preview = data_str[:150] if data_str else ""
                        print(f"    [#{event_count}] {event}: {preview}")
                    data: object = data_str
                    if data_str:
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            pass
                    if event in ("plan_item", "delta", "token", "message"):
                        c, _ = extract_content_fields(data)
                        if c:
                            content_parts.append(c)
                    elif event == "done":
                        break
                    elif event in ("error", "fatal_error"):
                        if isinstance(data, dict):
                            err_msg = data.get("message") or data.get("error") or data_str
                        else:
                            err_msg = data_str
                        print(f"    ✗ 错误: {err_msg}")
                        break

            content = "".join(content_parts)
            if content:
                print(f"\n  ★ 成功! content 长度 {len(content)}")
                print(f"  回复: {content[:200]}")
                success_models.append(model)
                # 第一个成功的就够了
                break
            elif not err_msg:
                print(f"  (无 content 也无 error)")
        except httpx.HTTPError as exc:
            print(f"  网络错误: {exc}")

    print("\n" + "=" * 60)
    if success_models:
        print(f"✓ 成功的模型: {success_models}")
        return 0
    else:
        print("✗ 所有模型都失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
