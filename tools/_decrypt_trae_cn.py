"""Decrypt Trae CN tc\\x05 encrypted values to find auth tokens."""
import base64
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
storage = json.loads(
    (BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8")
)


def decrypt_tc05(enc_b64: str, name_short: str) -> str | None:
    """Try to decrypt a tc05 value with the given name_short as key seed."""
    try:
        raw = base64.b64decode(enc_b64)
        if raw[:6] != b"tc\x05\x10\x00\x00":
            return None
        iv = raw[6:22]
        ciphertext = raw[22:]
        key = hashlib.md5(name_short.encode()).hexdigest().encode()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        pad_len = padded[-1]
        if pad_len == 0 or pad_len > 16:
            return None
        plain = padded[:-pad_len]
        # Validate it's valid UTF-8 (auth tokens are JSON or JWT strings)
        return plain.decode("utf-8")
    except Exception as exc:
        return None


# Candidate product names for key derivation
candidates = [
    "Trae CN",
    "TRAE CN",
    "trae-cn",
    "Trae",
    "trae",
    "icube",
    "iCube",
    "ICUBE",
    "trae_cn",
    "TraeCN",
    "TRAE_CN",
]

enc_token = storage.get("iCubeAuthInfo://icube-dc:3951005750868043", "")
print(f"Encrypted token (iCube-dc): len={len(enc_token)}")

for name in candidates:
    result = decrypt_tc05(enc_token, name)
    if result is not None:
        print(f"\n=== SUCCESS with name_short={name!r} ===")
        print(f"Decrypted length: {len(result)}")
        print(f"First 200 chars: {result[:200]}")
        # Try to parse as JSON
        try:
            obj = json.loads(result)
            print(f"\nParsed as JSON, keys: {list(obj.keys()) if isinstance(obj, dict) else type(obj)}")
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and len(v) > 60:
                        print(f"  {k}: {v[:60]}... (len={len(v)})")
                    else:
                        print(f"  {k}: {v!r}")
        except json.JSONDecodeError:
            # Maybe it's a JWT
            if result.startswith("eyJ"):
                print(f"\nLooks like a JWT token: {result[:80]}...")
            else:
                print(f"\nNot JSON, not JWT. Raw: {result[:120]!r}")
        break
else:
    print("\n=== All name candidates failed ===")
    print("Trying brute force with common patterns...")
    # Try variations
    for name in ["TRAE", "Trae Work CN", "TRAE WORK CN", "trae work cn", "trae-work-cn"]:
        result = decrypt_tc05(enc_token, name)
        if result is not None:
            print(f"  SUCCESS with {name!r}: {result[:100]}")
            break
