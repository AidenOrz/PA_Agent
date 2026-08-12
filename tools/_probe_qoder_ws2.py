"""Qoder CN WebSocket client - proper JSON-RPC 2.0 communication.

The sidecar on port 36510 accepts WebSocket at /ws with Cosy-MachineToken header.
Server sends extension/register notification on connect.
"""
import json
import uuid
import threading
import time
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

URL = "ws://127.0.0.1:36510/ws"
HEADERS = {"Cosy-MachineToken": MACHINE_TOKEN}

received_messages = []
connected = threading.Event()

def on_message(ws, message):
    received_messages.append(message)
    if len(received_messages) <= 10:
        preview = message[:300] if isinstance(message, str) else str(message)[:300]
        print(f"  [RECV #{len(received_messages)}] {preview}")
    elif len(received_messages) == 11:
        print(f"  [RECV ...] (suppressing further messages, total so far: {len(received_messages)})")

def on_error(ws, error):
    print(f"  [ERROR] {error}")

def on_close(ws, code, msg):
    print(f"  [CLOSE] code={code} msg={msg}")

def on_open(ws):
    print("  [OPEN] Connected!")
    connected.set()

def send_rpc(ws, method: str, params: dict = None, is_notification: bool = False):
    req = {"jsonrpc": "2.0", "method": method}
    if not is_notification:
        req["id"] = str(uuid.uuid4())[:8]
    if params:
        req["params"] = params
    msg = json.dumps(req)
    print(f"  [SEND] {msg[:200]}")
    ws.send(msg)

print(f"[+] Connecting to {URL} with Cosy-MachineToken header...")

# Enable trace for debugging
websocket.enableTrace(False)

ws = websocket.WebSocketApp(
    URL,
    header=HEADERS,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
    on_open=on_open,
)

# Start WebSocket in background
wst = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 30, "ping_timeout": 10})
wst.daemon = True
wst.start()

# Wait for connection
if not connected.wait(timeout=5):
    print("[!] Failed to connect within 5s")
    ws.close()
    exit(1)

# Wait to receive initial messages
print("\n[+] Waiting 3s for initial messages...")
time.sleep(3)

print(f"\n[+] Received {len(received_messages)} messages total.")
print("\n[+] Now trying to send JSON-RPC methods...")

# Try various methods
methods_to_try = [
    ("ping", {}),
    ("initialize", {}),
    ("listModels", {}),
    ("chat.listModels", {}),
    ("model.list", {}),
    ("extension/listCommands", {}),
    ("broker.listSessions", {}),
    ("chat.listSessions", {}),
    ("session.list", {}),
]

for method, params in methods_to_try:
    send_rpc(ws, method, params)
    time.sleep(0.5)

# Wait for responses
print("\n[+] Waiting 5s for responses...")
time.sleep(5)

print(f"\n[+] Total messages received: {len(received_messages)}")
print("\n[+] All received messages (first 500 chars each):")
for i, msg in enumerate(received_messages[:20]):
    preview = msg[:500] if isinstance(msg, str) else str(msg)[:500]
    print(f"\n--- Message {i+1} ---\n{preview}")

ws.close()
