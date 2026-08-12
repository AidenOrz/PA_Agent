"""Test chat/ask with correct parameter structure and listen for session/update notifications."""
import json
import time
import uuid
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
        idx = rest.find("Content-Length:")
        if idx < 0:
            # Also try without Content-Length (some messages might be raw JSON)
            stripped = rest.strip()
            if stripped and stripped.startswith("{"):
                try:
                    out.append(json.loads(stripped))
                    break
                except Exception:
                    pass
            break
        rest = rest[idx:]
        end = rest.find("\r\n\r\n")
        if end < 0:
            end = rest.find("\n\n")
            if end < 0:
                break
            header = rest[:end]
            body_start = end + 2
        else:
            header = rest[:end]
            body_start = end + 4
        try:
            length = int(header.split("Content-Length:")[1].strip().split("\n")[0].strip())
        except Exception:
            break
        body = rest[body_start:body_start + length]
        if len(body) < length:
            break
        try:
            out.append(json.loads(body))
        except Exception as e:
            print(f"  [parse error] {e}: {body[:200]}")
        rest = rest[body_start + length:]
    return out


def recv_all(ws, timeout: float = 60.0, idle_gap: float = 5.0):
    """Receive all messages until timeout or idle gap after first message."""
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
        except websocket.WebSocketTimeoutException:
            if messages and time.time() - last_recv > idle_gap:
                break
            continue
        except Exception as e:
            print(f"  [recv error] {e}")
            break
    return messages


# ====== Step 1: Get full model list (with longer wait) ======
print("=" * 60)
print("STEP 1: Get full model list")
print("=" * 60)
ws = make_ws()
send_lsp(ws, "initialize", {}, id_="init-1")
msgs = recv_all(ws, timeout=5)
send_lsp(ws, "config/queryModels", {}, id_="models-1")
msgs = recv_all(ws, timeout=10)
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

# ====== Step 2: chat/ask with correct params ======
print("\n" + "=" * 60)
print("STEP 2: chat/ask with correct params + listen for session/update")
print("=" * 60)
ws = make_ws()
send_lsp(ws, "initialize", {}, id_="init-2")
time.sleep(1)
# Drain init response
_ = recv_all(ws, timeout=2)

request_id = str(uuid.uuid4())
chat_params = {
    "sessionId": "",
    "requestId": request_id,
    "questionText": "Reply with exactly these words: hello world",
    "mode": "agent",
    "sessionType": "assistant",
    "chatTask": "free_input",
    "stream": True,
    "source": 1,
    "isReply": False,
    "taskDefinitionType": "system",
    "shellType": "",
    "codeLanguage": "",
    "preferredLanguage": "zh-cn",
    "closeTypewriter": True,
    "pluginPayloadConfig": {},
    "chatContext": {
        "text": "Reply with exactly these words: hello world",
        "localeLang": "zh-cn",
        "preferredLanguage": "zh-cn",
    },
    "extra": {
        "modelConfig": {
            "key": "auto",
        },
    },
}

print(f"\nSending chat/ask with requestId={request_id}")
send_lsp(ws, "chat/ask", chat_params, id_="chat-2")

print("Listening for all messages (60s, idle_gap=8s)...")
msgs = recv_all(ws, timeout=60, idle_gap=8)
print(f"\nReceived {len(msgs)} messages:")
for i, m in enumerate(msgs):
    method = m.get("method", "(response)")
    id_ = m.get("id", "-")
    s = json.dumps(m, ensure_ascii=False)
    if len(s) > 500:
        s = s[:500] + "..."
    print(f"  [{i}] method={method} id={id_}: {s}")
ws.close()

# ====== Step 3: Try with a model key ======
print("\n" + "=" * 60)
print("STEP 3: chat/ask with model=qmodel_38max")
print("=" * 60)
ws = make_ws()
send_lsp(ws, "initialize", {}, id_="init-3")
time.sleep(1)
_ = recv_all(ws, timeout=2)

request_id = str(uuid.uuid4())
chat_params2 = dict(chat_params)
chat_params2["requestId"] = request_id
chat_params2["extra"] = {"modelConfig": {"key": "qmodel_38max"}}

print(f"\nSending chat/ask with requestId={request_id}, model=qmodel_38max")
send_lsp(ws, "chat/ask", chat_params2, id_="chat-3")

print("Listening for all messages (60s, idle_gap=8s)...")
msgs = recv_all(ws, timeout=60, idle_gap=8)
print(f"\nReceived {len(msgs)} messages:")
for i, m in enumerate(msgs):
    method = m.get("method", "(response)")
    id_ = m.get("id", "-")
    s = json.dumps(m, ensure_ascii=False)
    if len(s) > 500:
        s = s[:500] + "..."
    print(f"  [{i}] method={method} id={id_}: {s}")
ws.close()
