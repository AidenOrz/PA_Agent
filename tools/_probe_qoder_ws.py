"""Probe Qoder CN sidecar WebSocket on port 36510.

The binary shows:
- ws://%s/ws format string (path is /ws)
- JSON-RPC 2.0 protocol
- HandleWebViewWebSocketLoginWithPersonalTokenRequest (auth via personal token)
- Sec-WebSocket-Key header
"""
import json
import uuid
import websocket  # websocket-client library
import time

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

try:
    with open(r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\id", "r") as f:
        USER_ID = f.read().strip()
except Exception:
    USER_ID = ""

print(f"[+] machine_token: {MACHINE_TOKEN[:30]}...")
print(f"[+] user_id: {USER_ID}")

# Try different URL patterns
URLS = [
    "ws://127.0.0.1:36510/ws",
    "ws://127.0.0.1:36510/",
]

# Try different header combinations
def make_headers(auth_type: str) -> dict:
    h = {}
    if auth_type == "machine_token":
        h["Authorization"] = f"Bearer {MACHINE_TOKEN}"
    elif auth_type == "cosy":
        h["Cosy-MachineToken"] = MACHINE_TOKEN
    elif auth_type == "both":
        h["Authorization"] = f"Bearer {MACHINE_TOKEN}"
        h["Cosy-MachineToken"] = MACHINE_TOKEN
    elif auth_type == "query":
        # token in URL query param instead
        pass
    return h

# JSON-RPC methods to try
METHODS = [
    "initialize",
    "ping",
    "listModels",
    "list_models",
    "model/list",
    "chat",
    "chat.send",
    "chat/completions",
    "completion",
    "query",
    "stream",
    "broker.listSessions",
    "session.list",
    "task.list",
]

def try_connect(url: str, headers: dict, timeout: float = 3.0):
    print(f"\n--- Connecting to {url} (headers: {list(headers.keys())}) ---")
    try:
        ws = websocket.create_connection(url, header=headers, timeout=timeout)
        print(f"  [OK] Connected! Server response: {ws.recv()[:200]}")
        return ws
    except Exception as e:
        print(f"  [EXC] {e}")
        return None

def try_send_rpc(ws, method: str, params: dict = None, timeout: float = 3.0):
    req = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4())[:8],
        "method": method,
    }
    if params:
        req["params"] = params
    msg = json.dumps(req)
    try:
        ws.send(msg)
        result = ws.recv()
        return result[:500]
    except Exception as e:
        return f"EXC: {e}"

# Test 1: Try connecting with different auth to /ws
for url in URLS:
    for auth_type in ["none", "machine_token", "cosy", "both"]:
        headers = make_headers(auth_type)
        ws = try_connect(url, headers)
        if ws:
            # Try sending a ping
            for method in ["ping", "initialize", "listModels"]:
                result = try_send_rpc(ws, method)
                print(f"  [{method}] -> {result}")
            ws.close()
        time.sleep(0.3)

# Test 2: Try with token in query string
print("\n\n=== With token in query string ===")
for url_base in ["ws://127.0.0.1:36510/ws", "ws://127.0.0.1:36510/"]:
    for qparam in ["token", "machine_token", "access_token", "auth"]:
        url = f"{url_base}?{qparam}={MACHINE_TOKEN}"
        try:
            ws = websocket.create_connection(url, timeout=2)
            print(f"  [OK] {qparam}={MACHINE_TOKEN[:15]}...: Connected!")
            result = ws.recv()
            print(f"    Initial: {result[:200]}")
            ws.close()
        except Exception as e:
            err = str(e)[:120]
            print(f"  [ERR] {qparam}: {err}")
