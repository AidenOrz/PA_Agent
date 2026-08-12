"""Trace the exact WebSocket handshake with Qoder CN sidecar."""
import json
import base64
import os
import socket
import websocket

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

# Enable trace to see all frames
websocket.enableTrace(True)

print("=" * 60)
print("Test 1: create_connection with Cosy-MachineToken (should work)")
print("=" * 60)
try:
    ws = websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={"Cosy-MachineToken": MACHINE_TOKEN},
        timeout=5,
    )
    print(f"\n[+] Connected! Status: {ws.status}")
    print(f"[+] Headers: {dict(ws.headers)}")
    result = ws.recv()
    print(f"\n[+] First recv ({len(result)} chars): {result[:500]}")
    ws.close()
except Exception as e:
    print(f"\n[!] Error: {e}")

print("\n\n" + "=" * 60)
print("Test 2: create_connection with NO header (should fail)")
print("=" * 60)
try:
    ws = websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        timeout=5,
    )
    print(f"\n[+] Connected! Status: {ws.status}")
    result = ws.recv()
    print(f"\n[+] First recv: {result[:300]}")
    ws.close()
except Exception as e:
    print(f"\n[!] Error: {e}")

print("\n\n" + "=" * 60)
print("Test 3: create_connection with Origin header")
print("=" * 60)
try:
    ws = websocket.create_connection(
        "ws://127.0.0.1:36510/ws",
        header={
            "Cosy-MachineToken": MACHINE_TOKEN,
            "Origin": "http://127.0.0.1:36510",
        },
        timeout=5,
    )
    print(f"\n[+] Connected! Status: {ws.status}")
    result = ws.recv()
    print(f"\n[+] First recv: {result[:300]}")
    ws.close()
except Exception as e:
    print(f"\n[!] Error: {e}")
