"""Extract full JWT token and chat API request details from Trae CN logs."""
import base64
import json
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9NiIsInR5cCI6IkpXVCJ9[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")
# More relaxed JWT pattern
JWT_RE2 = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")

# Use the most recent real log dir (skip aha_log)
log_dirs = sorted([d for d in (BASE / "logs").iterdir() if d.name != "aha_log"])
latest_dir = log_dirs[-1]
print(f"=== Using latest log dir: {latest_dir.name} ===")

# Extract full JWT tokens from all logs
all_jwts = set()
for log_file in latest_dir.rglob("*.log"):
    try:
        data = log_file.read_bytes()
    except Exception:
        continue
    for m in JWT_RE2.finditer(data):
        all_jwts.add(m.group())

print(f"\n=== Found {len(all_jwts)} unique JWT tokens ===")
for jwt in sorted(all_jwts, key=len, reverse=True):
    jwt_str = jwt.decode("ascii", errors="replace")
    parts = jwt_str.split(".")
    if len(parts) == 3:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(pad))
            exp = payload.get("exp", 0)
            import time
            now = time.time()
            status = "EXPIRED" if exp < now else f"VALID (expires in {(exp-now)/3600:.1f}h)"
            print(f"\n  Status: {status}")
            print(f"  Payload: {json.dumps(payload, indent=2)[:400]}")
            print(f"  Token: {jwt_str[:80]}...{jwt_str[-20:]}")
            print(f"  Length: {len(jwt_str)}")
        except Exception as exc:
            print(f"  Decode error: {exc}, token: {jwt_str[:60]}...")

# Search for chat API request details in ai-agent logs
print("\n=== Searching for chat API request details ===")
ai_agent_logs = list(latest_dir.rglob("ai-agent*stdout*.log"))
if not ai_agent_logs:
    # Search all log dirs
    for d in log_dirs:
        ai_agent_logs.extend(d.rglob("ai-agent*stdout*.log"))

for log_file in ai_agent_logs[-3:]:  # Check last 3
    data = log_file.read_bytes()
    print(f"\n--- {log_file.relative_to(BASE)} ({len(data)} bytes) ---")
    # Search for key request fields
    for pattern in [
        rb"chat_mode",
        rb"create_agent_task",
        rb"model_name",
        rb"intent_name",
        rb"user_input",
        rb"x-app-id",
        rb"x-device-id",
        rb"x-machine-id",
        rb"chat_history",
    ]:
        matches = list(re.finditer(pattern, data, re.IGNORECASE))
        if matches:
            print(f"\n  '{pattern.decode()}': {len(matches)} matches")
            m = matches[0]
            start = max(0, m.start() - 200)
            end = min(len(data), m.end() + 600)
            snippet = data[start:end].decode("utf-8", errors="replace")
            print(f"    {snippet[:800]}")
