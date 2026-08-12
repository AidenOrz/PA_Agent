"""Try different param shapes for /api/ide/v1/model_list to get full model list."""
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


def try_post(path: str, body: dict, headers: dict, timeout: float = 10.0) -> tuple[int, str]:
    url = f"{_DEFAULT_TRAE_API_HOST}{path}"
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


# Different param shapes observed in TRAE-like APIs.
PARAM_SHAPES = [
    # Maybe needs function/scene.
    {"function": "chat"},
    {"scene": "chat"},
    {"function": "icube_chat"},
    {"function": "ai_chat"},
    {"scene": "icube_chat"},
    {"function": "solo_agent_lite"},
    {"agent_type": "solo_agent_lite"},
    {"agent_label": "solo_agent_lite"},
    {"label": "solo_agent_lite"},
    {"type": "solo_agent_lite"},
    # Maybe needs model_type.
    {"model_type": "chat"},
    {"model_type": "all"},
    # Maybe needs version.
    {"version": "3.3.76"},
    # Maybe needs all fields.
    {"function": "chat", "agent_type": "solo_agent_lite"},
    {"scene": "chat", "agent_type": "solo_agent_lite"},
    # Empty / all.
    {},
    {"all": True},
    {"page_size": 100},
]


def main() -> int:
    print("=" * 60)
    print("TRAE model_list 参数探测")
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

    path = "/api/ide/v1/model_list"
    print(f"\n[尝试 {len(PARAM_SHAPES)} 种参数组合 for {path}]")
    for body in PARAM_SHAPES:
        status, text = try_post(path, body, headers)
        snippet = text.replace("\n", " ")[:300]
        marker = "✓" if status == 200 else "~" if status > 0 else "✗"
        print(f"\n{marker} POST {path} body={body}")
        print(f"  -> {status}: {snippet}")

        if status == 200 and "model_configs" in text:
            try:
                data = json.loads(text)
                configs = data.get("model_configs", [])
                if configs:
                    print(f"\n  ✓✓✓ 找到 {len(configs)} 个模型配置 ✓✓✓")
                    names = set()
                    for c in configs:
                        name = c.get("model_name") or c.get("name") or c.get("model") or ""
                        if name:
                            names.add(name)
                        # Print full first config for structure inspection.
                    if names:
                        print(f"\n  模型名列表 ({len(names)} 个):")
                        for i, n in enumerate(sorted(names), 1):
                            print(f"  {i:2d}. {n}")
                    print(f"\n  第一个配置的完整结构:")
                    print(f"  {json.dumps(configs[0], ensure_ascii=False, indent=2)[:800]}")
            except json.JSONDecodeError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
