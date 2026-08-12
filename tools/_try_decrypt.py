"""Try multiple decryption approaches for tc\x05 values."""
import base64, ctypes, hashlib, json, sys
from ctypes import wintypes
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN")
storage = json.loads((BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8"))
enc_b64 = storage["iCubeAuthInfo://icube.cloudide"]
raw = base64.b64decode(enc_b64)
print(f"raw[:6]: {raw[:6]}")
print(f"raw len: {len(raw)}")

# Get DPAPI-decrypted Electron AES key
def dpapi_decrypt(blob: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buf_in = (ctypes.c_ubyte * len(blob))(*blob)
    blob_in = DATA_BLOB(len(blob), buf_in)
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)
    )
    if not ok:
        raise RuntimeError("DPAPI failed")
    try:
        size = blob_out.cbData
        buf = ctypes.cast(blob_out.pbData, ctypes.POINTER(ctypes.c_ubyte * size))
        return bytes(buf.contents)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

ls = json.loads((BASE / "Local State").read_text(encoding="utf-8"))
enc_key_b64 = ls["os_crypt"]["encrypted_key"]
enc_key = base64.b64decode(enc_key_b64)
assert enc_key.startswith(b"DPAPI")
electron_aes_key = dpapi_decrypt(enc_key[5:])
print(f"Electron AES key len: {len(electron_aes_key)}")  # Should be 32 bytes

# The tc\x05 format: 6-byte header + 16-byte IV + ciphertext
header = raw[:6]
iv = raw[6:22]
ciphertext = raw[22:]
print(f"header: {header.hex()}")
print(f"iv: {iv.hex()}")
print(f"ciphertext len: {len(ciphertext)}")

# Approach 1: AES-CBC with Electron key (32 bytes)
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    cipher = Cipher(algorithms.AES(electron_aes_key), modes.CBC(iv), backend=default_backend())
    d = cipher.decryptor()
    padded = d.update(ciphertext) + d.finalize()
    pad_len = padded[-1]
    if 1 <= pad_len <= 16:
        plain = padded[:-pad_len].decode("utf-8", errors="replace")
        print(f"Approach 1 (AES-CBC + Electron key): SUCCESS")
        print(f"  plain[:100]: {plain[:100]}")
    else:
        print(f"Approach 1: bad padding {pad_len}")
except Exception as e:
    print(f"Approach 1: {e}")

# Approach 2: AES-GCM with Electron key (like v10 format, but custom header)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    # Maybe IV is 12 bytes and rest is ciphertext+tag
    iv12 = raw[6:18]
    ct_tag = raw[18:]
    plain = AESGCM(electron_aes_key).decrypt(iv12, ct_tag, None)
    print(f"Approach 2 (AES-GCM 12-byte IV + Electron key): SUCCESS")
    print(f"  plain[:100]: {plain[:100]}")
except Exception as e:
    print(f"Approach 2: {e}")

# Approach 3: AES-GCM with 16-byte IV (non-standard)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    # AES-GCM with 16-byte IV
    ct_tag = raw[22:]
    plain = AESGCM(electron_aes_key).decrypt(iv, ct_tag, None)
    print(f"Approach 3 (AES-GCM 16-byte IV + Electron key): SUCCESS")
    print(f"  plain[:100]: {plain[:100]}")
except Exception as e:
    print(f"Approach 3: {e}")

# Approach 4: Maybe header is tc\x05 + 4-byte length, then v10 format
try:
    after_header = raw[6:]
    if after_header[:3] in (b"v10", b"v11"):
        print(f"Approach 4: found {after_header[:3]} after tc\x05 header")
        nonce = after_header[3:15]
        ct = after_header[15:]
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        plain = AESGCM(electron_aes_key).decrypt(nonce, ct, None)
        print(f"  SUCCESS: {plain[:100]}")
    else:
        print(f"Approach 4: after header = {after_header[:6].hex()} (not v10/v11)")
except Exception as e:
    print(f"Approach 4: {e}")

# Approach 5: machineId as key (MD5 hexdigest = 32 bytes)
machine_id = storage.get("telemetry.machineId", "")
print(f"\nmachineId: {machine_id}")
key5 = hashlib.md5(machine_id.encode()).hexdigest().encode()
try:
    cipher = Cipher(algorithms.AES(key5), modes.CBC(iv), backend=default_backend())
    d = cipher.decryptor()
    padded = d.update(ciphertext) + d.finalize()
    pad_len = padded[-1]
    if 1 <= pad_len <= 16:
        plain = padded[:-pad_len].decode("utf-8", errors="replace")
        print(f"Approach 5 (MD5(machineId) AES-CBC): SUCCESS")
        print(f"  plain[:100]: {plain[:100]}")
    else:
        print(f"Approach 5: bad padding {pad_len}")
except Exception as e:
    print(f"Approach 5: {e}")

# Approach 6: SHA256(machineId) as key (32 bytes)
key6 = hashlib.sha256(machine_id.encode()).digest()
try:
    cipher = Cipher(algorithms.AES(key6), modes.CBC(iv), backend=default_backend())
    d = cipher.decryptor()
    padded = d.update(ciphertext) + d.finalize()
    pad_len = padded[-1]
    if 1 <= pad_len <= 16:
        plain = padded[:-pad_len].decode("utf-8", errors="replace")
        print(f"Approach 6 (SHA256(machineId) AES-CBC): SUCCESS")
        print(f"  plain[:100]: {plain[:100]}")
    else:
        print(f"Approach 6: bad padding {pad_len}")
except Exception as e:
    print(f"Approach 6: {e}")
