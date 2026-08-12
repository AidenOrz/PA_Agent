"""Try multiple decryption approaches for tc\\x05 encrypted Trae CN tokens."""
import base64
import hashlib
import json
import ctypes
from ctypes import wintypes
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
storage = json.loads(
    (BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8")
)

enc_b64 = storage["iCubeAuthInfo://icube-dc:3951005750868043"]
raw = base64.b64decode(enc_b64)
print(f"Raw length: {len(raw)}")
print(f"Header (hex): {raw[:20].hex()}")
print(f"Header bytes: {list(raw[:20])}")

# DPAPI decryption helper
def dpapi_decrypt(blob: bytes) -> bytes | None:
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
        return None
    try:
        size = blob_out.cbData
        buf = ctypes.cast(blob_out.pbData, ctypes.POINTER(ctypes.c_ubyte * size))
        return bytes(buf.contents)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

# Get AES key from Local State (Electron safeStorage key)
local_state = json.loads((BASE / "Local State").read_text(encoding="utf-8"))
enc_key_b64 = local_state["os_crypt"]["encrypted_key"]
enc_key = base64.b64decode(enc_key_b64)
print(f"\nElectron key prefix: {enc_key[:5]}")
aes_key = dpapi_decrypt(enc_key[5:])
print(f"Electron AES key: {aes_key.hex()[:40]}...")

name_short = "Trae CN"
md5_key = hashlib.md5(name_short.encode()).hexdigest().encode()
print(f"MD5('{name_short}') as key: {md5_key.hex()}")

# Approach 1: tc\x05 header(6) + IV(16) + ciphertext, key=md5(nameShort)
print("\n=== Approach 1: header(6) + IV(16) + ct, key=md5(nameShort) ===")
try:
    iv = raw[6:22]
    ct = raw[22:]
    cipher = Cipher(algorithms.AES(md5_key), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    padded = dec.update(ct) + dec.finalize()
    print(f"  Decrypted (first 100): {padded[:100]}")
except Exception as e:
    print(f"  Failed: {e}")

# Approach 2: header(4) + IV(16) + ciphertext, key=md5(nameShort)
print("\n=== Approach 2: header(4) + IV(16) + ct, key=md5(nameShort) ===")
try:
    iv = raw[4:20]
    ct = raw[20:]
    cipher = Cipher(algorithms.AES(md5_key), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    padded = dec.update(ct) + dec.finalize()
    print(f"  Decrypted (first 100): {padded[:100]}")
except Exception as e:
    print(f"  Failed: {e}")

# Approach 3: Strip tc\x05 header, treat rest as Electron v10/v11 (AES-GCM)
print("\n=== Approach 3: strip header(6), then v10/v11 AES-GCM ===")
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    rest = raw[6:]
    print(f"  Rest prefix: {rest[:3]}")
    # Try if rest starts with v10
    if rest[:3] in (b"v10", b"v11"):
        nonce = rest[3:15]
        ct = rest[15:]
        plain = AESGCM(aes_key).decrypt(nonce, ct, None)
        print(f"  Decrypted: {plain[:100]}")
    else:
        # Maybe the whole thing after header is nonce(12)+ct for AES-GCM
        nonce = rest[:12]
        ct = rest[12:]
        plain = AESGCM(aes_key).decrypt(nonce, ct, None)
        print(f"  Decrypted (no v10): {plain[:100]}")
except Exception as e:
    print(f"  Failed: {e}")

# Approach 4: tc\x05 header(6) + nonce(12) + ct+tag, key=aes_key (Electron), AES-GCM
print("\n=== Approach 4: header(6) + nonce(12) + ct, key=Electron AES, AES-GCM ===")
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = raw[6:18]
    ct = raw[18:]
    plain = AESGCM(aes_key).decrypt(nonce, ct, None)
    print(f"  Decrypted: {plain[:100]}")
except Exception as e:
    print(f"  Failed: {e}")

# Approach 5: Try raw[6:] as DPAPI blob directly
print("\n=== Approach 5: raw[6:] as DPAPI blob ===")
try:
    rest = raw[6:]
    plain = dpapi_decrypt(rest)
    if plain:
        print(f"  DPAPI decrypted: {plain[:100]}")
    else:
        print("  DPAPI returned None")
except Exception as e:
    print(f"  Failed: {e}")

# Approach 6: header(6) + IV(16) + ct, key=Electron AES key (first 32 bytes)
print("\n=== Approach 6: header(6) + IV(16) + ct, key=Electron AES (32 bytes), CBC ===")
try:
    iv = raw[6:22]
    ct = raw[22:]
    key32 = aes_key[:32] if len(aes_key) >= 32 else aes_key
    cipher = Cipher(algorithms.AES(key32), modes.CBC(iv), backend=default_backend())
    dec = cipher.decryptor()
    padded = dec.update(ct) + dec.finalize()
    print(f"  Decrypted (first 100): {padded[:100]}")
except Exception as e:
    print(f"  Failed: {e}")

# Approach 7: The tc\x05\x10\x00\x00 might mean IV length = 0x10 = 16
# So: magic(2) + version(1) + iv_len(1=0x10) + reserved(2) + IV(16) + ct
# This is same as approach 1. Let me try with nameShort variations
print("\n=== Approach 7: try different nameShort values ===")
for name in ["Trae CN", "trae-cn", "Trae", "trae", "icube", "iCube",
             "TraeCN", "TRAE", "TRAE CN", "ICUBE", "trae_cn"]:
    try:
        iv = raw[6:22]
        ct = raw[22:]
        key = hashlib.md5(name.encode()).hexdigest().encode()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()
        # Check if result looks valid
        if all(b < 128 for b in padded[:20]):
            print(f"  nameShort='{name}': {padded[:80]}")
    except Exception:
        pass

# Approach 8: Maybe the key is the raw md5 digest (16 bytes) used as AES-128
print("\n=== Approach 8: AES-128-CBC with raw md5 digest (16 bytes) ===")
for name in ["Trae CN", "trae-cn", "Trae", "icube"]:
    try:
        iv = raw[6:22]
        ct = raw[22:]
        key16 = hashlib.md5(name.encode()).digest()  # 16 bytes raw
        cipher = Cipher(algorithms.AES(key16), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()
        if all(b < 128 for b in padded[:20]):
            print(f"  nameShort='{name}' (AES-128): {padded[:80]}")
    except Exception as e:
        pass
