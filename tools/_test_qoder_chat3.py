"""Test chat/ask and listen for streaming notifications."""
import json
import time
import uuid
import threading
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]


def make_ws():
    return websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={"Cosy-MachineToken": MACHINE_TOKEN},
        suppress_origin=True,
        timeout=15,
    )


def send_lsp(ws, method: str, params=None, id_: str = None):
    msg = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        msg["id"] = id_
    if params is not None:
        msg["params"] = params
    raw = json.dumps(msg)
    framed = f"Content-Length: {len(raw)}\r\n\r\n{raw}"
    ws.send(framed)


def parse_lsp_messages(data: str):
    """Parse one or more LSP-framed JSON-RPC messages from a buffer."""
    out = []
    rest = data
    while True:
        # Find Content-Length header
        idx = rest.find("Content-Length:")
        if idx < 0:
            break
        rest = rest[idx:]
        # Parse header
        end = rest.find("\r\n\r\n")
        if end < 0:
            # Try \n\n
            end = rest.find("\n\n")
            if end < 0:
                break
            header = rest[:end]
            body_start = end + 2
        else:
            header = rest[:end]
            body_start = end + 4
        # Extract length
        try:
            length = int(header.split("Content-Length:")[1].strip().split("\n")[0].strip())
        except Exception:
            break
        body = rest[body_start:body_start + length]
        if len(body) < length:
            break  # incomplete
        try:
            out.append(json.loads(body))
        except Exception as e:
            print(f"  [parse error] {e}: {body[:200]}")
        rest = rest[body_start + length:]
    return out


def recv_all(ws, timeout: float = 30.0, idle_gap: float = 2.0):
    """Receive all messages until timeout or idle gap."""
    messages = []
    deadline = time.time() + timeout
    ws.settimeout(0.5)
    last_recv = time.time()
    while time.time() < deadline:
        try:
            data = ws.recv()
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            last_recv = time.time()
            parsed = parse_lsp_messages(data)
            for m in parsed:
                messages.append(m)
                # Reset idle timer when we get messages
                deadline = max(deadline, time.time() + idle_gap)
        except websocket.WebSocketTimeoutException:
            if messages and time.time() - last_recv > idle_gap:
                break
            continue
        except Exception as e:
            print(f"  [recv error] {e}")
            break
    return messages


# Step 1: Get full model list
print("=" * 60)
print("STEP 1: Get full model list")
print("=" * 60)
ws = make_ws()
send_lsp(ws, "initialize", {}, id_="init-1")
time.sleep(0.5)
send_lsp(ws, "config/queryModels", {}, id_="models-1")
time.sleep(2)
msgs = recv_all(ws, timeout=5)
for m in msgs:
    if m.get("id") == "models-1" and "result" in m:
        result = m["result"]
        for cat in ["assistant", "chat", "reasoning", "completion"]:
            if cat in result:
                print(f"\n[{cat}]")
                for model in result[cat]:
                    print(f"  - key={model.get('key')}, name={model.get('displayName')}, "
                          f"reasoning={model.get('isReasoning')}, default={model.get('isDefault')}")
ws.close()

# Step 2: Try chat/ask and listen for streaming events
print("\n" + "=" * 60)
print("STEP 2: chat/ask + listen for streaming notifications")
print("=" * 60)
ws = make_ws()
send_lsp(ws, "initialize", {}, id_="init-2")
time.sleep(0.5)

# Try chat/ask with different param shapes
chat_id = "chat-" + uuid.uuid4().hex[:6]
chat_params = {
    "query": "Reply with exactly: hello world",
    "mode": "agent",
    "model": "auto",
}
print(f"\nSending chat/ask with id={chat_id}")
send_lsp(ws, "chat/ask", chat_params, id_=chat_id)

# Listen for streaming events
print("Listening for streaming events (30s)...")
msgs = recv_all(ws, timeout=30, idle_gap=3)
print(f"\nReceived {len(msgs)} messages:")
for i, m in enumerate(msgs):
    method = m.get("method", "(response)")
    id_ = m.get("id", "-")
    s = json.dumps(m, ensure_ascii=False)
    if len(s) > 400:
        s = s[:400] + "..."
    print(f"  [{i}] method={method} id={id_}: {s}")
ws.close()

# Step 3: Try with session/getCurrent + session/prompt pattern
print("\n" + "=" * 60)
print("STEP 3: Try session/prompt with requestId")
print("=" * 60)
ws = make_ws()
send_lsp(ws, "initialize", {}, id_="init-3")
time.sleep(0.5)

req_id = "req-" + uuid.uuid4().hex[:8]
prompt_params = {
    "requestId": req_id,
    "query": "Reply with exactly: hello world",
    "model": "auto",
}
print(f"\nSending session/prompt with requestId={req_id}")
send_lsp(ws, "session/prompt", prompt_params, id_="prompt-3")

print("Listening for streaming events (30s)...")
msgs = recv_all(ws, timeout=30, idle_gap=3)
print(f"\nReceived {len(msgs)} messages:")
for i, m in enumerate(msgs):
    method = m.get("method", "(response)")
    id_ = m.get("id", "-")
    s = json.dumps(m, ensure_ascii=False)
    if len(s) > 400:
        s = s[:400] + "..."
    print(f"  [{i}] method={method} id={id_}: {s}")
ws.close()
