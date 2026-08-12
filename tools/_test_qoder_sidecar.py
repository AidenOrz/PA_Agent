"""Probe Qoder CN sidecar (cosy) HTTP endpoints on port 36510.

The sidecar listens on localhost:36510 (websocketPort) and exposes a
local API for the renderer. We probe common paths to find the chat endpoint.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

HOST = "http://127.0.0.1:36510"

# Credentials (for header tests).
CACHE_DIR = Path(r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache")
TOKEN = json.loads((CACHE_DIR / "machine_token.json").read_text(encoding="utf-8"))["token"]

# Candidate paths.
PATHS = [
    "/",
    "/health",
    "/healthz",
    "/v1/chat/completions",
    "/chat/completions",
    "/api/v1/chat/completions",
    "/api/chat/completions",
    "/inference",
    "/v1/models",
    "/api/v1/models",
    "/models",
    "/cosy/chat/completions",
    "/qoder/chat/completions",
    "/openai/chat/completions",
    "/v1/inference",
]


def try_get(path: str, timeout: float = 3.0) -> tuple[int, str]:
    url = f"{HOST}{path}"
    headers = {
        "Accept": "application/json, text/event-stream, */*",
        "Authorization": f"Bearer {TOKEN}",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
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


def try_post(path: str, body: dict, timeout: float = 5.0) -> tuple[int, str]:
    url = f"{HOST}{path}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream, */*",
        "Authorization": f"Bearer {TOKEN}",
    }
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
    print("Qoder CN sidecar (cosy) HTTP 探测")
    print(f"HOST: {HOST}")
    print("=" * 60)

    # 1. GET probes.
    print(f"\n[GET 探测 {len(PATHS)} 个路径]")
    for path in PATHS:
        status, text = try_get(path)
        snippet = text.replace("\n", " ")[:200]
        if status == -1:
            marker = "✗"
        elif status == 200:
            marker = "✓"
        else:
            marker = "~"
        print(f"  {marker} GET {path:<35} -> {status}: {snippet}")

    # 2. POST probes (chat completion style).
    print(f"\n[POST 探测 chat 端点]")
    chat_body = {
        "model": "auto",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": False,
    }
    for path in [
        "/v1/chat/completions",
        "/chat/completions",
        "/api/v1/chat/completions",
        "/api/chat/completions",
        "/inference",
        "/cosy/chat/completions",
        "/openai/chat/completions",
    ]:
        status, text = try_post(path, chat_body)
        snippet = text.replace("\n", " ")[:200]
        if status == -1:
            marker = "✗"
        elif status == 200:
            marker = "✓"
        else:
            marker = "~"
        print(f"  {marker} POST {path:<35} -> {status}: {snippet}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
