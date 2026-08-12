"""Qoder CN sidecar uses HTTP (not WebSocket) on port 36510.

The 'websocket' connection actually returned an HTTP response:
  Content-Length: 1964
  {"jsonrpc":"2.0","method":"extension/register","params":...}

Let's try plain HTTP GET/POST to /ws and other paths.
"""
import json
import uuid
import urllib.request
import urllib.error

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

HOST = "http://127.0.0.1:36510"
HEADERS = {
    "Content-Type": "application/json",
    "Cosy-MachineToken": MACHINE_TOKEN,
    "Cosy-Version": "1.23.0",
    "X-Request-ID": str(uuid.uuid4()),
    "User-Agent": "qoder-cn/1.23.0",
}

PATHS_GET = ["/", "/ws", "/ping", "/health", "/api", "/status", "/v1", "/v2"]
PATHS_POST = ["/", "/ws", "/ping", "/chat", "/chat/completions", "/api/chat", "/rpc", "/jsonrpc"]

print("=== GET tests ===")
for p in PATHS_GET:
    url = f"{HOST}{p}"
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:600]
            print(f"\n[OK {resp.status}] GET {p}")
            print(f"  Headers: {dict(resp.headers)}")
            print(f"  Body: {body[:500]}")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            body = ""
        print(f"\n[ERR {e.code}] GET {p}: {body}")
    except Exception as e:
        print(f"\n[EXC] GET {p}: {str(e)[:200]}")

print("\n\n=== POST tests (JSON-RPC) ===")
RPC_METHODS = [
    "ping",
    "initialize",
    "listModels",
    "extension/listCommands",
    "chat.listModels",
    "broker.listSessions",
]

for method in RPC_METHODS:
    body_req = {"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8], "method": method}
    for p in ["/ws", "/"]:
        url = f"{HOST}{p}"
        data = json.dumps(body_req).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:600]
                print(f"\n[OK {resp.status}] POST {p} method={method}")
                print(f"  Body: {body[:500]}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                body = ""
            print(f"\n[ERR {e.code}] POST {p} method={method}: {body}")
        except Exception as e:
            print(f"\n[EXC] POST {p} method={method}: {str(e)[:200]}")
