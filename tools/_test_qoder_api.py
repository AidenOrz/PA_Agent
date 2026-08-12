"""Probe Qoder CN cloud API: https://lingma-api.tongyi.aliyun.com/algo/api/v1/...

Uses Cosy-MachineToken header for auth (extracted from machine_token.json).
"""
import json
import sys
import time
import uuid
import urllib.request
import urllib.error

# Read machine_token from cache
TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    token_data = json.load(f)
MACHINE_TOKEN = token_data["token"]
print(f"[+] machine_token: {MACHINE_TOKEN[:30]}... (len={len(MACHINE_TOKEN)})")

BASE = "https://lingma-api.tongyi.aliyun.com/algo/api/v1"
HEADERS = {
    "Content-Type": "application/json",
    "Cosy-MachineToken": MACHINE_TOKEN,
    "Cosy-Version": "1.23.0",
    "X-Request-ID": str(uuid.uuid4()),
    "User-Agent": "qoder-cn/1.23.0",
}


def try_get(path: str, timeout: float = 10.0) -> tuple[int, str]:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")[:1500]
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:1500]
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return -1, str(e)


def try_post(path: str, body: dict, timeout: float = 30.0, extra_headers: dict | None = None) -> tuple[int, str]:
    url = f"{BASE}{path}"
    h = dict(HEADERS)
    if extra_headers:
        h.update(extra_headers)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")[:2500]
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:2500]
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return -1, str(e)


print("\n=== 1. GET /ping ===")
code, body = try_get("/ping")
print(f"HTTP {code}\n{body}\n")

print("=== 2. GET /version ===")
code, body = try_get("/version")
print(f"HTTP {code}\n{body}\n")

print("=== 3. GET /organizations ===")
code, body = try_get("/organizations")
print(f"HTTP {code}\n{body}\n")

print("=== 4. POST /chat/completions (model=auto) ===")
body_req = {
    "model": "auto",
    "messages": [{"role": "user", "content": "say hi in 3 words"}],
    "stream": False,
}
code, body = try_post("/chat/completions", body_req)
print(f"HTTP {code}\n{body}\n")

print("=== 5. POST /chat/completions (model=qwen-max) ===")
body_req = {
    "model": "qwen-max",
    "messages": [{"role": "user", "content": "say hi in 3 words"}],
    "stream": False,
}
code, body = try_post("/chat/completions", body_req)
print(f"HTTP {code}\n{body}\n")

print("=== 6. POST /chat/completions (with X-Model-Name=auto header) ===")
body_req = {
    "messages": [{"role": "user", "content": "say hi in 3 words"}],
    "stream": False,
}
code, body = try_post("/chat/completions", body_req, extra_headers={"X-Model-Name": "auto"})
print(f"HTTP {code}\n{body}\n")
