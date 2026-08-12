"""Extract ALL WebSocket URLs and connection patterns from extension.js."""
import re

EXT = r"C:\Program Files\QoderCN\resources\app\extensions\aicoding-agent\dist\extension.js"
with open(EXT, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

# Find all ws:// patterns with context
print("=== All ws:// URLs with context ===")
ws_re = re.compile(r'.{0,100}ws://[^"\']{0,150}.{0,100}')
for m in ws_re.finditer(text):
    s = m.group(0)
    if "127.0.0.1" in s or "localhost" in s:
        print(f"\n  {s[:400]}")

# Find new WebSocket( patterns
print("\n\n=== new WebSocket() calls with context ===")
nws_re = re.compile(r'.{0,150}new WebSocket\(.{0,200}')
for m in nws_re.finditer(text):
    s = m.group(0)
    print(f"\n  {s[:500]}")

# Find port-related patterns
print("\n\n=== Port patterns ===")
port_re = re.compile(r'(?:port|PORT|Port)["\']?\s*[:=]\s*["\']?(\d{4,5})["\']?')
ports = sorted(set(port_re.findall(text)))
print(f"Found ports: {ports}")

# Find /ws, /chat, /agent path patterns
print("\n\n=== Path patterns for ws/chat/agent ===")
path_re = re.compile(r'["\'`](/(?:ws|chat|agent|rpc|api|stream|quest)[a-zA-Z0-9_/\-]*)["\'`]')
paths = sorted(set(path_re.findall(text)))
print(f"Found paths: {paths}")

# Find cosyInfo or port detection
print("\n\n=== cosyInfo / port detection ===")
ci_re = re.compile(r'.{0,100}cosyInfo.{0,200}')
for m in ci_re.finditer(text):
    print(f"\n  {m.group(0)[:400]}")

# Find .info.json patterns
print("\n\n=== .info.json patterns ===")
info_re = re.compile(r'.{0,100}\.info\.json.{0,100}')
for m in list(info_re.finditer(text))[:5]:
    print(f"\n  {m.group(0)[:300]}")
