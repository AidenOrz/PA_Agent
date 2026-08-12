"""Extract WebSocket protocol details from aicoding-agent extension.js."""
import re

EXT = r"C:\Program Files\QoderCN\resources\app\extensions\aicoding-agent\dist\extension.js"
with open(EXT, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

print(f"[+] extension.js size: {len(text)} chars")

# Search for WebSocket connection patterns
patterns = [
    (r'new WebSocket[^;]{0,200}', "new WebSocket(...)"),
    (r'ws://[^"\']{0,100}', "ws:// URLs"),
    (r'wss://[^"\']{0,100}', "wss:// URLs"),
    (r'36510', "port 36510"),
    (r'["\']ws["\']', "literal 'ws'"),
    (r'Cosy-MachineToken', "Cosy-MachineToken header"),
    (r'jsonrpc[^;]{0,100}', "jsonrpc"),
    (r'extension/register', "extension/register"),
    (r'method:["\'][a-zA-Z0-9_./]{3,50}', "method: names"),
    (r'["\']initialize["\']', "initialize"),
    (r'["\']chat\.send["\']', "chat.send"),
    (r'["\']chat\.stream["\']', "chat.stream"),
    (r'["\']chat\.message["\']', "chat.message"),
    (r'["\']broker\.[a-zA-Z.]+["\']', "broker.* methods"),
]

for pat, desc in patterns:
    matches = list(set(re.findall(pat, text)))
    if matches:
        print(f"\n=== {desc} ({len(matches)} unique) ===")
        for m in sorted(matches)[:15]:
            preview = m[:200]
            print(f"  {preview}")
    else:
        print(f"\n=== {desc}: NOT FOUND ===")

# Search for method name patterns
print("\n\n=== Looking for JSON-RPC method calls ===")
method_re = re.compile(r'method:["\']([a-zA-Z0-9_./\-]{3,60})["\']')
methods = sorted(set(method_re.findall(text)))
print(f"Found {len(methods)} unique method names:")
for m in methods:
    print(f"  {m}")

# Also look for .send( patterns with method names
print("\n\n=== .send() patterns ===")
send_re = re.compile(r'\.send\(\s*["\']([a-zA-Z0-9_./\-]{3,60})["\']')
sends = sorted(set(send_re.findall(text)))
print(f"Found {len(sends)} unique .send() methods:")
for s in sends:
    print(f"  {s}")
