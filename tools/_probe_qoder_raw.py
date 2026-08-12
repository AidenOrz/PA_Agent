"""Raw socket probe to see exact bytes from Qoder CN sidecar on port 36510."""
import socket
import time
import uuid
import json
import base64
import os

TOKEN_PATH = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\machine_token.json"
with open(TOKEN_PATH, "r", encoding="utf-8") as f:
    MACHINE_TOKEN = json.load(f)["token"]

# Generate a random Sec-WebSocket-Key
ws_key = base64.b64encode(os.urandom(16)).decode("ascii")

# Build a proper WebSocket upgrade request
request = (
    f"GET /ws HTTP/1.1\r\n"
    f"Host: 127.0.0.1:36510\r\n"
    f"Upgrade: websocket\r\n"
    f"Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {ws_key}\r\n"
    f"Sec-WebSocket-Version: 13\r\n"
    f"Cosy-MachineToken: {MACHINE_TOKEN}\r\n"
    f"Origin: vscode://vscode.github\r\n"
    f"\r\n"
).encode("utf-8")

print(f"[+] Connecting to 127.0.0.1:36510...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(("127.0.0.1", 36510))

print(f"[+] Sending WebSocket upgrade request ({len(request)} bytes)...")
s.sendall(request)

# Read the response
print("[+] Reading response...")
all_data = b""
try:
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        all_data += chunk
        if len(all_data) > 8192:
            break
except socket.timeout:
    pass

print(f"\n[+] Received {len(all_data)} bytes total")
print(f"\n=== RAW RESPONSE (first 2000 bytes) ===")
# Show as text, replacing non-printable chars
text = all_data[:2000].decode("utf-8", errors="replace")
print(text)

print(f"\n=== HEX DUMP (first 200 bytes) ===")
for i in range(0, min(200, len(all_data)), 16):
    hex_part = " ".join(f"{b:02x}" for b in all_data[i:i+16])
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in all_data[i:i+16])
    print(f"  {i:04x}: {hex_part:<48} {ascii_part}")

s.close()

# Now try a plain HTTP GET (no WebSocket upgrade)
print("\n\n=== Now trying plain HTTP GET /ws ===")
s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s2.settimeout(5)
s2.connect(("127.0.0.1", 36510))
http_req = (
    f"GET /ws HTTP/1.1\r\n"
    f"Host: 127.0.0.1:36510\r\n"
    f"Cosy-MachineToken: {MACHINE_TOKEN}\r\n"
    f"\r\n"
).encode("utf-8")
s2.sendall(http_req)
all_data2 = b""
try:
    while True:
        chunk = s2.recv(4096)
        if not chunk:
            break
        all_data2 += chunk
        if len(all_data2) > 4096:
            break
except socket.timeout:
    pass
print(f"[+] Received {len(all_data2)} bytes")
print(f"\n=== HTTP GET RESPONSE ===")
print(all_data2[:1500].decode("utf-8", errors="replace"))
s2.close()

# Try HTTP POST with JSON-RPC
print("\n\n=== Now trying HTTP POST /ws with JSON-RPC ===")
s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s3.settimeout(5)
s3.connect(("127.0.0.1", 36510))
rpc_body = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}})
http_post = (
    f"POST /ws HTTP/1.1\r\n"
    f"Host: 127.0.0.1:36510\r\n"
    f"Content-Type: application/json\r\n"
    f"Content-Length: {len(rpc_body)}\r\n"
    f"Cosy-MachineToken: {MACHINE_TOKEN}\r\n"
    f"\r\n"
    f"{rpc_body}"
).encode("utf-8")
s3.sendall(http_post)
all_data3 = b""
try:
    while True:
        chunk = s3.recv(4096)
        if not chunk:
            break
        all_data3 += chunk
        if len(all_data3) > 4096:
            break
except socket.timeout:
    pass
print(f"[+] Received {len(all_data3)} bytes")
print(f"\n=== HTTP POST RESPONSE ===")
print(all_data3[:1500].decode("utf-8", errors="replace"))
s3.close()
