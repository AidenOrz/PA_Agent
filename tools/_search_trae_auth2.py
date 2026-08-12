"""Search TRAE JS files for super_completion_query and Cloud-IDE-JWT auth."""
from pathlib import Path

base = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out")

# Find all .js files
js_files = list(base.rglob("*.js"))
print(f"Total JS files: {len(js_files)}")

keywords = [
    "super_completion_query",
    "Cloud-IDE-JWT",
    "solo-lite-websocket-headers",
    "llm_raw_chat",
    "llm_utils_chat",
    "x-ide-token",
    "ide-token",
    "x-flow-traceparent",
]

for js in js_files:
    try:
        text = js.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for kw in keywords:
        if kw in text:
            idx = text.find(kw)
            start = max(0, idx - 250)
            end = min(len(text), idx + 350)
            snippet = text[start:end].replace("\n", "\\n")
            print(f"\n=== {js.name} [{kw} @ {idx}] ===")
            print(snippet)
