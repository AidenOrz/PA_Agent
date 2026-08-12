"""Test different Qoder CN API path variations.

Confirmed: /algo/api/v1/ping works (200 pong). /algo prefix is stripped by gateway.
Trying: /algo/chat/completions, /algo/api/v2/*, etc.
"""
import json
import uuid
import urllib.request
import urllib.error

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

HOSTS = [
    "https://lingma-api.tongyi.aliyun.com",
]
PATHS_GET = [
    "/algo/api/v1/ping",
    "/algo/api/v2/model/list",
    "/algo/api/v2/quota/usage",
    "/algo/api/v2/user/plan",
    "/algo/api/v1/version",
    "/algo/api/v1/organizations",
    "/algo/api/v1/model/list",
]
PATHS_POST_CHAT = [
    "/algo/chat/completions",
    "/algo/api/v1/chat/completions",
    "/algo/api/v2/chat/completions",
    "/algo/v1/chat/completions",
    "/algo/api/chat/completions",
    "/algo/api/v1/chat/answer",
    "/algo/api/v2/chat/answer",
]

HEADERS = {
    "Content-Type": "application/json",
    "Cosy-MachineToken": MACHINE_TOKEN,
    "Cosy-Version": "1.23.0",
    "X-Request-ID": str(uuid.uuid4()),
    "User-Agent": "qoder-cn/1.23.0",
}

chat_body = {
    "model": "auto",
    "messages": [{"role": "user", "content": "say hi in 3 words"}],
    "stream": False,
}

for host in HOSTS:
    print(f"\n========== Host: {host} ==========")
    print("--- GET tests ---")
    for p in PATHS_GET:
        url = f"{host}{p}"
        req = urllib.request.Request(url, headers=HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:300]
                print(f"  [OK  {resp.status}] {p}: {body[:200]}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                body = ""
            print(f"  [ERR {e.code}] {p}: {body}")
        except Exception as e:
            print(f"  [EXC    ] {p}: {e}")

    print("\n--- POST chat tests ---")
    for p in PATHS_POST_CHAT:
        url = f"{host}{p}"
        data = json.dumps(chat_body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                print(f"  [OK  {resp.status}] {p}: {body[:400]}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                body = ""
            print(f"  [ERR {e.code}] {p}: {body}")
        except Exception as e:
            print(f"  [EXC    ] {p}: {e}")
