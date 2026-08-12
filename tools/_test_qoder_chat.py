"""Test chat/ask and other key methods on Qoder CN WebSocket."""
import json
import time
import uuid
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

ws = websocket.create_connection(
    "ws://127.0.0.1:36510/ws",
    header={"Cosy-MachineToken": MACHINE_TOKEN},
    suppress_origin=True,
    timeout=10,
)
print("[+] Connected!")

def send_rpc(method: str, params: dict = None, timeout: float = 5.0, label: str = ""):
    msg = {"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8], "method": method}
    if params is not None:
        msg["params"] = params
    raw = json.dumps(msg)
    ws.send(raw)
    ws.settimeout(timeout)
    try:
        result = ws.recv()
        if result.startswith("Content-Length:"):
            parts = result.split("\n\n", 1)
            if len(parts) == 2:
                try:
                    resp = json.loads(parts[1])
                    return resp
                except json.JSONDecodeError:
                    return parts[1]
        return result
    except Exception as e:
        return f"TIMEOUT/ERROR: {e}"

# 1. Initialize
print("\n=== 1. initialize ===")
resp = send_rpc("initialize", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:500] if isinstance(resp, dict) else str(resp)[:500]}")

# 2. auth/status
print("\n=== 2. auth/status ===")
resp = send_rpc("auth/status", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 3. config/queryModels
print("\n=== 3. config/queryModels ===")
resp = send_rpc("config/queryModels", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 4. model/queryClasses
print("\n=== 4. model/queryClasses ===")
resp = send_rpc("model/queryClasses", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 5. session/getCurrent
print("\n=== 5. session/getCurrent ===")
resp = send_rpc("session/getCurrent", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 6. chat/listAllSessions
print("\n=== 6. chat/listAllSessions ===")
resp = send_rpc("chat/listAllSessions", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 7. chat/ask with minimal params
print("\n=== 7. chat/ask (minimal) ===")
chat_params = {
    "query": "say hello in 3 words",
    "mode": "agent",
}
resp = send_rpc("chat/ask", chat_params, timeout=15)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:1000] if isinstance(resp, dict) else str(resp)[:1000]}")

# 8. session/prompt
print("\n=== 8. session/prompt ===")
resp = send_rpc("session/prompt", {"query": "say hello"}, timeout=10)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 9. session/addUserMessage
print("\n=== 9. session/addUserMessage ===")
resp = send_rpc("session/addUserMessage", {"content": "hello"}, timeout=10)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 10. user/plan
print("\n=== 10. user/plan ===")
resp = send_rpc("user/plan", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

# 11. credit/usage
print("\n=== 11. credit/usage ===")
resp = send_rpc("credit/usage", {}, timeout=5)
print(f"  Result: {json.dumps(resp, ensure_ascii=False)[:800] if isinstance(resp, dict) else str(resp)[:800]}")

ws.close()
print("\n[+] Done!")
