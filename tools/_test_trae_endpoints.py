"""Test various TRAE endpoints and auth methods."""
import json
import base64
import hashlib
import uuid
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
import httpx

# ── Decrypt storage.json ─────────────────────────────────────────────────
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

# ── Generate temp token ──────────────────────────────────────────────────
url_gen = "https://api.trae.cn/cloudide/api/v3/trae/GenerateTempToken"
headers_gen = {
    "Content-Type": "application/json",
    "x-cloudide-token": user_jwt,
    "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
    "x-custom-trace-id": uuid.uuid4().hex,
    "x-device-id": "3951005750868043",
    "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
    "x-device-type": "windows",
    "request-traffic-type": "prod",
    "x-request-id": str(uuid.uuid4()),
    "x-trae-request-id": str(uuid.uuid4()),
}
resp_gen = httpx.post(url_gen, headers=headers_gen, json={"IDEVersion": "0.1.48"}, timeout=30.0)
temp_token = resp_gen.json()["Result"]["Token"]
print("User JWT first 50:", user_jwt[:50])
print("Temp token first 50:", temp_token[:50])
print()

# ── Common headers ───────────────────────────────────────────────────────
def make_headers(auth_name, auth_value):
    trace_id = uuid.uuid4().hex
    req_id = str(uuid.uuid4())
    h = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
        "x-app-version": "default",
        "x-app-version-code": "20260806",
        "x-ide-version": "0.1.48",
        "x-ide-version-code": "20260806",
        "x-ide-version-type": "stable",
        "x-custom-trace-id": trace_id,
        "x-flow-traceparent": f"04-{trace_id}-{uuid.uuid4().hex[:16]}-01",
        "x-device-id": "3951005750868043",
        "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
        "x-device-brand": "PA-Agent",
        "x-device-cpu": "Intel",
        "x-device-type": "windows",
        "x-os-version": "Windows 10 Pro",
        "request-traffic-type": "prod",
        "x-request-id": req_id,
        "x-trae-request-id": req_id,
    }
    if auth_name:
        h[auth_name] = auth_value
    return h

# ── Test 1: model_list with x-ide-token (temp token) ─────────────────────
print("=== Test 1: model_list with x-ide-token (temp) ===")
url = "https://trae-api-cn.mchost.guru/api/ide/v1/model_list"
resp = httpx.post(url, headers=make_headers("x-ide-token", temp_token), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
print()

# ── Test 2: model_list with x-ide-token (user JWT) ───────────────────────
print("=== Test 2: model_list with x-ide-token (user JWT) ===")
resp = httpx.post(url, headers=make_headers("x-ide-token", user_jwt), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
print()

# ── Test 3: model_list with x-cloudide-token (user JWT) ──────────────────
print("=== Test 3: model_list with x-cloudide-token (user JWT) ===")
resp = httpx.post(url, headers=make_headers("x-cloudide-token", user_jwt), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
print()

# ── Test 4: model_list with Authorization Bearer (user JWT) ──────────────
print("=== Test 4: model_list with Authorization Bearer (user JWT) ===")
resp = httpx.post(url, headers=make_headers("Authorization", f"Bearer {user_jwt}"), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
print()

# ── Test 5: model_list with NO auth header ───────────────────────────────
print("=== Test 5: model_list with NO auth header ===")
resp = httpx.post(url, headers=make_headers(None, None), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
print()

# ── Test 6: super_completion_query with x-ide-token (user JWT) ───────────
print("=== Test 6: super_completion_query with x-ide-token (user JWT) ===")
url2 = "https://trae-api-cn.mchost.guru/api/ide/v1/super_completion_query"
body = {
    "messages": [{"role": "user", "content": "Say hello"}],
    "model": "glm-5.2",
}
with httpx.stream("POST", url2, headers=make_headers("x-ide-token", user_jwt), json=body, timeout=30.0) as resp:
    print(f"Status: {resp.status_code}")
    count = 0
    for line in resp.iter_lines():
        if line:
            print(f"  {line[:200]}")
            count += 1
            if count > 10:
                break
print()

# ── Test 7: ping endpoint ────────────────────────────────────────────────
print("=== Test 7: ping with x-ide-token (temp) ===")
url3 = "https://trae-api-cn.mchost.guru/api/ide/v1/ping"
resp = httpx.post(url3, headers=make_headers("x-ide-token", temp_token), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
print()

# ── Test 8: ping with x-ide-token (user JWT) ─────────────────────────────
print("=== Test 8: ping with x-ide-token (user JWT) ===")
resp = httpx.post(url3, headers=make_headers("x-ide-token", user_jwt), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")
