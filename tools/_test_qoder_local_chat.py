"""Test Qoder CN sidecar HTTP API with /chat/completions (no v1 prefix).

Discovered from QoderCN.exe binary scan:
  * Endpoint path: /chat/completions  (no /v1/ prefix)
  * Auth headers: Cosy-Key, Cosy-Date, Cosy-User, Cosy-Version,
                 Cosy-MachineId, Cosy-MachineOS, Cosy-MachineType,
                 Cosy-MachineCode, Cosy-MachineToken, Cosy-ClientType,
                 Cosy-ClientIp, Cosy-Organization-Id, Cosy-Data-Policy
  * Signature: MD5 HMAC over base64(payload), Cosy-Key, Cosy-Date, body

The local sidecar may not require signature verification when called via
127.0.0.1 (since it's the same machine). Let's test that hypothesis.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error

HTTP_PORT = 37510

MACHINE_TOKEN = "P1gATBmn3chlyQHqjAnVqs1k3SEM--aIm5D8vG1fl_nc5UVUsujXKzLQa3SvYYS0v7zjEIIOrsnWUtKw0ktH1c0c"
MACHINE_ID = "e9de1011-6113-443d-bebc-577da74ad439"
MACHINE_CODE = "cbd4713b795bcbb609"
CLIENT_ID = "32633433-3830-452d-b964-38773a34332d"
USER_ID = "019feeea-2bf1-7531-afa0-199437a81a16"

CANDIDATE_PATHS = [
    "/chat/completions",
    "/api/chat/completions",
    "/api/v1/chat/completions",
    "/v1/chat/completions",
    "/inference/chat/completions",
    "/openai/chat/completions",
    "/proxy/chat/completions",
    "/llm/chat/completions",
    "/cosy/chat/completions",
    "/api/chat",
    "/chat",
    "/v1/models",
    "/api/v1/models",
    "/models",
    "/api/models",
    "/auth/status",
    "/api/v1/auth/status",
    "/api/v1/userinfo",
    "/api/v1/userinfo",
    "/api/v1/quotas",
]


def build_headers() -> dict[str, str]:
    """Build the full Cosy-* header set the sidecar might check for."""
    return {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
        "User-Agent": "QoderCN/1.23.0 PA-Agent/1.0",
        "Cosy-Version": "1.23.0",
        "Cosy-ClientType": "qoder",
        "Cosy-ClientIp": "127.0.0.1",
        "Cosy-MachineId": MACHINE_ID,
        "Cosy-MachineOS": "windows",
        "Cosy-MachineType": "2d8a3be2146dc7b96e",
        "Cosy-MachineCode": MACHINE_CODE,
        "Cosy-MachineToken": MACHINE_TOKEN,
        "Cosy-Key": MACHINE_TOKEN,
        "Cosy-Date": str(int(time.time())),
        "Cosy-User": USER_ID,
        "X-Request-ID": f"pa-agent-{int(time.time()*1000)}",
        "X-Model-Name": "auto",
        "X-Model-Source": "system",
        # Also include the Authorization Bearer in case that works.
        "Authorization": f"Bearer {MACHINE_TOKEN}",
    }


def probe(method: str, path: str, body: dict | None = None, *, timeout: float = 5.0) -> tuple[int, str]:
    url = f"http://127.0.0.1:{HTTP_PORT}{path}"
    headers = build_headers()
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_text = resp.read().decode("utf-8", errors="replace")
            return resp.status, body_text[:600]
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            pass
        return exc.code, body_text
    except Exception as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print("=" * 70)
    print("Qoder CN sidecar /chat/completions probe")
    print(f"  HTTP port: {HTTP_PORT}")
    print("=" * 70)

    # GET probes (looking for any non-404 path).
    print("\n[GET probes]")
    for path in CANDIDATE_PATHS:
        status, body = probe("GET", path)
        snippet = body.replace("\n", " ")[:120]
        marker = "✓" if status == 200 else ("~" if status > 0 and status != 404 else "✗")
        print(f"  {marker} GET  {path:35s} -> {status}  {snippet}")

    # POST probes for chat completions with various body shapes.
    print("\n[POST /chat/completions probes]")
    chat_paths = ["/chat/completions", "/api/chat/completions", "/v1/chat/completions"]
    chat_bodies = [
        # OpenAI shape.
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "用中文说一句你好"}],
            "stream": False,
        },
        # OpenAI streaming.
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "用中文说一句你好"}],
            "stream": True,
        },
        # With Cosy-style extras.
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "用中文说一句你好"}],
            "stream": True,
            "model_name": "auto",
            "user_id": USER_ID,
            "session_id": "",
        },
    ]
    for path in chat_paths:
        for i, body in enumerate(chat_bodies):
            status, body_text = probe("POST", path, body=body, timeout=10.0)
            snippet = body_text.replace("\n", " ")[:200]
            marker = "✓" if status == 200 else ("~" if status > 0 and status != 404 else "✗")
            print(f"  {marker} POST {path:35s} body{i} -> {status}  {snippet}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
