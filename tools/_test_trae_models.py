"""Find correct model names and body format for TRAE chat API."""
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

def make_headers():
    trace_id = uuid.uuid4().hex
    req_id = str(uuid.uuid4())
    return {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-ide-token": user_jwt,
        "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
        "x-app-version": "default",
        "x-app-version-code": "20260806",
        "x-ide-version": "0.1.48",
        "x-ide-version-code": "20260806",
        "x-ide-version-type": "stable",
        "x-custom-trace-id": trace_id,
        "x-device-id": "3951005750868043",
        "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
        "x-device-type": "windows",
        "request-traffic-type": "prod",
        "x-request-id": req_id,
        "x-trae-request-id": req_id,
    }

base = "https://trae-api-cn.mchost.guru"

# ── Try model_list with GET ──────────────────────────────────────────────
print("=== model_list GET ===")
resp = httpx.get(f"{base}/api/ide/v1/model_list", headers=make_headers(), timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")
print()

# ── Try model_list with different body ───────────────────────────────────
for body in [{"model_type": "chat"}, {"type": "chat"}, {"scene": "chat"}, {}]:
    print(f"=== model_list POST body={body} ===")
    resp = httpx.post(f"{base}/api/ide/v1/model_list", headers=make_headers(), json=body, timeout=30.0)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
    print()

# ── Try get_model_list ───────────────────────────────────────────────────
print("=== get_model_list ===")
resp = httpx.post(f"{base}/api/ide/v1/get_model_list", headers=make_headers(), json={}, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")
print()

# ── Try llm_raw_chat with different model names ──────────────────────────
model_names = [
    "doubao-pro-32k",
    "doubao-pro-4k",
    "doubao-lite-32k",
    "doubao-1.5-pro-32k",
    "skylark-chat",
    "claude-3-5-sonnet",
    "gpt-4o",
    "deepseek-v3",
    "glm-4",
    "glm-4-plus",
    "bytedance-v3",
    "default",
]

for model_name in model_names:
    body = {"user_input": "Say hello", "model_name": model_name}
    try:
        with httpx.stream("POST", f"{base}/api/ide/v1/llm_raw_chat", headers=make_headers(), json=body, timeout=15.0) as resp:
            if resp.status_code != 200:
                print(f"  {model_name}: HTTP {resp.status_code}")
                continue
            for line in resp.iter_lines():
                if line and line.startswith("data:"):
                    data = line[5:].strip()
                    if "error" in data.lower():
                        print(f"  {model_name}: {data[:150]}")
                        break
                    elif "content" in data.lower() or "text" in data.lower() or "delta" in data.lower():
                        print(f"  {model_name}: SUCCESS! {data[:200]}")
                        break
                    elif "done" in data.lower():
                        print(f"  {model_name}: done (no content)")
                        break
    except Exception as e:
        print(f"  {model_name}: Exception {e}")
