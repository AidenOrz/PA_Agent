"""Test Qoder CN actual endpoints: gateway.qoder.com.cn and qts.qoder.com.cn."""
import json
import uuid
import urllib.request
import urllib.error

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

print(f"[+] machine_token: {MACHINE_TOKEN[:30]}... (len={len(MACHINE_TOKEN)})")

HOSTS = [
    "https://gateway.qoder.com.cn",
    "https://qts.qoder.com.cn",
]

HEADERS = {
    "Content-Type": "application/json",
    "Cosy-MachineToken": MACHINE_TOKEN,
    "Cosy-Version": "1.23.0",
    "X-Request-ID": str(uuid.uuid4()),
    "User-Agent": "qoder-cn/1.23.0",
}

GET_PATHS = [
    "/algo/api/v1/ping",
    "/api/v2/model/list",
    "/api/v2/quota/usage",
    "/api/v2/user/plan",
    "/api/v1/userinfo",
    "/api/v2/remoteAgent/qoder/sessions/",
]

POST_CHAT_PATHS = [
    "/algo/chat/completions",
    "/algo/api/v1/chat/completions",
    "/algo/api/v2/chat/completions",
]

chat_body = {
    "model": "auto",
    "messages": [{"role": "user", "content": "say hi in 3 words"}],
    "stream": False,
}

for host in HOSTS:
    print(f"\n========== Host: {host} ==========")
    print("--- GET tests ---")
    for p in GET_PATHS:
        url = f"{host}{p}"
        req = urllib.request.Request(url, headers=HEADERS, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:400]
                print(f"  [OK  {resp.status}] {p}: {body[:300]}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                body = ""
            print(f"  [ERR {e.code}] {p}: {body}")
        except Exception as e:
            print(f"  [EXC    ] {p}: {e}")

    print("\n--- POST chat tests ---")
    for p in POST_CHAT_PATHS:
        url = f"{host}{p}"
        data = json.dumps(chat_body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:600]
                print(f"  [OK  {resp.status}] {p}: {body[:500]}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                body = ""
            print(f"  [ERR {e.code}] {p}: {body}")
        except Exception as e:
            print(f"  [EXC    ] {p}: {e}")
