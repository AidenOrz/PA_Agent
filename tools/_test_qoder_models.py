"""Query Qoder CN's available model list - using chat4's working approach."""
import json
import time
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


def recv_all(ws, timeout=60.0, idle_gap=5.0):
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
send_lsp(ws, "initialize", {}, id_="init-1")
msgs = recv_all(ws, timeout=5)
print(f"[init] received {len(msgs)} messages")

send_lsp(ws, "config/queryModels", {}, id_="models-1")
msgs = recv_all(ws, timeout=30, idle_gap=5)
print(f"[queryModels] received {len(msgs)} messages")

for i, m in enumerate(msgs):
    method = m.get("method", "(response)")
    id_ = m.get("id", "-")
    if m.get("id") == "models-1" and "result" in m:
        result = m["result"]
        print("\n=== Model List ===")
        if isinstance(result, dict):
            for cat, models in result.items():
                if isinstance(models, list):
                    print(f"\n[{cat}]")
                    for model in models:
                        if isinstance(model, dict):
                            print(f"  key={model.get('key')}, name={model.get('displayName')}, "
                                  f"reasoning={model.get('isReasoning')}, default={model.get('isDefault')}")
        else:
            print(f"  result: {result}")
    else:
        s = json.dumps(m, ensure_ascii=False)
        if len(s) > 500:
            s = s[:500] + "..."
        print(f"  [{i}] method={method} id={id_}: {s}")

ws.close()
