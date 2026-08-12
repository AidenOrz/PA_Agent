"""Try different auth methods for Qoder CN v2 API."""
import json
import uuid
import urllib.request
import urllib.error

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

# Try reading user_id
try:
    with open(r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\id", "r") as f:
        USER_ID = f.read().strip()
except Exception:
    USER_ID = ""

print(f"[+] machine_token: {MACHINE_TOKEN[:30]}... (len={len(MACHINE_TOKEN)})")
print(f"[+] user_id: {USER_ID}")

HOST = "https://gateway.qoder.com.cn"

# Test different auth header combinations
TEST_PATHS = [
    "/api/v2/model/list",
    "/api/v2/quota/usage",
    "/api/v1/userinfo",
]

AUTH_VARIANTS = [
    ("Bearer machine_token", {"Authorization": f"Bearer {MACHINE_TOKEN}"}),
    ("Cosy-MachineToken + Bearer", {"Cosy-MachineToken": MACHINE_TOKEN, "Authorization": f"Bearer {MACHINE_TOKEN}"}),
    ("X-Cosy-Token", {"X-Cosy-Token": MACHINE_TOKEN}),
    ("Cosy-Token", {"Cosy-Token": MACHINE_TOKEN}),
    ("X-Machine-Token", {"X-Machine-Token": MACHINE_TOKEN}),
    ("Authorization raw", {"Authorization": MACHINE_TOKEN}),
    ("Cosy-MachineToken + X-User-Id", {"Cosy-MachineToken": MACHINE_TOKEN, "X-User-Id": USER_ID}),
]

for auth_name, auth_headers in AUTH_VARIANTS:
    print(f"\n=== Auth: {auth_name} ===")
    headers = {
        "Content-Type": "application/json",
        "Cosy-Version": "1.23.0",
        "X-Request-ID": str(uuid.uuid4()),
        "User-Agent": "qoder-cn/1.23.0",
    }
    headers.update(auth_headers)
    for p in TEST_PATHS:
        url = f"{HOST}{p}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:250]
                print(f"  [OK  {resp.status}] {p}: {body[:200]}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                body = ""
            print(f"  [ERR {e.code}] {p}: {body}")
        except Exception as e:
            print(f"  [EXC    ] {p}: {e}")

# Try jobToken/exchange
print("\n\n=== POST /api/v1/jobToken/exchange ===")
exchange_bodies = [
    {"machineToken": MACHINE_TOKEN},
    {"machine_token": MACHINE_TOKEN},
    {"token": MACHINE_TOKEN},
    {"grantType": "machine_token", "machineToken": MACHINE_TOKEN},
]
for body_req in exchange_bodies:
    url = f"{HOST}/api/v1/jobToken/exchange"
    headers = {
        "Content-Type": "application/json",
        "Cosy-MachineToken": MACHINE_TOKEN,
        "Cosy-Version": "1.23.0",
        "X-Request-ID": str(uuid.uuid4()),
        "User-Agent": "qoder-cn/1.23.0",
    }
    data = json.dumps(body_req).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:500]
            print(f"  [OK  {resp.status}] body={json.dumps(body_req)[:80]}: {body[:400]}")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            body = ""
        print(f"  [ERR {e.code}] body={json.dumps(body_req)[:80]}: {body}")
    except Exception as e:
        print(f"  [EXC    ] body={json.dumps(body_req)[:80]}: {e}")
