"""TRAE Work CN - 获取可用模型列表,然后实际发送聊天请求。

用法:
    python tools/_test_trae_get_models.py
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
    _DEFAULT_TRAE_API_HOST,
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


def try_get_model_list(api_host: str, headers: dict) -> dict | None:
    """尝试调用 model_list 端点获取可用模型列表。"""
    candidate_paths = [
        "/api/ide/v1/model_list",
        "/api/ide/v1/models",
        "/api/agent/v3/model_list",
        "/api/agent/v3/models",
        "/api/ide/v1/llm_model_list",
        "/api/ide/v1/raw_model_list",
        "/api/agent/v3/llm_model_list",
    ]
    for path in candidate_paths:
        url = f"{api_host}{path}"
        print(f"\n  尝试 GET {url}")
        try:
            # 注意 model_list 可能是 POST 也可能是 GET
            for method in ("GET", "POST"):
                try:
                    if method == "GET":
                        resp = httpx.get(url, headers=headers, timeout=10.0)
                    else:
                        resp = httpx.post(url, headers=headers, json={}, timeout=10.0)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            print(f"    {method} {resp.status_code} JSON: {str(data)[:300]}")
                            if isinstance(data, dict) and (data.get("models") or data.get("data")):
                                return data
                        except json.JSONDecodeError:
                            print(f"    {method} {resp.status_code} 文本: {resp.text[:300]}")
                    else:
                        snippet = resp.text[:200] if resp.text else ""
                        print(f"    {method} {resp.status_code}: {snippet}")
                except httpx.HTTPError as exc:
                    print(f"    {method} 错误: {exc}")
        except Exception as exc:
            print(f"  异常: {exc}")
    return None


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


def try_chat(api_host: str, headers: dict, payload: dict, label: str) -> str:
    """实际发送聊天请求,返回 content 字符串。"""
    url = f"{api_host}/api/ide/v1/llm_raw_chat"
    print(f"\n--- {label} ---")
    print(f"  URL: {url}")
    print(f"  Payload: {json.dumps(payload, ensure_ascii=False)[:200]}")

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    final_status = None
    final_err = ""

    try:
        with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as resp:
            final_status = resp.status_code
            print(f"  HTTP {resp.status_code}")
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                print(f"  响应体: {body}")
                return ""

            print("  事件流:")
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
                preview = data_str[:200] if data_str else ""
                print(f"    [#{event_count}] {event}: {preview}")
                data: object = data_str
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        pass
                if event == "plan_item" or event == "delta" or event == "token":
                    c_delta, r_delta = extract_content_fields(data)
                    if r_delta:
                        reasoning_parts.append(r_delta)
                    if c_delta:
                        content_parts.append(c_delta)
                elif event == "done":
                    break
                elif event in ("error", "fatal_error"):
                    if isinstance(data, dict):
                        final_err = data.get("message") or data.get("error") or data_str
                    else:
                        final_err = data_str
                    print(f"    ✗ 错误: {final_err}")
                    break
    except httpx.HTTPError as exc:
        print(f"  网络错误: {exc}")
        return ""

    content = "".join(content_parts)
    print(f"\n  content 长度: {len(content)}")
    if content:
        print(f"  content: {content[:500]}")
    return content


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN 模型列表查询 + 实际聊天测试")
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
    print("\n[1] 查询模型列表 ...")
    models_data = try_get_model_list(api_host, headers)

    available_models: list[str] = []
    if models_data:
        print(f"\n  原始数据: {json.dumps(models_data, ensure_ascii=False)[:500]}")
        # 尝试不同的字段路径
        if isinstance(models_data, dict):
            for key in ("models", "data", "list", "items"):
                v = models_data.get(key)
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            for mk in ("id", "name", "model", "model_id", "model_name"):
                                if item.get(mk):
                                    available_models.append(str(item[mk]))
                                    break
                        elif isinstance(item, str):
                            available_models.append(item)
            # 也可能是嵌套的
            if not available_models:
                # 直接把整个 dict 的所有值中是字符串的找出来作为模型名
                for v in models_data.values():
                    if isinstance(v, str) and ("-" in v or "_" in v):
                        available_models.append(v)

    print(f"\n  发现的模型名: {available_models}")

    # 2. 尝试各种已知的模型名
    print("\n[2] 尝试聊天调用 ...")
    candidate_models = list(set(
        available_models + [
            "glm-5.2", "glm-5.1", "glm-4.5",
            "kimi-k2.7-code", "kimi-k2",
            "claude-3.7-sonnet", "claude-sonnet-4",
            "seed_m8", "seed-1.6",
            "deepseek-v3", "deepseek-r1",
            "default", "auto",
        ]
    ))

    # 尝试不同的 payload 格式
    payload_variants = [
        # 简化版
        lambda m: {"user_input": "1+1=?", "model_name": m},
        # 带 messages
        lambda m: {"user_input": "1+1=?", "model_name": m, "messages": [{"role": "user", "content": "1+1=?"}]},
        # 带 prompt
        lambda m: {"prompt": "1+1=?", "model": m},
        # 带 query
        lambda m: {"query": "1+1=?", "model": m},
        # messages + model
        lambda m: {"messages": [{"role": "user", "content": "1+1=?"}], "model": m},
    ]

    # 只测前 5 个候选模型,避免过多请求
    for model in candidate_models[:8]:
        for i, payload_fn in enumerate(payload_variants):
            payload = payload_fn(model)
            content = try_chat(api_host, headers, payload, f"model={model} payload_variant={i}")
            if content:
                print(f"\n  ★★★ 成功! model={model} payload_variant={i}")
                print(f"  Payload 模板: {json.dumps(payload, ensure_ascii=False)}")
                return 0

    print("\n所有模型名+payload 组合都失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())
