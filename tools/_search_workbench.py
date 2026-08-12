"""Search workbench JS for temp token usage and chat endpoints."""
from pathlib import Path

p = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\vs\workbench\workbench.desktop.main.solo-lite.js")
text = p.read_text(encoding="utf-8", errors="replace")
print(f"File size: {len(text)} chars")

keywords = [
    "generateTempToken",
    "tempToken",
    "temp_token",
    "TempToken",
    "x-ide-token",
    "ide-token",
    "ideToken",
    "super_completion",
    "completion_query",
    "/api/ide/v1/",
    "/api/agent/v3/",
    "llm_utils_chat",
    "llm_raw_chat",
    "chat_completion",
    "model_list",
    "GetTempToken",
    "ide_user_ent",
]

for kw in keywords:
    idx = 0
    count = 0
    while True:
        idx = text.find(kw, idx)
        if idx < 0:
            break
        count += 1
        if count <= 2:
            start = max(0, idx - 200)
            end = min(len(text), idx + 350)
            snippet = text[start:end].replace("\n", "\\n")
            print(f"\n=== [{kw} @ {idx}] (occ {count}) ===")
            print(snippet)
        idx += len(kw)
    if count > 0:
        print(f"--- '{kw}' total: {count} ---")
