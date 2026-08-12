"""Live test of TRAE Work CN API with fresh JWT from storage.json.

This script:
1. Reads storage.json (just-updated by running TRAE Work CN)
2. Decrypts the user JWT via AES-128-CBC
3. Calls GenerateTempToken to get a fresh x-ide-token
4. Calls /api/ide/v1/super_completion_query with a simple test message
5. Prints the model response (if any)
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


# ── 1. Decrypt storage.json to get user JWT ─────────────────────────────────
def get_user_jwt() -> str:
    sp = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\GlobalStorage\storage.json")
    storage = json.loads(sp.read_text(encoding="utf-8"))

    # AES salt = Rte XOR $te (hardcoded in TRAE main.js byteCrypto)
    Rte = bytes([82,9,106,213,48,54,165,56,191,64,163,158,129,243,215,251,
                 124,227,57,130,155,47,255,135,52,142,67,68,196,222,233,203,
                 84,123,148,50,166,194,35,61,238,76,149,11,66,250,195,78,8,
                 46,161,102,40,217,36,178,118,91,162,73,109,139,209,37])
    Ste = bytes([31,221,168,51,136,7,199,49,177,18,16,89,39,128,236,95,
                 96,81,127,169,25,181,74,13,45,229,122,159,147,201,156,239,
                 160,224,59,77,174,42,245,176,200,235,187,60,131,83,153,97,
                 23,43,4,126,186,119,214,38,225,105,20,99,85,33,12,125])
    salt = bytes(a ^ b for a, b in zip(Rte, Ste))

    auth_keys = [k for k in storage if k.startswith("iCubeAuthInfo://") and k != "iCubeAuthInfo://usertag"]
    auth_keys.sort(key=lambda k: 0 if "icube.cloudide" in k else 1)
    print(f"Found {len(auth_keys)} auth keys: {auth_keys}")

    for key in auth_keys:
        raw = base64.b64decode(storage[key])
        if raw[:6] != b"tc\x05\x10\x00\x00":
            print(f"  [{key}] header mismatch: {raw[:6]!r}")
            continue
        km = raw[6:38]
        ct = raw[38:]
        inner = hashlib.sha512(km).digest()
        derived = hashlib.sha512(inner + salt).digest()
        dec = Cipher(algorithms.AES(derived[0:16]), modes.CBC(derived[16:32])).decryptor()
        try:
            padded = dec.update(ct) + dec.finalize()
            unp = PKCS7(128).unpadder()
            plain = unp.update(padded) + unp.finalize()
        except Exception as e:
            print(f"  [{key}] decrypt failed: {e}")
            continue
        obj = json.loads(plain[64:].decode("utf-8"))
        token = obj.get("token", "")
        if token.startswith("eyJ"):
            # Check expiry
            parts = token.split(".")
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            exp = payload.get("exp", 0)
            now = int(time.time())
            print(f"  [{key}] JWT exp={exp} ({time.ctime(exp)}), now={now} ({time.ctime(now)}), expired={exp<now}")
            return token
    raise RuntimeError("No valid JWT found in storage.json")


# ── 2. Generate temp token ──────────────────────────────────────────────────
def gen_temp_token(user_jwt: str) -> str:
    url = "https://api.trae.cn/cloudide/api/v3/trae/GenerateTempToken"
    trace_id = uuid.uuid4().hex
    req_id = str(uuid.uuid4())
    headers = {
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
    resp = requests.post(url, headers=headers, json={"IDEVersion": "0.1.48"}, timeout=30.0)
    print(f"GenerateTempToken status={resp.status_code}")
    if resp.status_code != 200:
        print(f"  body: {resp.text[:500]}")
        raise RuntimeError(f"GenerateTempToken failed: {resp.status_code}")
    data = resp.json()
    token = data["Result"]["Token"]
    print(f"  got temp token: {token[:60]}...")
    return token


# ── 3. Test super_completion_query ──────────────────────────────────────────
def test_super_completion(temp_token: str) -> None:
    url = "https://trae-api-cn.mchost.guru/api/ide/v1/super_completion_query"
    trace_id = uuid.uuid4().hex
    req_id = str(uuid.uuid4())
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
        "x-custom-trace-id": trace_id,
        "x-flow-traceparent": f"04-{trace_id}-{uuid.uuid4().hex[:16]}-01",
        "x-device-id": "3951005750868043",
        "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
        "x-device-brand": "PA-Agent",
        "x-device-type": "windows",
        "request-traffic-type": "prod",
        "x-request-id": req_id,
        "x-trae-request-id": req_id,
    }

    # Body format that TRAE actually uses (based on log analysis)
    body = {
        "query": "用中文说一句你好,只说一句",
        "model": "glm-5.2",
        "messages": [{"role": "user", "content": "用中文说一句你好,只说一句"}],
        "stream": True,
    }
    print(f"\n=== POST {url} ===")
    print(f"body: {body}")
    try:
        resp = requests.post(url, headers=headers, json=body, stream=True, timeout=60.0)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Error body: {resp.text[:1000]}")
            return
        line_count = 0
        content_chunks = []
        for line in resp.iter_lines():
            if line:
                line_str = line.decode("utf-8", errors="replace")
                print(f"  L{line_count}: {line_str[:300]}")
                # Try to extract content from SSE
                if line_str.startswith("data:"):
                    payload = line_str[5:].strip()
                    try:
                        evt = json.loads(payload)
                        # Look for content fields
                        if "choices" in evt:
                            for ch in evt["choices"]:
                                delta = ch.get("delta", {})
                                if "content" in delta and delta["content"]:
                                    content_chunks.append(delta["content"])
                        elif "content" in evt:
                            content_chunks.append(evt["content"])
                    except json.JSONDecodeError:
                        pass
                line_count += 1
                if line_count > 50:
                    print("  ...(truncated)")
                    break
        if content_chunks:
            print(f"\n>>> Extracted content: {''.join(content_chunks)}")
    except Exception as e:
        print(f"Exception: {e}")


# ── 4. Test llm_raw_chat (alternative endpoint) ─────────────────────────────
def test_llm_raw_chat(temp_token: str) -> None:
    url = "https://trae-api-cn.mchost.guru/api/ide/v1/llm_raw_chat"
    trace_id = uuid.uuid4().hex
    req_id = str(uuid.uuid4())
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
        "x-custom-trace-id": trace_id,
        "x-device-id": "3951005750868043",
        "x-machine-id": "12b6128fc28fd5c2be4c1e2446252ecb1bcd00499e8c14a5250309cf3a7ba6f5",
        "x-device-type": "windows",
        "request-traffic-type": "prod",
        "x-request-id": req_id,
        "x-trae-request-id": req_id,
    }
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "用中文说一句你好,只说一句"}]}
        ],
        "model": "glm-5.2",
        "function": "solo_agent_lite",
        "stream": True,
    }
    print(f"\n=== POST {url} ===")
    print(f"body keys: {list(body.keys())}")
    try:
        resp = requests.post(url, headers=headers, json=body, stream=True, timeout=60.0)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Error body: {resp.text[:1000]}")
            return
        line_count = 0
        content_chunks = []
        for line in resp.iter_lines():
            if line:
                line_str = line.decode("utf-8", errors="replace")
                print(f"  L{line_count}: {line_str[:300]}")
                if line_str.startswith("data:"):
                    payload = line_str[5:].strip()
                    if payload == "[DONE]":
                        continue
                    try:
                        evt = json.loads(payload)
                        if "choices" in evt:
                            for ch in evt["choices"]:
                                delta = ch.get("delta", {})
                                if "content" in delta and delta["content"]:
                                    content_chunks.append(delta["content"])
                                if "reasoning_content" in delta and delta["reasoning_content"]:
                                    print(f"    [reasoning] {delta['reasoning_content'][:200]}")
                    except json.JSONDecodeError:
                        pass
                line_count += 1
                if line_count > 80:
                    print("  ...(truncated)")
                    break
        if content_chunks:
            print(f"\n>>> Extracted content: {''.join(content_chunks)}")
    except Exception as e:
        print(f"Exception: {e}")


if __name__ == "__main__":
    print("=== Step 1: Extract user JWT from storage.json ===")
    user_jwt = get_user_jwt()
    print(f"User JWT: {user_jwt[:50]}...{user_jwt[-20:]}")

    print("\n=== Step 2: Generate temp token ===")
    temp_token = gen_temp_token(user_jwt)

    print("\n=== Step 3: Test super_completion_query ===")
    test_super_completion(temp_token)

    print("\n=== Step 4: Test llm_raw_chat ===")
    test_llm_raw_chat(temp_token)
