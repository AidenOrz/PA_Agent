"""Find Qu enum (API categories) and any chat/completion/streaming endpoints."""
from pathlib import Path
import re

p = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\vs\workbench\workbench.desktop.main.solo-lite.js")
text = p.read_text(encoding="utf-8", errors="replace")

# Find Qu enum definition
print("=== Qu enum / API categories ===")
for m in re.finditer(r'Qu\s*=\s*\{', text):
    idx = m.start()
    end = text.find('}', idx)
    if end > 0 and end - idx < 2000:
        snippet = text[idx:end+1].replace("\n", "\\n")
        print(f"@ {idx}: {snippet[:1500]}")
        print()

# Find all getApi calls with paths
print("\n=== getApi calls (API paths) ===")
seen = set()
for m in re.finditer(r'getApi\([^,]+,\s*["`](/[a-z_/]+)["`]', text):
    path = m.group(1)
    if path not in seen:
        seen.add(path)
        idx = m.start()
        print(f"  {path}")

# Find chat/completion/stream related
print("\n=== chat/completion/stream keywords ===")
for kw in ["chat_completions", "chat/completions", "/chat/", "completion", "stream_chat", "doStream", "doRequestWithStream"]:
    idx = 0
    count = 0
    while True:
        idx = text.find(kw, idx)
        if idx < 0:
            break
        count += 1
        if count <= 2:
            start = max(0, idx - 150)
            end = min(len(text), idx + 250)
            snippet = text[start:end].replace("\n", "\\n")
            print(f"\n  [{kw} @ {idx}] {snippet}")
        idx += len(kw)
    if count:
        print(f"  --- '{kw}' total: {count} ---")
