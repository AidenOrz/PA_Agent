"""Find the actual JSON-RPC method names the extension sends to the sidecar."""
import re

EXT = r"C:\Program Files\QoderCN\resources\app\extensions\aicoding-agent\dist\extension.js"
with open(EXT, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

# Search for chatAskDirect
print("=== chatAskDirect context ===")
idx = text.find("chatAskDirect")
while idx >= 0:
    context = text[max(0, idx-200):min(len(text), idx+300)]
    print(f"\n  @{idx}: ...{context}...")
    print("---")
    idx = text.find("chatAskDirect", idx + 1)

# Search for sendRequest patterns
print("\n\n=== sendRequest patterns ===")
sr_re = re.compile(r'\.sendRequest\(["\']([^"\']{3,60})["\']')
methods = sorted(set(sr_re.findall(text)))
print(f"Found {len(methods)} sendRequest methods:")
for m in methods:
    print(f"  {m}")

# Search for languageClient. method calls
print("\n\n=== languageClient. method calls ===")
lc_re = re.compile(r'languageClient\.([a-zA-Z]+)\(')
lc_methods = sorted(set(lc_re.findall(text)))
print(f"Found {len(lc_methods)} languageClient methods:")
for m in lc_methods:
    print(f"  {m}")

# Search for .onRequest patterns (methods the extension handles)
print("\n\n=== onRequest patterns (extension handles these) ===")
or_re = re.compile(r'\.onRequest\(["\']([^"\']{3,60})["\']')
or_methods = sorted(set(or_re.findall(text)))
print(f"Found {len(or_methods)} onRequest methods:")
for m in or_methods:
    print(f"  {m}")

# Search for .onNotification patterns
print("\n\n=== onNotification patterns ===")
on_re = re.compile(r'\.onNotification\(["\']([^"\']{3,60})["\']')
on_methods = sorted(set(on_re.findall(text)))
print(f"Found {len(on_methods)} onNotification methods:")
for m in on_methods:
    print(f"  {m}")

# Search for MethodName constants
print("\n\n=== Method name constants ===")
mn_re = re.compile(r'(?:MethodName|method_name|METHOD)\s*=\s*["\']([a-zA-Z0-9_./\-]{3,60})["\']')
mn_methods = sorted(set(mn_re.findall(text)))
for m in mn_methods:
    print(f"  {m}")
