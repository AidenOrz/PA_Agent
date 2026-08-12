"""Test Qoder CN with disabled agent features - check if prompt is smaller and output is not truncated."""
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


def test_model(model_key, question, use_lean_config=True):
    print(f"\n{'='*60}")
    config_type = "lean (no agent tools)" if use_lean_config else "full agent"
    print(f"Model: {model_key}, Config: {config_type}")
    print(f"Question: {question[:100]}...")
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
    if use_lean_config:
        plugin_config = {
            "isEnableProjectRule": False,
            "isEnableAskAgent": False,
            "isEnableAutoMemory": False,
        }
    else:
        plugin_config = {}

    chat_params = {
        "sessionId": "",
        "requestId": request_id,
        "questionText": question,
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
        "pluginPayloadConfig": plugin_config,
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
    reasoning_parts = []
    usage_info = {}
    ws.settimeout(0.5)
    deadline = time.monotonic() + 180
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
                    # Check for thinking markers
                    if "think::" in text:
                        reasoning_parts.append(text)
                    else:
                        content_parts.append(text)
            elif method == "context/usage/sync":
                usage_info = params
            elif method == "chat/finish":
                finish_reason = str(params.get("reason", ""))
                t_end = time.monotonic()

                content = "".join(content_parts)
                content = re.sub(r"````think::\{THINK_TIME\}.*?````", "", content, flags=re.DOTALL).strip()
                reasoning = "".join(reasoning_parts).strip()

                total_time = t_end - t_start
                first_token_time = (t_first_token - t_start) if t_first_token else 0

                print(f"\n  [RESULT]")
                print(f"  finish_reason: {finish_reason}")
                print(f"  content ({len(content)} chars): {content[:200]!r}")
                if reasoning:
                    print(f"  reasoning ({len(reasoning)} chars): {reasoning[:200]!r}")
                print(f"  usage: {json.dumps(usage_info, ensure_ascii=False)}")
                print(f"  total_time: {total_time:.2f}s")
                print(f"  first_token_time: {first_token_time:.2f}s")

                ws.close()
                return {
                    "content": content,
                    "reasoning": reasoning,
                    "usage": usage_info,
                    "total_time": total_time,
                    "first_token_time": first_token_time,
                    "finish_reason": finish_reason,
                }

    t_end = time.monotonic()
    content = "".join(content_parts)
    print(f"\n  [TIMEOUT after {t_end - t_start:.1f}s]")
    print(f"  content so far ({len(content)} chars): {content[:200]!r}")
    ws.close()
    return {"content": content, "total_time": t_end - t_start, "finish_reason": "timeout"}


# Test 1: Simple question with lean config
question_simple = "Reply with exactly: hi"

# Test 2: JSON question similar to PA Agent's stage1
question_json = """Analyze the market and respond with ONLY a JSON object (no markdown, no explanation):
{"cycle_position":"trading_range","direction":"neutral","diagnosis_confidence":72,"market_phase":"stable","transition_risk":null,"detected_patterns":["barbwire","overlap"],"key_bars":[{"bar":"K1","role":"structure","bar_type":"outside_bull","context_effect":"strengthens_bull","follow_through":"pending","trapped_side":"bears"}]}

Output the exact same JSON above, nothing else."""

results = []
# Test with lean config (disabled agent features)
for model in ["mmodel", "auto"]:
    r = test_model(model, question_json, use_lean_config=True)
    results.append(("lean", model, r))

# Summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for config, model, r in results:
    if "error" in r:
        print(f"  {config}/{model}: ERROR {r['error']}")
    else:
        print(f"  {config}/{model}: time={r.get('total_time',0):.1f}s, "
              f"content={len(r.get('content',''))} chars, "
              f"finish={r.get('finish_reason','')}")
