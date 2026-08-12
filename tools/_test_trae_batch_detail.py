"""Fetch full model list from TRAE's /api/ide/v1/batch_get_detail_param endpoint.

Discovered from ai-agent log:
  POST https://trae-api-cn.mchost.guru/api/ide/v1/batch_get_detail_param
  Body: BatchDetailParamRequest {
      functions: ["assistant", "solo_agent_lite", "solo_coder",
                  "solo_agent_remote", "solo_work_lite", "solo_work_remote",
                  "solo_design_lite", "solo_design_remote", "builder"],
      agent_type: "",
      current_config_info: { config_name: "", is_custom_model: false },
      mode_type: "Manual",
      access_type: "SoloLite",
      ab_force_vids: "",
      ab_autotest_advanced_mode: 0
  }
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pa_agent.ai.trae_connector import (
    _extract_trae_cn_token,
    _get_trae_cn_info,
    _DEFAULT_TRAE_API_HOST,
    _TRAE_APP_ID,
    _is_jwt_expired,
)
import uuid


def build_headers(token: str, device_id: str, machine_id: str) -> dict[str, str]:
    trace_id = uuid.uuid4().hex
    request_id = str(uuid.uuid4())
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream, */*",
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
        "x-device-type": "windows",
        "x-os-version": "Windows",
        "request-traffic-type": "prod",
        "x-request-id": request_id,
        "x-trae-request-id": request_id,
        "Authorization": f"Cloud-IDE-JWT {token}",
        "x-ide-token": token,
    }


def extract_models(data, models: set, labels: dict, depth: int = 0) -> None:
    """Recursively extract model names from the response JSON."""
    if depth > 10:
        return
    if isinstance(data, dict):
        # Check for model_name / name / model_id fields.
        for k in ("model_name", "model_id", "modelName", "modelId"):
            v = data.get(k)
            if isinstance(v, str) and v and not v.startswith("$"):
                models.add(v)
        # Check for model_id pattern in "id" fields.
        id_val = data.get("id", "")
        if isinstance(id_val, str) and "__" in id_val:
            parts = id_val.rsplit("__", 1)
            if len(parts) == 2 and "_" in parts[0]:
                label = parts[0].rsplit("_", 1)[0]
                name = parts[1]
                if label not in labels:
                    labels[label] = set()
                labels[label].add(name)
                models.add(name)

        # Check label/agent_type fields with model lists.
        label = data.get("label") or data.get("agent_type") or data.get("function")
        if isinstance(label, str) and label:
            for k in ("models", "model_list", "model_configs"):
                v = data.get(k)
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            name = item.get("model_name") or item.get("name") or item.get("model")
                            if isinstance(name, str) and name:
                                if label not in labels:
                                    labels[label] = set()
                                labels[label].add(name)
                                models.add(name)

        # Recurse into all values.
        for v in data.values():
            extract_models(v, models, labels, depth + 1)
    elif isinstance(data, list):
        for item in data:
            extract_models(item, models, labels, depth + 1)


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN — 完整模型列表获取")
    print("  端点: /api/ide/v1/batch_get_detail_param")
    print("=" * 60)

    token = _extract_trae_cn_token()
    if not token or _is_jwt_expired(token):
        print("✗ Token 不可用")
        return 1
    info = _get_trae_cn_info()
    api_host, jwt, device_info = info
    device_id = device_info.get("device_id", "") or device_info.get("deviceId", "")
    machine_id = device_info.get("machine_id", "") or device_info.get("machineId", "")
    headers = build_headers(token, device_id, machine_id)
    print(f"✓ Token / device 就绪")

    # Build request body matching the log format.
    body = {
        "functions": [
            "assistant", "solo_agent_lite", "solo_coder", "solo_agent_remote",
            "solo_work_lite", "solo_work_remote", "solo_design_lite",
            "solo_design_remote", "builder",
        ],
        "agent_type": "",
        "current_config_info": {
            "config_name": "",
            "is_custom_model": False,
        },
        "mode_type": "Manual",
        "access_type": "SoloLite",
        "ab_force_vids": "",
        "ab_autotest_advanced_mode": 0,
    }

    url = f"{_DEFAULT_TRAE_API_HOST}/api/ide/v1/batch_get_detail_param"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    print(f"\n[POST] {url}")
    print(f"  body: {json.dumps(body)[:200]}...")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:
        print(f"✗ 请求失败: {exc}")
        return 1

    print(f"\n-> HTTP {status}")
    print(f"   响应长度: {len(text)} 字符")

    if status != 200:
        print(f"   响应: {text[:500]}")
        return 1

    # Parse and extract models.
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"✗ JSON 解析失败: {exc}")
        print(f"   响应前 500 字符: {text[:500]}")
        return 1

    models: set[str] = set()
    labels: dict[str, set[str]] = {}
    extract_models(data, models, labels)

    print("\n" + "=" * 60)
    print("模型列表 (按 label 分组)")
    print("=" * 60)
    for label in sorted(labels.keys()):
        ms = sorted(labels[label])
        print(f"\n[{label}] ({len(ms)} 个)")
        for i, m in enumerate(ms, 1):
            print(f"  {i:2d}. {m}")

    print("\n" + "=" * 60)
    print(f"所有模型名 ({len(models)} 个)")
    print("=" * 60)
    for i, m in enumerate(sorted(models), 1):
        print(f"  {i:2d}. {m}")

    # Save full response for inspection.
    out_file = Path(__file__).parent / "_trae_model_list_response.json"
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整响应已保存到: {out_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
