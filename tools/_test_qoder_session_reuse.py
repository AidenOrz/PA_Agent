"""Test Qoder CN: pre-create session, then reuse it for chat/ask."""
import json
import time
import uuid
import re
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]


def send_lsp(ws, method, params=None, id_=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        msg["id"] = id_
    if params is not None:
        msg["params"] = params
    raw = json.dumps(msg)
    ws.send(f"Content-Length: {len(raw)}\r\n\r\n{raw}")


def parse_lsp_messages(data):
    out = []
    rest = data
    while True:
        idx = rest.find("Content-Length:")
        if idx < 0:
            stripped = rest.strip()
            if stripped and stripped.startswith("{"):
                try:
                    out.append(json.loads(stripped))
                except Exception:
                    pass
            break
        rest = rest[idx:]
        end = rest.find("\r\n\r\n")
        if end < 0:
            end = rest.find("\n\n")
            if end < 0:
                break
            body_start = end + 2
        else:
            body_start = end + 4
        try:
            length = int(rest.split("Content-Length:")[1].strip().split("\n")[0].strip())
        except Exception:
            break
        body = rest[body_start:body_start + length]
        if len(body) < length:
            break
        try:
            out.append(json.loads(body))
        except Exception:
            pass
        rest = rest[body_start + length:]
    return out


def recv_all(ws, timeout=30, idle_gap=5):
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
            for m in parse_lsp_messages(data):
                messages.append(m)
        except websocket.WebSocketTimeoutException:
            if messages and time.time() - last_recv > idle_gap:
                break
            continue
        except Exception:
            break
    return messages


# Step 1: Try session/new to get a session ID
print("=" * 60)
print("STEP 1: session/new")
print("=" * 60)
ws = websocket.create_connection(
    "ws://127.0.0.1:36510/ws",
    header={"Cosy-MachineToken": MACHINE_TOKEN},
    suppress_origin=True,
    timeout=15,
)
send_lsp(ws, "initialize", {}, id_="init")
_ = recv_all(ws, timeout=3)

# Try session/new with minimal params
send_lsp(ws, "session/new", {
    "sessionType": "assistant",
    "mode": "chat",
}, id_="session-new")
msgs = recv_all(ws, timeout=15)
session_id = None
for m in msgs:
    s = json.dumps(m, ensure_ascii=False)
    if len(s) > 500:
        s = s[:500] + "..."
    print(f"  {s}")
    if m.get("id") == "session-new":
        result = m.get("result", {})
        if isinstance(result, dict):
            session_id = result.get("sessionId") or result.get("id") or result.get("session_id")
            if not session_id and "sessionId" in result:
                session_id = result["sessionId"]
print(f"\n  session_id: {session_id}")

# Step 2: If we have a session, try chat/ask with that session
if session_id:
    print(f"\n{'='*60}")
    print(f"STEP 2: chat/ask with sessionId={session_id}")
    print(f"{'='*60}")

    request_id = str(uuid.uuid4())
    chat_params = {
        "sessionId": session_id,
        "requestId": request_id,
        "questionText": "Reply with exactly: hi",
        "mode": "chat",
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
            "text": "Reply with exactly: hi",
            "localeLang": "zh-cn",
            "preferredLanguage": "zh-cn",
        },
        "extra": {
            "modelConfig": {
                "key": "mmodel",
            },
        },
    }

    t_start = time.monotonic()
    send_lsp(ws, "chat/ask", chat_params, id_="chat-1")
    msgs = recv_all(ws, timeout=60, idle_gap=8)
    t_end = time.monotonic()

    content_parts = []
    for m in msgs:
        method = m.get("method", "")
        params = m.get("params", {})
        if method == "chat/answer":
            text = str(params.get("text", ""))
            if text:
                content_parts.append(text)
        elif method == "chat/finish":
            print(f"  finish: {params}")

    content = "".join(content_parts)
    content = re.sub(r"````think::\{THINK_TIME\}.*?````", "", content, flags=re.DOTALL).strip()
    print(f"\n  content: {content!r}")
    print(f"  total_time: {t_end - t_start:.2f}s")

    # Step 3: Reuse same session for second question
    print(f"\n{'='*60}")
    print(f"STEP 3: Reuse session for second question")
    print(f"{'='*60}")

    request_id2 = str(uuid.uuid4())
    chat_params2 = dict(chat_params)
    chat_params2["requestId"] = request_id2
    chat_params2["questionText"] = "Reply with exactly: bye"
    chat_params2["chatContext"]["text"] = "Reply with exactly: bye"

    t_start2 = time.monotonic()
    send_lsp(ws, "chat/ask", chat_params2, id_="chat-2")
    msgs2 = recv_all(ws, timeout=60, idle_gap=8)
    t_end2 = time.monotonic()

    content_parts2 = []
    for m in msgs2:
        method = m.get("method", "")
        params = m.get("params", {})
        if method == "chat/answer":
            text = str(params.get("text", ""))
            if text:
                content_parts2.append(text)
        elif method == "chat/finish":
            print(f"  finish: {params}")

    content2 = "".join(content_parts2)
    content2 = re.sub(r"````think::\{THINK_TIME\}.*?````", "", content2, flags=re.DOTALL).strip()
    print(f"\n  content: {content2!r}")
    print(f"  total_time: {t_end2 - t_start2:.2f}s")

    print(f"\n{'='*60}")
    print(f"COMPARISON:")
    print(f"  First call (new session):  {t_end - t_start:.2f}s")
    print(f"  Second call (reuse):       {t_end2 - t_start2:.2f}s")
else:
    print("\n  No session_id obtained. Testing chat/ask without session reuse.")

ws.close()
