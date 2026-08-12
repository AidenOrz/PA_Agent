"""Extract full JWT token and chat API request details from Trae CN logs."""
import json
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")

# Find the most recent ai-agent log
log_dirs = sorted((BASE / "logs").iterdir())
print(f"Log directories: {[d.name for d in log_dirs]}")

# Use the most recent log dir
latest_dir = log_dirs[-1]
print(f"\n=== Using latest log dir: {latest_dir.name} ===")

# Find ai-agent logs
ai_agent_logs = list(latest_dir.rglob("ai-agent*stdout*.log"))
print(f"ai-agent logs: {[p.name for p in ai_agent_logs]}")

# Extract full JWT tokens and chat API requests from all logs in the latest dir
all_jwts = set()
for log_file in latest_dir.rglob("*.log"):
    try:
        data = log_file.read_bytes()
    except Exception:
        continue
    for m in JWT_RE.finditer(data):
        all_jwts.add(m.group())

print(f"\n=== Found {len(all_jwts)} unique JWT tokens ===")
for jwt in all_jwts:
    jwt_str = jwt.decode("ascii", errors="replace")
    # Decode the payload to check expiry
    parts = jwt_str.split(".")
    if len(parts) == 3:
        import base64
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(pad))
            print(f"\n  JWT payload: {json.dumps(payload, indent=2)[:300]}")
            print(f"  Full token: {jwt_str[:80]}...{jwt_str[-20:]}")
            print(f"  Length: {len(jwt_str)}")
        except Exception as exc:
            print(f"  Failed to decode: {exc}")

# Now search for the chat API request details in the ai-agent log
print("\n=== Searching for chat API request details ===")
for log_file in ai_agent_logs:
    data = log_file.read_bytes()
    # Search for request headers, body, and response
    # Look for "chat" related content
    for pattern in [
        rb"chat_mode",
        rb"create_agent_task",
        rb"model_name",
        rb"intent_name",
        rb"user_input",
        rb"Authorization",
        rb"x-app-id",
        rb"x-device-id",
        rb"x-machine-id",
        rb"chat_history",
        rb"function",
    ]:
        matches = list(re.finditer(pattern, data, re.IGNORECASE))
        if matches:
            print(f"\n  {log_file.name}: '{pattern.decode()}' - {len(matches)} matches")
            for m in matches[:1]:
                start = max(0, m.start() - 100)
                end = min(len(data), m.end() + 500)
                snippet = data[start:end].decode("utf-8", errors="replace")
                print(f"    ...{snippet[:600]}...")
