"""Test the Trae CN llm_utils_chat API with the most recent JWT token."""
import base64
import json
import re
import time
import uuid
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")

# Find the most recent JWT token across ALL log dirs
all_jwts = {}
for log_dir in sorted((BASE / "logs").iterdir()):
    if not log_dir.is_dir():
        continue
    for log_file in log_dir.rglob("*.log"):
        try:
            data = log_file.read_bytes()
            if len(data) > 50 * 1024 * 1024:
                continue
        except Exception:
            continue
        for m in JWT_RE.finditer(data):
            jwt = m.group().decode("ascii", errors="replace")
            parts = jwt.split(".")
            if len(parts) == 3:
                pad = parts[1] + "=" * (-len(parts[1]) % 4)
                try:
                    payload = json.loads(base64.urlsafe_b64decode(pad))
                    exp = payload.get("exp", 0)
                    iat = payload.get("iat", 0)
                    if jwt not in all_jwts or iat > all_jwts[jwt][1]:
                        all_jwts[jwt] = (exp, iat, log_file.name)
                except Exception:
                    pass

# Sort by iat (issued at) descending to get the most recent
sorted_jwts = sorted(all_jwts.items(), key=lambda x: x[1][1], reverse=True)
print(f"Found {len(sorted_jwts)} unique JWT tokens")
for jwt, (exp, iat, log_name) in sorted_jwts[:5]:
    now = time.time()
    status = "EXPIRED" if exp < now else f"VALID (expires in {(exp-now)/3600:.1f}h)"
    print(f"  iat={iat} exp={exp} status={status} from={log_name}")
    print(f"  token: {jwt[:60]}...{jwt[-20:]}")

if not sorted_jwts:
    print("No JWT tokens found!")
    exit(1)

# Use the most recent token (even if expired)
token = sorted_jwts[0][0]
print(f"\nUsing token: {token[:60]}...")

# Device info
env_path = BASE / "ModularData" / "ckg_server" / "local_env.json"
env = json.loads(env_path.read_text(encoding="utf-8"))
storage = json.loads(
    (BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8")
)

device_id = env.get("device_id", "")
machine_id = storage.get("telemetry.machineId", "")
print(f"Device ID: {device_id}")
print(f"Machine ID: {machine_id}")

# Make the API call
import requests

url = "https://trae-api-cn.mchost.guru/api/agent/v3/llm_utils_chat"
trace_id = uuid.uuid4().hex
request_id = str(uuid.uuid4())

headers = {
    "Content-Type": "application/json",
    "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    "x-app-version": "default",
    "x-app-version-code": "20260630",
    "x-ide-version": "3.3.76",
    "x-ide-version-code": "20260630",
    "x-ide-version-type": "stable",
    "x-custom-trace-id": trace_id,
    "x-flow-traceparent": f"04-{trace_id}-{uuid.uuid4().hex[:16]}-01",
    "x-device-id": device_id,
    "x-machine-id": machine_id,
    "x-device-brand": "MS-7D48",
    "x-device-cpu": "Intel",
    "x-device-type": "windows",
    "x-os-version": "Windows 10 Pro",
    "request-traffic-type": "prod",
    "x-request-id": request_id,
    "x-trae-request-id": request_id,
    "Authorization": f"Bearer {token}",
}

# Use the request body format from the summary
payload = {
    "user_input": "Say hello in one sentence.",
    "model_name": "glm-5.2",
    "intent_name": "chat",
    "chat_history": [],
    "function": "utils",
}

print(f"\n=== POST {url} ===")
print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

try:
    resp = requests.post(url, headers=headers, json=payload, timeout=30.0, stream=True)
    print(f"\nStatus: {resp.status_code}")
    print(f"Response headers:")
    for k, v in resp.headers.items():
        if k.lower() in ("content-type", "x-log-id", "x-request-id", "transfer-encoding"):
            print(f"  {k}: {v}")
    
    print(f"\nResponse body:")
    line_count = 0
    for line in resp.iter_lines():
        if line:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            print(f"  {line[:500]}")
            line_count += 1
            if line_count > 50:
                print("  ... (truncated)")
                break
except Exception as exc:
    print(f"Error: {exc}")
