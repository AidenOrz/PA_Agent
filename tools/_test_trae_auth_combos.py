"""Try multiple auth header combinations for TRAE chat endpoint."""
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

# Decode JWT payload to check expiry
parts = user_jwt.split(".")
pad = parts[1] + "=" * (-len(parts[1]) % 4)
payload = json.loads(base64.urlsafe_b64decode(pad))
print(f"User JWT: exp={payload.get('exp')}, iat={payload.get('iat')}, now={int(time.time())}")
print(f"  expired: {payload.get('exp', 0) <= time.time()}")
print(f"  token prefix: {user_jwt[:40]}...")

# ── 2. Generate temp token ───────────────────────────────────────────────
url_gen = "https://api.trae.cn/cloudide/api/v3/trae/GenerateTempToken"
trace_id = uuid.uuid4().hex
req_id = str(uuid.uuid4())
device_id = "3951005750868043"
machine_id = "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5"

headers_gen = {
    "Content-Type": "application/json",
    "x-cloudide-token": user_jwt,
    "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    "x-custom-trace-id": trace_id,
    "x-device-id": device_id,
    "x-machine-id": machine_id,
    "x-device-type": "windows",
    "request-traffic-type": "prod",
    "x-request-id": req_id,
    "x-trae-request-id": req_id,
}
resp_gen = httpx.post(url_gen, headers=headers_gen, json={"IDEVersion": "0.1.48"}, timeout=30.0)
gen_data = resp_gen.json()
temp_token = gen_data["Result"]["Token"]
print(f"\nTemp token obtained: {temp_token[:50]}...")

# ── 3. Try multiple auth combos on chat endpoint ─────────────────────────
chat_url = "https://trae-api-cn.mchost.guru/api/agent/v3/llm_utils_chat"
super_url = "https://trae-api-cn.mchost.guru/api/ide/v1/super_completion_query"

def base_headers():
    tid = uuid.uuid4().hex
    rid = str(uuid.uuid4())
    return {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
        "x-app-version": "default",
        "x-app-version-code": "20260806",
        "x-ide-version": "0.1.48",
        "x-ide-version-code": "20260806",
        "x-ide-version-type": "stable",
        "x-custom-trace-id": tid,
        "x-flow-traceparent": f"04-{tid}-{uuid.uuid4().hex[:16]}-01",
        "x-device-id": device_id,
        "x-machine-id": machine_id,
        "x-device-brand": "MS-7D48",
        "x-device-cpu": "Intel",
        "x-device-type": "windows",
        "x-os-version": "Windows 10 Pro",
        "request-traffic-type": "prod",
        "x-request-id": rid,
        "x-trae-request-id": rid,
    }

body_chat = {
    "user_input": "Say hello in Chinese, one sentence only.",
    "model_name": "glm-5.2",
    "intent_name": "chat",
    "function": "utils",
    "chat_history": [],
}

# Test combos: (label, url, headers_override, body)
combos = [
    ("A: Cloud-IDE-JWT user_jwt @ llm_utils_chat", chat_url,
     {"Authorization": f"Cloud-IDE-JWT {user_jwt}"}, body_chat),
    ("B: Cloud-IDE-JWT temp @ llm_utils_chat", chat_url,
     {"Authorization": f"Cloud-IDE-JWT {temp_token}"}, body_chat),
    ("C: x-icube-token user_jwt @ llm_utils_chat", chat_url,
     {"x-icube-token": user_jwt}, body_chat),
    ("D: x-ide-token temp @ llm_utils_chat", chat_url,
     {"x-ide-token": temp_token}, body_chat),
    ("E: x-ide-token user_jwt @ llm_utils_chat", chat_url,
     {"x-ide-token": user_jwt}, body_chat),
    ("F: Bearer user_jwt @ llm_utils_chat", chat_url,
     {"Authorization": f"Bearer {user_jwt}"}, body_chat),
    ("G: Cloud-IDE-JWT user_jwt @ super_completion", super_url,
     {"Authorization": f"Cloud-IDE-JWT {user_jwt}"}, body_chat),
    ("H: x-icube-token user_jwt @ super_completion", super_url,
     {"x-icube-token": user_jwt}, body_chat),
]

for label, url, hdr_override, body in combos:
    print(f"\n=== {label} ===")
    h = base_headers()
    h.update(hdr_override)
    try:
        with httpx.stream("POST", url, headers=h, json=body, timeout=20.0) as resp:
            print(f"  Status: {resp.status_code}")
            line_count = 0
            got_content = False
            for line in resp.iter_lines():
                if line:
                    print(f"  {line[:250]}")
                    line_count += 1
                    if "content" in line.lower() and "error" not in line.lower():
                        got_content = True
                    if line_count > 8:
                        print("  ...(truncated)")
                        break
            if got_content:
                print("  >>> SUCCESS: got content!")
    except Exception as e:
        print(f"  Exception: {e}")
