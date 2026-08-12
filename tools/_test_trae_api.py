"""Decrypt TRAE SOLO CN cloudide token and test the llm_utils_chat API."""
import base64
import ctypes
import json
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN")


def dpapi_decrypt(blob: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    buf_in = (ctypes.c_ubyte * len(blob))(*blob)
    blob_in = DATA_BLOB(len(blob), buf_in)
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)
    )
    if not ok:
        raise RuntimeError("DPAPI CryptUnprotectData failed")
    try:
        size = blob_out.cbData
        buf = ctypes.cast(blob_out.pbData, ctypes.POINTER(ctypes.c_ubyte * size))
        return bytes(buf.contents)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def get_aes_key() -> bytes:
    ls = json.loads((BASE / "Local State").read_text(encoding="utf-8"))
    enc_key_b64 = ls.get("os_crypt", {}).get("encrypted_key", "")
    enc_key = base64.b64decode(enc_key_b64)
    assert enc_key.startswith(b"DPAPI"), "encrypted_key doesn't start with DPAPI"
    return dpapi_decrypt(enc_key[5:])


def decrypt_value(aes_key: bytes, enc_b64: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    enc = base64.b64decode(enc_b64)
    # v10 prefix (3 bytes) + nonce (12 bytes) + ciphertext+tag
    assert enc[:3] in (b"v10", b"v11"), f"unknown prefix: {enc[:3]}"
    nonce = enc[3:15]
    ciphertext = enc[15:]
    plain = AESGCM(aes_key).decrypt(nonce, ciphertext, None)
    return plain.decode("utf-8", errors="replace")


def get_cloudide_token() -> str:
    aes_key = get_aes_key()
    storage = json.loads(
        (BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8")
    )
    enc_token = storage.get("iCubeAuthInfo://icube.cloudide", "")
    if not enc_token:
        raise RuntimeError("iCubeAuthInfo://icube.cloudide not found in storage.json")
    return decrypt_value(aes_key, enc_token)


def get_device_info() -> dict:
    env_path = BASE / "ModularData" / "ckg_server" / "local_env.json"
    env = json.loads(env_path.read_text(encoding="utf-8"))
    return {
        "device_id": env.get("device_id", ""),
        "machine_id": (
            json.loads(
                (BASE / "User" / "globalStorage" / "storage.json").read_text(
                    encoding="utf-8"
                )
            ).get("telemetry.machineId", "")
        ),
    }


def test_llm_utils_chat(token: str, device_info: dict) -> None:
    import httpx

    url = "https://trae-api-cn.mchost.guru/api/agent/v3/llm_utils_chat"
    trace_id = uuid.uuid4().hex
    request_id = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "x-app-id": "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8",
        "x-app-version": "default",
        "x-app-version-code": "20260806",
        "x-ide-version": "0.1.48",
        "x-ide-version-code": "20260806",
        "x-ide-version-type": "stable",
        "x-custom-trace-id": trace_id,
        "x-flow-traceparent": f"04-{trace_id}-{uuid.uuid4().hex[:16]}-01",
        "x-device-id": device_info["device_id"],
        "x-machine-id": device_info["machine_id"],
        "x-device-brand": "MS-7D48",
        "x-device-cpu": "Intel",
        "x-device-type": "windows",
        "x-os-version": "Windows 10 Pro",
        "request-traffic-type": "prod",
        "x-request-id": request_id,
        "x-trae-request-id": request_id,
        "Authorization": f"Bearer {token}",
    }

    # Try a minimal request body
    payload = {
        "user_input": "Say hello in one sentence.",
        "model_name": "glm-5.1",
        "intent_name": "chat",
        "chat_history": [],
        "function": "utils",
    }

    print(f"\n=== POST {url} ===")
    print(f"Token prefix: {token[:40]}...")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)[:200]}")

    try:
        with httpx.stream(
            "POST", url, headers=headers, json=payload, timeout=30.0
        ) as resp:
            print(f"Status: {resp.status_code}")
            print(f"Response headers: {dict(resp.headers)[:200] if hasattr(resp.headers, '__getitem__') else ''}")
            line_count = 0
            for line in resp.iter_lines():
                if line:
                    print(f"  SSE: {line[:300]}")
                    line_count += 1
                    if line_count > 30:
                        print("  ... (truncated)")
                        break
    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    print("=== Decrypting cloudide token ===")
    token = get_cloudide_token()
    print(f"Token length: {len(token)}")
    print(f"Token prefix: {token[:60]}...")

    print("\n=== Device info ===")
    dev = get_device_info()
    print(f"Device ID: {dev['device_id']}")
    print(f"Machine ID: {dev['machine_id']}")

    test_llm_utils_chat(token, dev)
