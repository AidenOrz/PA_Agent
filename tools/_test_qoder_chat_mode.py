"""Test Qoder CN with chat mode instead of agent mode."""
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


def test_model(model_key: str, mode: str = "chat", question: str = "Reply with exactly: hi"):
    print(f"\n{'='*60}")
    print(f"Testing model: {model_key}, mode: {mode}")
    print(f"Question: {question}")
    print(f"{'='*60}")

    ws = websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={"Cosy-MachineToken": MACHINE_TOKEN},
        suppress_origin=True,
        timeout=15,
    )

    send_lsp(ws, "initialize", {}, id_="init")
    ws.settimeout(3)
    try:
        _ = ws.recv()
    except Exception:
        pass

    request_id = str(uuid.uuid4())
    chat_params = {
        "sessionId": "",
        "requestId": request_id,
        "questionText": question,
        "mode": mode,
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
            "text": question,
            "localeLang": "zh-cn",
            "preferredLanguage": "zh-cn",
        },
        "extra": {
            "modelConfig": {
                "key": model_key,
            },
        },
    }

    t_start = time.monotonic()
    t_first_token = None
    send_lsp(ws, "chat/ask", chat_params, id_="chat")

    content_parts = []
    ws.settimeout(0.5)
    deadline = time.monotonic() + 120
    finish_reason = ""

    while time.monotonic() < deadline:
        try:
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as e:
            print(f"  [recv error] {e}")
            break

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        for m in parse_lsp_messages(raw):
            method = m.get("method", "")
            params = m.get("params", {})
            if method == "chat/answer":
                if t_first_token is None:
                    t_first_token = time.monotonic()
                text = str(params.get("text", ""))
                if text:
                    content_parts.append(text)
            elif method == "chat/finish":
                finish_reason = str(params.get("reason", ""))
                t_end = time.monotonic()
                content = "".join(content_parts)
                content = re.sub(r"````think::\{THINK_TIME\}.*?````", "", content, flags=re.DOTALL).strip()

                total_time = t_end - t_start
                first_token_time = (t_first_token - t_start) if t_first_token else 0
                print(f"\n  [RESULT]")
                print(f"  model: {model_key}, mode: {mode}")
                print(f"  finish_reason: {finish_reason}")
                print(f"  content: {content!r}")
                print(f"  total_time: {total_time:.2f}s")
                print(f"  first_token_time: {first_token_time:.2f}s")
                print(f"  content_length: {len(content)} chars")

                ws.close()
                return {
                    "model": model_key,
                    "mode": mode,
                    "content": content,
                    "total_time": total_time,
                    "first_token_time": first_token_time,
                    "finish_reason": finish_reason,
                }

    t_end = time.monotonic()
    content = "".join(content_parts)
    print(f"\n  [TIMEOUT after {t_end - t_start:.1f}s]")
    print(f"  content so far: {content!r}")
    ws.close()
    return {
        "model": model_key,
        "mode": mode,
        "content": content,
        "total_time": t_end - t_start,
        "first_token_time": (t_first_token - t_start) if t_first_token else 0,
        "finish_reason": "timeout",
    }


# Test chat mode (lighter than agent mode)
results = []
for model_key in ["mmodel", "auto"]:
    for mode in ["chat", "agent"]:
        try:
            r = test_model(model_key, mode=mode)
            results.append(r)
        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({"model": model_key, "mode": mode, "error": str(e), "total_time": 0})

# Summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"{'Model':<15} {'Mode':<10} {'Total Time':<15} {'First Token':<15} {'Content':<20}")
print(f"{'-'*75}")
for r in results:
    if "error" in r:
        print(f"{r['model']:<15} {r.get('mode',''):<10} ERROR: {r['error'][:40]}")
    else:
        print(f"{r['model']:<15} {r['mode']:<10} {r['total_time']:.2f}s{'':<8} {r['first_token_time']:.2f}s{'':<8} {r.get('content', '')[:20]!r}")
