"""Probe Qoder CN cloud gateway API (gateway.qoder.com.cn).

The Qoder CN sidecar talks to a cloud gateway. This script probes the gateway
to find an OpenAI-compatible chat completions endpoint using the machine_token.

Known from cache.json:
  gateway: https://gateway.qoder.com.cn
  inferNodes: https://api3.qoder.sh (umid region 3)
  nesNodes: https://api5.qoder.com.cn
  openapiNodes: https://openapi.qoder.sh

Known from main.log update URL:
  openapi.qoder.com.cn  (CN region openapi)
  lingma-api.tongyi.aliyun.com  (update server)

Known from sharedprocess.log:
  https://openapi.qoder.com.cn/api/v1/qcs/config/stream?ns=qoder-feature-gates

Known models: auto, qmodel_38max, qmodel_latest, qmodel, q36fmodel, dmodel,
              dfmodel, gm51model, kmodel, mmodel
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error

# Auth material.
MACHINE_TOKEN = "P1gATBmn3chlyQHqjAnVqs1k3SEM--aIm5D8vG1fl_nc5UVUsujXKzLQa3SvYYS0v7zjEIIOrsnWUtKw0ktH1c0c"
MACHINE_ID = "e9de1011-6113-443d-bebc-577da74ad439"
CLIENT_ID = "32633433-3830-452d-b964-38773a34332d"
USER_ID = "019feeea-2bf1-7531-afa0-199437a81a16"

# Candidate gateways / hosts.
HOSTS = [
    "https://gateway.qoder.com.cn",
    "https://openapi.qoder.com.cn",
    "https://api5.qoder.com.cn",
]

# Candidate endpoint paths.
PATHS = [
    "/api/v1/qcs/config/stream?ns=qoder-feature-gates",
    "/api/v1/models",
    "/api/v1/chat/completions",
    "/v1/models",
    "/v1/chat/completions",
    "/api/v1/ping",
    "/api/v1/user/info",
    "/api/v1/user/me",
    "/api/v1/auth/verify",
    "/api/v1/credits",
    "/api/v1/credit/usage",
    "/api/v1/quota",
    "/api/v1/agent/chat",
    "/api/v1/inference/chat",
    "/api/v1/inference/completions",
]


def probe(host: str, path: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, str, dict]:
    url = f"{host}{path}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "QoderCN/1.23.0 PA-Agent-Probe/1.0",
        "Content-Type": "application/json",
        # Try several auth header styles.
        "Authorization": f"Bearer {MACHINE_TOKEN}",
        "x-machine-token": MACHINE_TOKEN,
        "x-umid": MACHINE_TOKEN,
        "x-machine-id": MACHINE_ID,
        "x-client-id": CLIENT_ID,
        "x-user-id": USER_ID,
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body_text = resp.read().decode("utf-8", errors="replace")
            return resp.status, body_text[:500], dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        return exc.code, body_text, dict(exc.headers) if hasattr(exc, "headers") else {}
    except urllib.error.URLError as exc:
        return -1, f"URLError: {exc}", {}
    except Exception as exc:
        return -2, f"{type(exc).__name__}: {exc}", {}


def main() -> int:
    print("=" * 70)
    print("Qoder CN cloud gateway probe")
    print(f"  machine_token length: {len(MACHINE_TOKEN)}")
    print("=" * 70)

    for host in HOSTS:
        print(f"\n[Host: {host}]")
        for path in PATHS:
            status, body, _ = probe(host, path)
            snippet = body.replace("\n", " ")[:120]
            marker = "✓" if status == 200 else ("~" if status > 0 else "✗")
            print(f"  {marker} GET  {path:50s} -> {status}  {snippet}")

    # Try POST chat on the most likely hosts/paths.
    print("\n[Chat completions POST probes]")
    chat_body = {
        "model": "auto",
        "messages": [{"role": "user", "content": "用中文说一句你好"}],
        "stream": False,
    }
    chat_paths = [
        "/api/v1/chat/completions",
        "/v1/chat/completions",
        "/api/v1/inference/chat",
        "/api/v1/agent/chat",
    ]
    for host in HOSTS:
        for path in chat_paths:
            status, body, _ = probe(host, path, method="POST", body=chat_body)
            snippet = body.replace("\n", " ")[:200]
            marker = "✓" if status == 200 else ("~" if status > 0 else "✗")
            print(f"  {marker} POST {host}{path:35s} -> {status}  {snippet}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
