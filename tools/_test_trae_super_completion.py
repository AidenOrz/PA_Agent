"""Test TRAE super_completion_query endpoint with x-ide-token auth."""
import json
import base64
import hashlib
import uuid
import time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
import httpx

# ── 1. Decrypt storage.json to get user JWT ──────────────────────────────
sp = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\GlobalStorage\storage.json")
storage = json.loads(sp.read_text(encoding="utf-8"))

Rte = [82,9,106,213,48,54,165,56,191,64,163,158,129,243,215,251,124,227,57,130,155,47,255,135,52,142,67,68,196,222,233,203,84,123,148,50,166,194,35,61,238,76,149,11,66,250,195,78,8,46,161,102,40,217,36,178,118,91,162,73,109,139,209,37]
Ste = [31,221,168,51,136,7,199,49,177,18,16,89,39,128,236,95,96,81,127,169,25,181,74,13,45,229,122,159,147,201,156,239,160,224,59,77,174,42,245,176,200,235,187,60,131,83,153,97,23,43,4,126,186,119,214,38,225,105,20,99,85,33,12,125]
salt = bytes(a ^ b for a, b in zip(Rte, Ste))

auth_key = [k for k in storage if k.startswith("iCubeAuthInfo://") and "icube.cloudide" in k][0]
raw = base64.b64decode(storage[auth_key])
km = raw[6:38]
ct = raw[38:]
inner = hashlib.sha512(km).digest()
derived = hashlib.sha512(inner + salt).digest()
dec = Cipher(algorithms.AES(derived[0:16]), modes.CBC(derived[16:32])).decryptor()
padded = dec.update(ct) + dec.finalize()
unp = PKCS7(128).unpadder()
plain = unp.update(padded) + unp.finalize()
obj = json.loads(plain[64:].decode("utf-8"))
user_jwt = obj["token"]

# ── 2. Generate temp token ───────────────────────────────────────────────
url_gen = "https://api.trae.cn/cloudide/api/v3/trae/GenerateTempToken"
trace_id = uuid.uuid4().hex
req_id = str(uuid.uuid4())
headers_gen = {
    "Content-Type": "application/json",
    "x-cloudide-token": user_jwt,
    "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    "x-custom-trace-id": trace_id,
    "x-device-id": "3951005750868043",
    "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
    "x-device-type": "windows",
    "request-traffic-type": "prod",
    "x-request-id": req_id,
    "x-trae-request-id": req_id,
}
resp_gen = httpx.post(url_gen, headers=headers_gen, json={"IDEVersion": "0.1.48"}, timeout=30.0)
temp_token = resp_gen.json()["Result"]["Token"]
print("Temp token obtained:", temp_token[:50], "...")

# Save temp token
token_file = Path.home() / ".trae-cn" / "trae-jwt-token"
token_file.parent.mkdir(parents=True, exist_ok=True)
token_file.write_text(temp_token, encoding="utf-8")

# ── 3. Call super_completion_query ───────────────────────────────────────
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
    "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
    "x-device-brand": "PA-Agent",
    "x-device-cpu": "Intel",
    "x-device-type": "windows",
    "x-os-version": "Windows 10 Pro",
    "request-traffic-type": "prod",
    "x-request-id": req_id2,
    "x-trae-request-id": req_id2,
}

# Try different body formats
bodies = [
    {
        "query": "Say hello in Chinese, one sentence only.",
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": "Say hello in Chinese, one sentence only."}],
    },
    {
        "prompt": "Say hello in Chinese, one sentence only.",
        "model_name": "glm-5.2",
    },
    {
        "user_input": "Say hello in Chinese, one sentence only.",
        "model_name": "glm-5.2",
    },
    {
        "messages": [{"role": "user", "content": "Say hello in Chinese, one sentence only."}],
        "model": "glm-5.2",
        "stream": True,
    },
]

for i, body in enumerate(bodies):
    print(f"\n=== Attempt {i+1}: body keys = {list(body.keys())} ===")
    try:
        with httpx.stream("POST", url, headers=headers, json=body, timeout=30.0) as resp:
            print(f"Status: {resp.status_code}")
            if resp.status_code != 200:
                error_text = resp.read().decode("utf-8", errors="replace")[:500]
                print(f"Error: {error_text}")
            else:
                line_count = 0
                for line in resp.iter_lines():
                    if line:
                        print(f"  {line[:300]}")
                        line_count += 1
                        if line_count > 20:
                            print("  ...(truncated)")
                            break
    except Exception as e:
        print(f"Exception: {e}")
