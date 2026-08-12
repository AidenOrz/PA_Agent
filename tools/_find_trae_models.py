"""Find model names from TRAE storage and try model list endpoints."""
import json, base64, hashlib, uuid
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
import httpx

sp = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\GlobalStorage\storage.json")
storage = json.loads(sp.read_text(encoding="utf-8"))

# Search for model-related keys in storage
print("=== Model-related keys in storage.json ===")
for key in sorted(storage.keys()):
    kl = key.lower()
    if "model" in kl or "llm" in kl:
        val = storage[key]
        if isinstance(val, str):
            print(f"  {key}: {val[:200]}")
        elif isinstance(val, (dict, list)):
            s = json.dumps(val, ensure_ascii=False)
            print(f"  {key}: {s[:300]}")
        else:
            print(f"  {key}: {val}")

# Also check for model list in GlobalStorage
print("\n=== Files in GlobalStorage ===")
gs_dir = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\GlobalStorage")
for f in gs_dir.iterdir():
    if f.is_file() and f.suffix == ".json":
        print(f"  {f.name} ({f.stat().st_size} bytes)")
    elif f.is_dir():
        print(f"  [dir] {f.name}/")

# Check for model list in state.vscdb
print("\n=== Looking for model list in all JSON files ===")
for f in gs_dir.rglob("*.json"):
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
        if "model" in text.lower() and ("solo_agent" in text.lower() or "model_name" in text.lower() or "model_list" in text.lower()):
            print(f"\n  Found in: {f}")
            # Try to parse and find model entries
            try:
                data = json.loads(text)
                s = json.dumps(data, ensure_ascii=False)
                if "solo_agent" in s.lower() or "model_list" in s.lower():
                    print(f"  {s[:1000]}")
            except:
                pass
    except:
        pass

# Now decrypt user JWT and try model list endpoints
Rte = [82,9,106,213,48,54,165,56,191,64,163,158,129,243,215,251,124,227,57,130,155,47,255,135,52,142,67,68,196,222,233,203,84,123,148,50,166,194,35,61,238,76,149,11,66,250,195,78,8,46,161,102,40,217,36,178,118,91,162,73,109,139,209,37]
Ste = [31,221,168,51,136,7,199,49,177,18,16,89,39,128,236,95,96,81,127,169,25,181,74,13,45,229,122,159,147,201,156,239,160,224,59,77,174,42,245,176,200,235,187,60,131,83,153,97,23,43,4,126,186,119,214,38,225,105,20,99,85,33,12,125]
salt = bytes(a ^ b for a, b in zip(Rte, Ste))
auth_key = [k for k in storage if k.startswith("iCubeAuthInfo://") and "icube.cloudide" in k][0]
raw = base64.b64decode(storage[auth_key])
inner = hashlib.sha512(raw[6:38]).digest()
derived = hashlib.sha512(inner + salt).digest()
dec = Cipher(algorithms.AES(derived[0:16]), modes.CBC(derived[16:32])).decryptor()
padded = dec.update(raw[38:]) + dec.finalize()
unp = PKCS7(128).unpadder()
plain = unp.update(padded) + unp.finalize()
user_jwt = json.loads(plain[64:].decode("utf-8"))["token"]

device_id = "3951005750868043"
machine_id = "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5"

def mk_headers():
    tid = uuid.uuid4().hex
    rid = str(uuid.uuid4())
    return {
        "Content-Type": "application/json",
        "Authorization": f"Cloud-IDE-JWT {user_jwt}",
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

# Try model list endpoints with different paths
print("\n\n=== Model list endpoint attempts ===")
for path in [
    "/api/ide/v1/model_list_by_function",
    "/api/ide/v1/model_list",
    "/api/ide/v1/models",
    "/api/agent/v3/model_list_by_function",
    "/api/agent/v3/models",
    "/api/ide/v1/llm_model_list",
]:
    url = f"https://trae-api-cn.mchost.guru{path}"
    for body in [{}, {"function": "chat"}, {"function": "utils"}, {"functions": ["chat", "utils"]}, {"function": ["chat", "utils", "code"]}, {"app_id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8", "function": "chat"}]:
        try:
            resp = httpx.post(url, headers=mk_headers(), json=body, timeout=15.0)
            if resp.status_code != 404:
                print(f"  {path} body={body}: {resp.status_code} {resp.text[:300]}")
        except:
            pass
