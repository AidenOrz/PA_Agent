"""Search ai-agent logs for chat API and JWT tokens."""
import os
import re

base = r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\logs"
for d in sorted(os.listdir(base), reverse=True)[:3]:
    dpath = os.path.join(base, d, "Modular")
    if not os.path.isdir(dpath):
        continue
    for f in os.listdir(dpath):
        if "ai-agent" not in f:
            continue
        p = os.path.join(dpath, f)
        try:
            size = os.path.getsize(p)
            if size > 30 * 1024 * 1024:
                with open(p, "rb") as fh:
                    fh.seek(-8 * 1024 * 1024, 2)
                    data = fh.read()
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
        except:
            continue

        # Search for chat-related API calls and JWT tokens
        patterns = [
            (rb"/api/[a-z/_-]*chat[a-z/_-]*", "chat API path"),
            (rb"/api/[a-z/_-]*llm[a-z/_-]*", "llm API path"),
            (rb"/api/[a-z/_-]*completions[a-z/_-]*", "completions API path"),
            (rb"/api/[a-z/_-]*stream[a-z/_-]*", "stream API path"),
            (rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", "JWT token"),
            (rb"authorization[\":\s]+[^\s,\"'}]{20,}", "authorization header"),
            (rb"intent_name[\":\s]+\w+", "intent_name"),
            (rb"chat_history[\":\s\[]", "chat_history"),
            (rb"function[\":\s]+\w+", "function field"),
            (rb"model_name[\":\s]+[^\s,}\"']+", "model_name full"),
        ]

        seen = set()
        for pat, label in patterns:
            matches = list(re.finditer(pat, data, re.IGNORECASE))
            if not matches:
                continue
            for m in matches[:3]:
                s = m.group().decode("utf-8", errors="replace")[:200]
                key = (label, s[:80])
                if key in seen:
                    continue
                seen.add(key)
                print(f"[{d}] {label}: {s}")
