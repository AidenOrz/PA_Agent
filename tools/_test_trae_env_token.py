"""Test TRAE API using TRAE_USER_CLOUDIDE_TOKEN_BLOB env var as token."""
import json
import os
import uuid
import requests

blob = os.environ.get("TRAE_USER_CLOUDIDE_TOKEN_BLOB", "")
print(f"TRAE_USER_CLOUDIDE_TOKEN_BLOB length: {len(blob)}")
print(f"Prefix: {blob[:80]}")

# Try 1: Use blob as x-cloudide-token for GenerateTempToken
print("\n=== Try 1: GenerateTempToken with blob as x-cloudide-token ===")
url_gen = "https://api.trae.cn/cloudide/api/v3/trae/GenerateTempToken"
trace_id = uuid.uuid4().hex
req_id = str(uuid.uuid4())
headers_gen = {
    "Content-Type": "application/json",
    "x-cloudide-token": blob,
    "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    "x-custom-trace-id": trace_id,
    "x-device-id": "3951005750868043",
    "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
    "x-device-type": "windows",
    "request-traffic-type": "prod",
    "x-request-id": req_id,
    "x-trae-request-id": req_id,
}
try:
    resp = requests.post(url_gen, headers=headers_gen, json={"IDEVersion": "0.1.48"}, timeout=30.0)
    print(f"  Status: {resp.status_code}")
    print(f"  Body: {resp.text[:500]}")
    if resp.status_code == 200:
        data = resp.json()
        if "Result" in data and "Token" in data["Result"]:
            temp_token = data["Result"]["Token"]
            print(f"  Got temp token: {temp_token[:60]}...")

            # Now try super_completion_query with this temp token
            print("\n=== Try 2: super_completion_query with temp token from blob ===")
            url = "https://trae-api-cn.mchost.guru/api/ide/v1/super_completion_query"
            trace_id2 = uuid.uuid4().hex
            req_id2 = str(uuid.uuid4())
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-ide-token": temp_token,
                "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
                "x-app-version": "default",
                "x-app-version-code": "20260806",
                "x-ide-version": "0.1.48",
                "x-ide-version-code": "20260806",
                "x-ide-version-type": "stable",
                "x-custom-trace-id": trace_id2,
                "x-flow-traceparent": f"04-{trace_id2}-{uuid.uuid4().hex[:16]}-01",
                "x-device-id": "3951005750868043",
                "x-device-brand": "MS-7D48",
                "x-device-cpu": "Intel",
                "x-device-type": "windows",
                "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
                "x-os-version": "Windows 10 Pro",
                "request-traffic-type": "prod",
                "x-request-id": req_id2,
                "x-trae-request-id": req_id2,
            }
            body = {
                "query": "用中文说一句你好",
                "model": "glm-5.2",
                "messages": [{"role": "user", "content": "用中文说一句你好"}],
                "stream": True,
            }
            resp2 = requests.post(url, headers=headers, json=body, stream=True, timeout=60.0)
            print(f"  Status: {resp2.status_code}")
            line_count = 0
            for line in resp2.iter_lines():
                if line:
                    line_str = line.decode("utf-8", errors="replace")
                    print(f"  L{line_count}: {line_str[:300]}")
                    line_count += 1
                    if line_count > 30:
                        print("  ...(truncated)")
                        break
except Exception as e:
    print(f"  Exception: {e}")

# Try 3: Use blob directly as x-ide-token (skip GenerateTempToken)
print("\n=== Try 3: super_completion_query with blob directly as x-ide-token ===")
url = "https://trae-api-cn.mchost.guru/api/ide/v1/super_completion_query"
trace_id3 = uuid.uuid4().hex
req_id3 = str(uuid.uuid4())
headers3 = {
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
    "x-ide-token": blob,
    "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    "x-app-version": "default",
    "x-app-version-code": "20260806",
    "x-ide-version": "0.1.48",
    "x-ide-version-code": "20260806",
    "x-ide-version-type": "stable",
    "x-custom-trace-id": trace_id3,
    "x-flow-traceparent": f"04-{trace_id3}-{uuid.uuid4().hex[:16]}-01",
    "x-device-id": "3951005750868043",
    "x-device-brand": "MS-7D48",
    "x-device-cpu": "Intel",
    "x-device-type": "windows",
    "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
    "x-os-version": "Windows 10 Pro",
    "request-traffic-type": "prod",
    "x-request-id": req_id3,
    "x-trae-request-id": req_id3,
}
body3 = {
    "query": "用中文说一句你好",
    "model": "glm-5.2",
    "messages": [{"role": "user", "content": "用中文说一句你好"}],
    "stream": True,
}
try:
    resp3 = requests.post(url, headers=headers3, json=body3, stream=True, timeout=60.0)
    print(f"  Status: {resp3.status_code}")
    line_count = 0
    for line in resp3.iter_lines():
        if line:
            line_str = line.decode("utf-8", errors="replace")
            print(f"  L{line_count}: {line_str[:300]}")
            line_count += 1
            if line_count > 30:
                print("  ...(truncated)")
                break
except Exception as e:
    print(f"  Exception: {e}")
