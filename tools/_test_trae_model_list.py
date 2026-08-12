"""Fetch the full model list from TRAE Work CN's model_list_by_function endpoint.

The TRAE desktop app calls this on startup to populate its model picker.
We replicate the call to discover all available internal model names.
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


# Known endpoints from logs.
ENDPOINTS = [
    # model_list_by_function — used by TRAE desktop to populate model picker.
    ("/api/ide/v1/model_list_by_function", {"function": "chat"}),
    ("/api/ide/v1/model_list_by_function", {"function": "agent"}),
    ("/api/ide/v1/model_list_by_function", {}),
    # model_list
    ("/api/ide/v1/model_list", {}),
    # agent model list
    ("/api/agent/v1/model_list", {}),
    ("/api/agent/v3/model_list", {}),
    # Try various namespaces
    ("/api/ide/v1/llm/model_list", {}),
    ("/api/ide/v1/llm/models", {}),
    ("/api/ide/v1/models", {}),
]


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


def try_post(host: str, path: str, body: dict, headers: dict, timeout: float = 10.0) -> tuple[int, str]:
    url = f"{host}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, text
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return exc.code, text
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print("=" * 60)
    print("TRAE Work CN — 完整模型列表获取")
    print("=" * 60)

    token = _extract_trae_cn_token()
    if not token:
        print("✗ 无法提取 Token")
        return 1
    if _is_jwt_expired(token):
        print("✗ Token 已过期")
        return 1
    print(f"✓ Token (len={len(token)})")

    info = _get_trae_cn_info()
    if info is None:
        print("✗ 无法读取 device/machine id")
        return 1
    api_host, jwt, device_info = info
    device_id = device_info.get("device_id", "") or device_info.get("deviceId", "")
    machine_id = device_info.get("machine_id", "") or device_info.get("machineId", "")
    print(f"✓ api_host={api_host}")
    print(f"✓ device_id={device_id}")
    print(f"✓ machine_id={machine_id}")

    headers = build_headers(token, device_id, machine_id)

    print(f"\n[尝试 {len(ENDPOINTS)} 个端点]")
    for path, body in ENDPOINTS:
        status, text = try_post(_DEFAULT_TRAE_API_HOST, path, body, headers)
        snippet = text.replace("\n", " ")[:300]
        marker = "✓" if status == 200 else "~" if status > 0 else "✗"
        print(f"\n{marker} POST {path}")
        print(f"  body: {body}")
        print(f"  -> {status}: {snippet}")

        if status == 200 and text.strip().startswith(("{", "[")):
            try:
                data = json.loads(text)
                # Extract model names from common shapes.
                models = extract_model_names(data)
                if models:
                    print(f"\n  ✓✓✓ 找到 {len(models)} 个模型 ✓✓✓")
                    for i, m in enumerate(sorted(set(models)), 1):
                        print(f"  {i:2d}. {m}")
            except json.JSONDecodeError:
                pass

    return 0


def extract_model_names(data) -> list[str]:
    """Recursively extract 'model_name' / 'name' / 'model' fields from JSON."""
    names: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = k.lower()
                if kl in ("model_name", "model", "name", "model_id", "value", "key") and isinstance(v, str) and v:
                    # Heuristic: model names look like identifiers with - or _ or dots.
                    if any(c in v for c in "-_.") or v.replace("_", "").replace("-", "").isalnum():
                        if not v.startswith("$") and len(v) < 80:
                            names.append(v)
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return names


if __name__ == "__main__":
    sys.exit(main())
