"""Read the full extension/register message from Qoder CN sidecar."""
import json
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

ws = websocket.create_connection(
    "ws://127.0.0.1:36510/ws",
    header={"Cosy-MachineToken": MACHINE_TOKEN},
    suppress_origin=True,
    timeout=15,
)
print("[+] Connected!")

# Read first message
raw = ws.recv()
print(f"[+] Raw message length: {len(raw)}")

# Parse: strip "Content-Length: N\n\n" prefix if present
if raw.startswith("Content-Length:"):
    parts = raw.split("\n\n", 1)
    if len(parts) == 2:
        header_part = parts[0]
        json_part = parts[1]
        print(f"[+] Header: {header_part}")
        print(f"[+] JSON length: {len(json_part)}")
        try:
            msg = json.loads(json_part)
            print(f"\n=== PARSED JSON-RPC MESSAGE ===")
            print(f"jsonrpc: {msg.get('jsonrpc')}")
            print(f"method: {msg.get('method')}")
            params = msg.get("params", {})
            print(f"params keys: {list(params.keys()) if isinstance(params, dict) else type(params)}")

            # Print all details
            print(f"\n=== FULL PARAMS (pretty) ===")
            print(json.dumps(params, indent=2, ensure_ascii=False)[:5000])
        except json.JSONDecodeError as e:
            print(f"[!] JSON parse error: {e}")
            print(f"[+] Raw JSON (first 2000): {json_part[:2000]}")
else:
    print("[+] No Content-Length prefix, raw content:")
    print(raw[:2000])

# Now try to read more messages
print("\n=== Trying to read more messages (5s timeout) ===")
import time
ws.settimeout(3)
for i in range(5):
    try:
        msg = ws.recv()
        print(f"\n[MSG {i+1}] ({len(msg)} bytes): {msg[:500]}")
    except Exception as e:
        print(f"[MSG {i+1}] timeout/error: {e}")
        break

# Try sending initialize with different params
print("\n=== Sending initialize with various params ===")
init_variants = [
    {"jsonrpc": "2.0", "id": "1", "method": "initialize"},
    {"jsonrpc": "2.0", "id": "2", "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "id": "3", "method": "initialize", "params": {"clientInfo": {"name": "test", "version": "1.0"}}},
    {"jsonrpc": "2.0", "id": "4", "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
]

for init in init_variants:
    msg = json.dumps(init)
    # Add Content-Length prefix like the server does
    framed = f"Content-Length: {len(msg)}\n\n{msg}"
    try:
        ws.send(framed)
        print(f"\n[SENT] {msg[:200]}")
    except Exception as e:
        print(f"\n[SEND ERR] {e}")
        break
    try:
        result = ws.recv()
        print(f"[RECV] {result[:500]}")
    except Exception as e:
        print(f"[RECV ERR] {e}")

ws.close()
