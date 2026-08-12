"""Try llm_raw_chat with additional fields and model_name."""
import json, base64, hashlib, uuid
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

raw_url = "https://trae-api-cn.mchost.guru/api/ide/v1/llm_raw_chat"
q = "Say hello in Chinese, one sentence only."

msgs = [{"role": "user", "content": [{"type": "text", "text": q}]}]

# Try many field combinations
combos = [
    # With function field
    ("R-F1: +function=chat", {"messages": msgs, "model": "glm-5.2", "function": "chat"}),
    ("R-F2: +function=utils", {"messages": msgs, "model": "glm-5.2", "function": "utils"}),
    ("R-F3: +function=solo_agent_lite", {"messages": msgs, "model": "glm-5.2", "function": "solo_agent_lite"}),
    # With model_name instead of model
    ("R-M1: model_name", {"messages": msgs, "model_name": "glm-5.2"}),
    ("R-M2: model_name+function", {"messages": msgs, "model_name": "glm-5.2", "function": "chat"}),
    ("R-M3: model_name+function=utils", {"messages": msgs, "model_name": "glm-5.2", "function": "utils"}),
    # With stream
    ("R-S1: +stream=true", {"messages": msgs, "model": "glm-5.2", "stream": True}),
    ("R-S2: +stream=false", {"messages": msgs, "model": "glm-5.2", "stream": False}),
    # With max_tokens
    ("R-T1: +max_tokens", {"messages": msgs, "model": "glm-5.2", "max_tokens": 100}),
    # With app_id
    ("R-A1: +app_id", {"messages": msgs, "model": "glm-5.2", "app_id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8"}),
    # With temperature
    ("R-T2: +temperature", {"messages": msgs, "model": "glm-5.2", "temperature": 0.7}),
    # String content (simple)
    ("R-C1: string content+model_name", {"messages": [{"role": "user", "content": q}], "model_name": "glm-5.2"}),
    ("R-C2: string content+model_name+function", {"messages": [{"role": "user", "content": q}], "model_name": "glm-5.2", "function": "chat"}),
    # With user_input
    ("R-U1: user_input+model+function", {"user_input": q, "model": "glm-5.2", "function": "chat"}),
    ("R-U2: user_input+model_name+function", {"user_input": q, "model_name": "glm-5.2", "function": "chat"}),
    # With intent_name
    ("R-I1: +intent_name=chat", {"messages": msgs, "model": "glm-5.2", "function": "utils", "intent_name": "chat"}),
    # With all fields
    ("R-ALL: everything", {"messages": msgs, "model": "glm-5.2", "model_name": "glm-5.2", "function": "chat", "stream": True, "max_tokens": 100, "app_id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8"}),
]

for label, body in combos:
    h = mk_headers()
    try:
        with httpx.stream("POST", raw_url, headers=h, json=body, timeout=20.0) as resp:
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line)
            # Find the error/data line
            data_line = next((l for l in lines if l.startswith("data:")), "")
            print(f"{label}: {resp.status_code} | {data_line[:200]}")
    except Exception as e:
        print(f"{label}: Exception {e}")

# Also try llm_utils_chat with function=chat and different model names
print("\n\n=== llm_utils_chat: function=chat with different models ===")
chat_url = "https://trae-api-cn.mchost.guru/api/agent/v3/llm_utils_chat"
for model in ["glm-5.2", "Doubao-Seed-2.1-Pro", "kimi-k3", "kimi-k2.7-code", "DeepSeek-V4-Flash", "qwen-3.7-plus", "auto", "Doubao_1_6"]:
    body = {"user_input": q, "model_name": model, "function": "chat"}
    h = mk_headers()
    try:
        with httpx.stream("POST", chat_url, headers=h, json=body, timeout=15.0) as resp:
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line)
            data_line = next((l for l in lines if l.startswith("data:")), "")
            print(f"  model={model}: {data_line[:250]}")
    except Exception as e:
        print(f"  model={model}: Exception {e}")
