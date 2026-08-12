"""Search ai-agent logs for API request patterns and auth tokens."""
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
                # Read last 5MB
                with open(p, "rb") as fh:
                    fh.seek(-5 * 1024 * 1024, 2)
                    data = fh.read()
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
        except:
            continue

        # Search for API URLs, auth headers, and request bodies
        patterns = [
            (rb"trae-api-cn\.mchost\.guru[^\s\"']*", "API URL"),
            (rb"Authorization[^}]*Bearer[^\s\"']+", "Auth header"),
            (rb"Bearer\s+eyJ[A-Za-z0-9_\-\.]+", "Bearer JWT"),
            (rb"model_name[\":\s]+\w+", "model_name"),
            (rb"intent_name[\":\s]+\w+", "intent_name"),
            (rb"user_input[\":\s]", "user_input"),
            (rb"/api/[a-z/_-]+", "API path"),
            (rb"x-app-id[\":\s]+[\w-]+", "x-app-id"),
            (rb"x-device-id[\":\s]+[\w-]+", "x-device-id"),
        ]

        for pat, label in patterns:
            matches = list(re.finditer(pat, data))
            if not matches:
                continue
            seen = set()
            for m in matches[:5]:
                s = m.group().decode("utf-8", errors="replace")[:150]
                if s not in seen:
                    seen.add(s)
                    print(f"[{d}] {label}: {s}")
