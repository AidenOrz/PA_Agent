"""Send JSON-RPC requests immediately after connecting to Qoder CN WebSocket."""
import json
import time
import uuid
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

def connect():
    return websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={"Cosy-MachineToken": MACHINE_TOKEN},
        suppress_origin=True,
        timeout=5,
    )

def send_and_recv(ws, msg: dict, timeout: float = 3.0, label: str = ""):
    raw = json.dumps(msg)
    # Try with Content-Length framing
    framed = f"Content-Length: {len(raw)}\n\n{raw}"
    old_timeout = ws.timeout
    ws.settimeout(timeout)
    try:
        ws.send(framed)
        print(f"  [{label}] SENT: {raw[:150]}")
    except Exception as e:
        print(f"  [{label}] SEND ERR: {e}")
        ws.settimeout(old_timeout)
        return None
    try:
        result = ws.recv()
        print(f"  [{label}] RECV ({len(result)} bytes): {result[:400]}")
        return result
    except Exception as e:
        print(f"  [{label}] RECV ERR: {e}")
    ws.settimeout(old_timeout)
    return None

def send_raw_and_recv(ws, raw: str, timeout: float = 3.0, label: str = ""):
    old_timeout = ws.timeout
    ws.settimeout(timeout)
    try:
        ws.send(raw)
        print(f"  [{label}] SENT raw: {raw[:150]}")
    except Exception as e:
        print(f"  [{label}] SEND ERR: {e}")
        ws.settimeout(old_timeout)
        return None
    try:
        result = ws.recv()
        print(f"  [{label}] RECV ({len(result)} bytes): {result[:400]}")
        return result
    except Exception as e:
        print(f"  [{label}] RECV ERR: {e}")
    ws.settimeout(old_timeout)
    return None

# Test 1: Send initialize immediately (no framing)
print("=== Test 1: initialize (no framing) ===")
ws = connect()
init = {"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}}
send_and_recv(ws, init, timeout=3, label="init-no-frame")
# Also try without Content-Length prefix
send_raw_and_recv(ws, json.dumps(init), timeout=3, label="init-raw")
ws.close()

# Test 2: Various methods
print("\n=== Test 2: Various methods ===")
ws = connect()
methods = [
    ("initialize", {}),
    ("query", {"query": "hello"}),
    ("stream", {"query": "hello"}),
    ("feature/getFeatureFlags", {}),
    ("chat.send", {"message": "hello"}),
    ("chat.query", {"query": "hello"}),
    ("session.new", {}),
    ("session.list", {}),
    ("extension/listCommands", {}),
    ("broker.listSessions", {}),
    ("ping", {}),
]
for method, params in methods:
    msg = {"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8], "method": method, "params": params}
    send_and_recv(ws, msg, timeout=2, label=method)
    time.sleep(0.2)
ws.close()

# Test 3: Read first, then send
print("\n=== Test 3: Read first message, then send ===")
ws = connect()
ws.settimeout(3)
try:
    first = ws.recv()
    print(f"  First msg: {first[:300]}")
except Exception as e:
    print(f"  First msg err: {e}")

# Now send initialize
init = {"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}}
send_and_recv(ws, init, timeout=3, label="after-first")
ws.close()
