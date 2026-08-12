"""TRAE Work CN - 获取可用模型列表。

从 ai_agent.dll 提取的关键字:
filesystemresponse_schematoolcall_historyintent_namecurrent_turn
token_usage_variable_keysstruct RenderInput with 10 elements

说明 llm_utils_chat 的请求字段包括: intent_name, current_turn, token_usage,
variable_keys, toolcall_history, filesystemresponse_schema

用法:
    python tools/_test_trae_models_list.py
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
        "Accept": "application/json",
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


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN - 模型列表 + 完整 llm_utils_chat 测试")
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

    # 1. 获取模型列表 (model_list)
    print("\n[1] 获取模型列表 ...")
    for auth_scheme in ["x-ide-token", "cloud-ide-jwt"]:
        for type_param in ["llm_raw_chat", "llm_utils_chat", "chat", "agent"]:
            url = f"{api_host}/api/ide/v1/model_list?type={type_param}"
            headers = build_headers(token, device_id, machine_id, auth_scheme)
            try:
                resp = httpx.get(url, headers=headers, timeout=15.0)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("model_configs") or data.get("models") or []
                    if models:
                        print(f"  ✓ auth={auth_scheme} type={type_param}: {len(models)} 模型")
                        for m in models[:20]:
                            name = m.get("name") or m.get("model") or "?"
                            print(f"    - {name}")
                        if len(models) > 0:
                            # 保存第一个模型名用于后续测试
                            with open(Path(__file__).parent / "_trae_models_found.json", "w", encoding="utf-8") as f:
                                json.dump({"auth": auth_scheme, "type": type_param, "models": models}, f, ensure_ascii=False, indent=2)
                            return 0
                else:
                    body = resp.text[:200]
                    print(f"  ✗ auth={auth_scheme} type={type_param}: HTTP {resp.status_code} {body}")
            except Exception as exc:
                print(f"  ✗ auth={auth_scheme} type={type_param}: {exc}")

    # 2. 用完整字段调用 llm_utils_chat (Cloud-IDE-JWT)
    print("\n[2] 测试 llm_utils_chat 用完整字段 ...")
    q = "用中文一句话回答: 1+1=?"
    url = f"{api_host}/api/agent/v3/llm_utils_chat"
    headers = build_headers(token, device_id, machine_id, "cloud-ide-jwt")
    headers["Accept"] = "text/event-stream"

    payloads = [
        ("完整字段 v1 (intent_name=chat)", {
            "user_input": q,
            "model_name": "glm-5.2",
            "intent_name": "chat",
            "function": "utils",
            "chat_history": [],
            "current_turn": 1,
            "toolcall_history": [],
            "variable_keys": [],
            "token_usage": {},
            "filesystemresponse_schema": {},
        }),
        ("完整字段 v2 (intent_name=free_chat)", {
            "user_input": q,
            "model_name": "glm-5.2",
            "intent_name": "free_chat",
            "function": "utils",
            "chat_history": [],
        }),
        ("完整字段 v3 (intent_name=codebase_chat)", {
            "user_input": q,
            "model_name": "glm-5.2",
            "intent_name": "codebase_chat",
            "function": "utils",
            "chat_history": [],
        }),
        ("用 model 而非 model_name", {
            "user_input": q,
            "model": "glm-5.2",
            "intent_name": "chat",
            "function": "utils",
            "chat_history": [],
        }),
        ("messages 格式", {
            "messages": [{"role": "user", "content": q}],
            "model_name": "glm-5.2",
            "intent_name": "chat",
            "function": "utils",
        }),
    ]

    for label, payload in payloads:
        print(f"\n--- {label} ---")
        print(f"  payload: {json.dumps(payload, ensure_ascii=False)[:300]}")
        try:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=30.0) as resp:
                print(f"  HTTP {resp.status_code}")
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")[:500]
                    print(f"  body: {body}")
                    continue
                # 读取所有 SSE
                content_parts = []
                event_count = 0
                for raw_line in resp.iter_lines():
                    if raw_line is None:
                        continue
                    if isinstance(raw_line, bytes):
                        raw_line = raw_line.decode("utf-8", errors="replace")
                    if not raw_line:
                        continue
                    event_count += 1
                    if event_count <= 15:
                        print(f"    {raw_line[:300]}")
                    if raw_line.startswith("data:"):
                        data_str = raw_line[5:].lstrip()
                        try:
                            data = json.loads(data_str)
                            if isinstance(data, dict):
                                # plan_item / output 中的 content
                                content = data.get("content") or ""
                                choices = data.get("choices") or []
                                for ch in choices:
                                    if isinstance(ch, dict):
                                        content = ch.get("text") or content
                                if content:
                                    content_parts.append(content)
                        except json.JSONDecodeError:
                            pass
                full = "".join(content_parts)
                if full:
                    print(f"  ★ content: {full[:500]}")
                    return 0
        except Exception as exc:
            print(f"  ✗ {exc}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
