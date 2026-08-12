"""Check state.vscdb for auth tokens and search for llm_utils_chat API."""
import sqlite3
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")

# 1. Check state.vscdb - look for auth/token keys
print("=== state.vscdb ===")
vscdb_path = BASE / "User" / "globalStorage" / "state.vscdb"
if vscdb_path.exists():
    db = sqlite3.connect(str(vscdb_path))
    cur = db.cursor()
    # Get ALL keys
    cur.execute("SELECT key FROM ItemTable ORDER BY key")
    all_keys = [r[0] for r in cur.fetchall()]
    print(f"Total keys: {len(all_keys)}")
    # Filter for auth/token/credential related
    auth_keys = [k for k in all_keys if any(kw in k.lower() for kw in ("auth", "token", "credential", "session", "login", "icube", "cloudide", "trae", "account"))]
    print(f"Auth-related keys: {auth_keys}")
    
    # Get values for auth-related keys
    for key in auth_keys:
        cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
        row = cur.fetchone()
        if row:
            val = row[0]
            if isinstance(val, bytes):
                print(f"\n  {key}: bytes len={len(val)}, first 100: {val[:100]}")
            else:
                print(f"\n  {key}: {str(val)[:200]}")
    db.close()

# 2. Search for llm_utils_chat in ALL log files
print("\n\n=== Searching for llm_utils_chat API ===")
logs_dir = BASE / "logs"
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")

for log_dir in sorted(logs_dir.iterdir()):
    if not log_dir.is_dir():
        continue
    for log_file in log_dir.rglob("*.log"):
        try:
            data = log_file.read_bytes()
        except Exception:
            continue
        if b"llm_utils_chat" in data:
            print(f"\n  Found in: {log_file.relative_to(BASE)}")
            # Find the context around llm_utils_chat
            idx = 0
            count = 0
            while True:
                idx = data.find(b"llm_utils_chat", idx)
                if idx == -1 or count >= 3:
                    break
                start = max(0, idx - 300)
                end = min(len(data), idx + 800)
                snippet = data[start:end].decode("utf-8", errors="replace")
                print(f"  --- at position {idx} ---")
                print(f"  {snippet[:1000]}")
                print()
                idx += 1
                count += 1
            break  # Only check first file with matches
    else:
        continue
    break

# 3. Search for the SSE/streaming response format
print("\n=== Searching for streaming response format ===")
for log_dir in sorted(logs_dir.iterdir()):
    if not log_dir.is_dir():
        continue
    for log_file in log_dir.rglob("ai-agent*stdout*.log"):
        try:
            data = log_file.read_bytes()
        except Exception:
            continue
        # Search for SSE event patterns
        for pattern in [b"event:", b"data:", b"content:", b"reasoning:", b"delta:", b"stream"]:
            if pattern in data:
                idx = data.find(pattern)
                start = max(0, idx - 100)
                end = min(len(data), idx + 400)
                snippet = data[start:end].decode("utf-8", errors="replace")
                print(f"\n  {log_file.name} - '{pattern.decode()}': {snippet[:500]}")
                break
        break
    break
