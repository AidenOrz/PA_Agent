"""Try matching function labels with model names for llm_utils_chat."""
import json, base64, hashlib, uuid, time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
import httpx

sp = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\GlobalStorage\storage.json")
storage = json.loads(sp.read_text(encoding="utf-8"))
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
        "Accept": "text/event-stream",
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

chat_url = "https://trae-api-cn.mchost.guru/api/agent/v3/llm_utils_chat"
q = "Say hello in Chinese, one sentence only."

# Try different function values with glm-5.2
functions = ["solo_agent_lite", "solo_agent", "chat_v3", "builder", "builder_v3",
             "solo_coder", "solo_work_lite", "agent", "solo_agent_remote"]

print("=== llm_utils_chat: function variants with model_name=glm-5.2 ===")
for func in functions:
    body = {"user_input": q, "model_name": "glm-5.2", "function": func}
    h = mk_headers()
    try:
        with httpx.stream("POST", chat_url, headers=h, json=body, timeout=15.0) as resp:
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line[:200])
            status = lines[0] if lines else ""
            error = next((l for l in lines if "error" in l.lower()), "")
            print(f"  func={func}: {resp.status_code} | {error[:200]}")
    except Exception as e:
        print(f"  func={func}: Exception {e}")

# Try function=utils with different param combos
print("\n=== llm_utils_chat: function=utils with different params ===")
utils_combos = [
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "intent_name": "chat"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "intent_name": "code"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "intent_name": "ask"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "usage": "chat"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "usage": "code"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "intent_name": "chat", "chat_history": []},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "intent": "chat"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "scene": "chat"},
    {"user_input": q, "model_name": "glm-5.2", "function": "utils", "app_id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8"},
    {"user_input": q, "function": "utils"},  # no model_name
]
for body in utils_combos:
    h = mk_headers()
    try:
        with httpx.stream("POST", chat_url, headers=h, json=body, timeout=15.0) as resp:
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line[:250])
            error = next((l for l in lines if "error" in l.lower() or "data" in l.lower()), "")
            print(f"  keys={list(body.keys())}: {error[:250]}")
    except Exception as e:
        print(f"  keys={list(body.keys())}: Exception {e}")

# Try llm_raw_chat with correct content array format and model names
print("\n=== llm_raw_chat: correct format with different models ===")
raw_url = "https://trae-api-cn.mchost.guru/api/ide/v1/llm_raw_chat"
for model in ["glm-5.2", "Doubao-Seed-2.1-Pro", "kimi-k2.7-code", "DeepSeek-V4-Flash", "qwen-3.7-plus"]:
    body = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": q}]}],
        "model": model,
    }
    h = mk_headers()
    try:
        with httpx.stream("POST", raw_url, headers=h, json=body, timeout=20.0) as resp:
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line[:250])
            print(f"  model={model}:")
            for l in lines[:6]:
                print(f"    {l}")
    except Exception as e:
        print(f"  model={model}: Exception {e}")
