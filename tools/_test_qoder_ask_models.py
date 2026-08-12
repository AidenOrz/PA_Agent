"""Ask Qoder CN what models are available."""
import json
import time
import uuid
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


def recv_all(ws, timeout=60.0, idle_gap=8.0):
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
        except Exception as e:
            print(f"  [recv error] {e}")
            break
    return messages


ws = websocket.create_connection(
    "ws://127.0.0.1:36510/ws",
    header={"Cosy-MachineToken": MACHINE_TOKEN},
    suppress_origin=True,
    timeout=15,
)
send_lsp(ws, "initialize", {}, id_="init")
_ = recv_all(ws, timeout=3)

request_id = str(uuid.uuid4())
chat_params = {
    "sessionId": "",
    "requestId": request_id,
    "questionText": "请列出你当前所有可用的模型名称(key)和显示名称(displayName)，包括推理模型和非推理模型。只输出列表，不要其他内容。",
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
        "text": "请列出你当前所有可用的模型名称(key)和显示名称(displayName)，包括推理模型和非推理模型。只输出列表，不要其他内容。",
        "localeLang": "zh-cn",
        "preferredLanguage": "zh-cn",
    },
    "extra": {
        "modelConfig": {
            "key": "auto",
        },
    },
}

print(f"Sending chat/ask with model=auto...")
send_lsp(ws, "chat/ask", chat_params, id_="chat-1")
msgs = recv_all(ws, timeout=90, idle_gap=10)

content_parts = []
for m in msgs:
    method = m.get("method", "")
    params = m.get("params", {})
    if method == "chat/answer":
        text = str(params.get("text", ""))
        if text:
            content_parts.append(text)
    elif method == "chat/finish":
        print(f"[finish] reason={params.get('reason')}, status={params.get('statusCode')}")

content = "".join(content_parts)
# Strip thinking markers
import re
content = re.sub(r"````think::\{THINK_TIME\}.*?````", "", content, flags=re.DOTALL)
print(f"\n=== Qoder CN Response (model=auto) ===\n{content.strip()}")
ws.close()
