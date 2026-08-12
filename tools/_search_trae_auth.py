"""Search TRAE main.js for auth/token/super_completion context."""
from pathlib import Path

p = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js")
text = p.read_text(encoding="utf-8", errors="replace")
print(f"File size: {len(text)} chars")

keywords = [
    "GenerateTempToken",
    "cloudide-token",
    "ide-token",
    "super_completion_query",
    "llm_raw_chat",
    "llm_utils_chat",
    "trae-api-cn",
    "x-trae",
    "tt-net",
    "ttnet",
    "TTNet",
    "x-tt",
    "bear-hat",
    "x-mcs",
    "mcs-token",
]

for kw in keywords:
    idx = 0
    count = 0
    while True:
        idx = text.find(kw, idx)
        if idx < 0:
            break
        count += 1
        if count <= 3:
            start = max(0, idx - 200)
            end = min(len(text), idx + 300)
            snippet = text[start:end].replace("\n", "\\n")
            print(f"\n=== {kw} @ {idx} (occurrence {count}) ===")
            print(snippet)
        idx += len(kw)
    print(f"\n--- '{kw}' total occurrences: {count} ---")
