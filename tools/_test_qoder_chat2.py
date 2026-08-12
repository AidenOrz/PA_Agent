"""Test chat/ask with proper LSP Content-Length framing."""
import json
import time
import uuid
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

def fresh_conn():
    return websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={"Cosy-MachineToken": MACHINE_TOKEN},
        suppress_origin=True,
        timeout=15,
    )

def send_lsp(ws, method: str, params=None, timeout: float = 10.0):
    """Send with LSP Content-Length framing."""
    msg = {"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8], "method": method}
    if params is not None:
        msg["params"] = params
    raw = json.dumps(msg)
    framed = f"Content-Length: {len(raw)}\r\n\r\n{raw}"
    ws.send(framed)
    ws.settimeout(timeout)
    try:
        result = ws.recv()
        if result.startswith("Content-Length:"):
            parts = result.split("\r\n\r\n", 1)
            if len(parts) == 2:
                return json.loads(parts[1])
            parts = result.split("\n\n", 1)
            if len(parts) == 2:
                return json.loads(parts[1])
        return result
    except Exception as e:
        return f"ERR: {e}"

# Fresh connection for each test to avoid stale state
tests = [
    ("initialize", {}, 5),
    ("ping", {}, 5),
    ("auth/status", {}, 10),
    ("config/queryModels", {}, 10),
    ("model/queryClasses", {}, 10),
    ("session/getCurrent", {}, 10),
    ("chat/listAllSessions", {}, 10),
    ("user/plan", {}, 10),
    ("credit/usage", {}, 10),
]

for method, params, timeout in tests:
    print(f"\n=== {method} ===")
    try:
        ws = fresh_conn()
        resp = send_lsp(ws, method, params, timeout=timeout)
        if isinstance(resp, dict):
            print(f"  {json.dumps(resp, ensure_ascii=False)[:600]}")
        else:
            print(f"  {str(resp)[:600]}")
        ws.close()
    except Exception as e:
        print(f"  Connection error: {e}")
    time.sleep(0.5)

# Test chat/ask separately with longer timeout
print("\n\n=== chat/ask (with longer timeout) ===")
try:
    ws = fresh_conn()
    # First initialize
    resp = send_lsp(ws, "initialize", {}, timeout=5)
    print(f"  init: {json.dumps(resp, ensure_ascii=False)[:200] if isinstance(resp, dict) else str(resp)[:200]}")
    
    # Then chat/ask
    chat_params = {
        "query": "say hello",
        "mode": "agent",
    }
    resp = send_lsp(ws, "chat/ask", chat_params, timeout=30)
    if isinstance(resp, dict):
        print(f"  chat/ask: {json.dumps(resp, ensure_ascii=False)[:1000]}")
    else:
        print(f"  chat/ask: {str(resp)[:1000]}")
    ws.close()
except Exception as e:
    print(f"  Error: {e}")

# Test session/prompt
print("\n\n=== session/prompt ===")
try:
    ws = fresh_conn()
    resp = send_lsp(ws, "initialize", {}, timeout=5)
    print(f"  init: {json.dumps(resp, ensure_ascii=False)[:200] if isinstance(resp, dict) else str(resp)[:200]}")
    
    resp = send_lsp(ws, "session/prompt", {"query": "say hello"}, timeout=30)
    if isinstance(resp, dict):
        print(f"  session/prompt: {json.dumps(resp, ensure_ascii=False)[:1000]}")
    else:
        print(f"  session/prompt: {str(resp)[:1000]}")
    ws.close()
except Exception as e:
    print(f"  Error: {e}")
