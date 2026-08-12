"""Connect to Qoder CN WebSocket and read first message with longer timeout."""
import json
import time
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

# Suppress default Origin by passing suppress_origin=True
print("[+] Connecting to ws://127.0.0.1:36510/ws ...")
try:
    ws = websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={"Cosy-MachineToken": MACHINE_TOKEN},
        suppress_origin=True,  # Don't add default Origin header
        timeout=10,
    )
    print(f"[+] Connected! Status: {ws.status}")
    print(f"[+] Headers: {dict(ws.headers)}")
    print(f"[+] Subprotocol: {ws.subprotocol}")

    # Try to receive with longer timeout
    print("\n[+] Waiting for first message (timeout=10s)...")
    try:
        result = ws.recv()
        print(f"[+] Received {len(result)} bytes")
        print(f"[+] Content (first 1000 chars):\n{result[:1000]}")
    except Exception as e:
        print(f"[!] recv error: {e}")

    # Try sending a message
    print("\n[+] Trying to send initialize...")
    init_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {
            "clientName": "test-client",
            "clientVersion": "1.0.0",
        }
    })
    ws.send(init_msg)
    print(f"[+] Sent: {init_msg[:200]}")

    # Wait for response
    print("\n[+] Waiting for response (timeout=10s)...")
    try:
        result = ws.recv()
        print(f"[+] Received {len(result)} bytes")
        print(f"[+] Content: {result[:1000]}")
    except Exception as e:
        print(f"[!] recv error: {e}")

    ws.close()
except Exception as e:
    print(f"[!] Connection error: {e}")
    import traceback
    traceback.print_exc()
