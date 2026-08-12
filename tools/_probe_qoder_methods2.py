"""Try many JSON-RPC method names to find chat-related ones."""
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
    timeout=5,
)
print("[+] Connected!")

# Initialize first
init = {"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {}}
ws.send(json.dumps(init))
try:
    resp = ws.recv()
    print(f"[+] Initialize response: {resp[:200]}")
except:
    print("[+] Initialize timeout (continuing anyway)")

# Try many methods
methods = [
    # LSP standard
    "shutdown",
    "exit",
    "textDocument/completion",
    "textDocument/hover",
    "workspace/symbol",
    "workspace/executeCommand",
    "completion/resolve",
    "textDocument/codeLens",
    "textDocument/signatureHelp",
    "textDocument/definition",
    "textDocument/references",
    "textDocument/formatting",
    "textDocument/codeAction",
    "textDocument/rename",
    "textDocument/documentSymbol",
    "textDocument/semanticTokens",
    "workspace/didChangeConfiguration",
    "workspace/configuration",
    "$/cancelRequest",
    "$/setTrace",
    "$/logTrace",
    # Custom - chat related
    "chat/new",
    "chat/send",
    "chat/message",
    "chat/create",
    "chat/start",
    "chat/answer",
    "chat/finish",
    "chat/stream",
    "chat/list",
    "chat/notify",
    "chat/cancel",
    "chat/stop",
    "chat/feedback",
    # Custom - session
    "session/create",
    "session/start",
    "session/list",
    "session/delete",
    "session/restore",
    # Custom - agent
    "agent/start",
    "agent/run",
    "agent/chat",
    "agent/stop",
    "agent/cancel",
    # Custom - task
    "task/create",
    "task/run",
    "task/list",
    "task/cancel",
    # Custom - model
    "model/list",
    "model/select",
    "model/info",
    # Custom - quest
    "quest/start",
    "quest/send",
    "quest/chat",
    "quest/create",
    # Custom - other
    "feature/getFeatureFlags",
    "ping",
    "health",
    "status",
    "info",
    "version",
    "capabilities",
    "commands",
    "listCommands",
    "getCommands",
    "getContextProviders",
    "getExtensions",
    "getCodeCompletion",
    "getInlineCompletion",
    "completion",
    "inlineCompletion",
    "codeCompletion",
    # More chat variants
    "aicoding.chat",
    "aicoding/chat",
    "aicoding.completion",
    "aicoding/completion",
    "cosy.chat",
    "cosy/chat",
    "cosy.chat.send",
    "cosy.chat.stream",
    "chat.createTask",
    "chat.createSession",
    "chat.sendMessage",
    "chat.sendMessageStream",
    "chat.sendUserMessage",
    "chat.sendQuestion",
    "chat.ask",
    "chat.query",
    "chat.run",
    "chat.invoke",
    "chat.generate",
    "chat.complete",
    "chat.completion",
    "chat.inference",
    "chat.predict",
    "chat.response",
    "chat.reply",
    "chat.request",
    "chat.submit",
    "chat.post",
    "chat.process",
]

found_methods = []
not_found_methods = []

for method in methods:
    msg = {"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8], "method": method, "params": {}}
    ws.send(json.dumps(msg))
    ws.settimeout(2)
    try:
        result = ws.recv()
        # Parse the response
        if result.startswith("Content-Length:"):
            parts = result.split("\n\n", 1)
            if len(parts) == 2:
                try:
                    resp_json = json.loads(parts[1])
                    if "error" in resp_json and resp_json["error"].get("code") == -32601:
                        not_found_methods.append(method)
                    else:
                        found_methods.append((method, resp_json))
                        print(f"  [FOUND] {method}: {json.dumps(resp_json)[:200]}")
                except json.JSONDecodeError:
                    print(f"  [PARSE ERR] {method}: {parts[1][:100]}")
            else:
                print(f"  [FORMAT] {method}: {result[:100]}")
        else:
            print(f"  [RAW] {method}: {result[:100]}")
    except Exception as e:
        print(f"  [TIMEOUT] {method}")
        not_found_methods.append(method)
    time.sleep(0.05)

print(f"\n\n=== SUMMARY ===")
print(f"Found methods ({len(found_methods)}):")
for m, r in found_methods:
    print(f"  {m}")
print(f"\nNot found methods ({len(not_found_methods)}):")
for m in not_found_methods:
    print(f"  {m}")

ws.close()
