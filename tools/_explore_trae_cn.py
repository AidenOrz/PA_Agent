"""Explore Trae CN storage.json to find auth tokens and config."""
import base64
import json
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
storage_path = BASE / "User" / "globalStorage" / "storage.json"

storage = json.loads(storage_path.read_text(encoding="utf-8"))

print(f"=== storage.json: {len(storage)} keys ===\n")

# Look for auth/token/cloudide/icube/trae related keys
interesting_keywords = (
    "auth", "token", "cloudide", "icube", "trae", "supabase",
    "account", "login", "session", "credential", "user",
)
print("=== Interesting keys ===")
for key in sorted(storage.keys()):
    key_lower = key.lower()
    if any(kw in key_lower for kw in interesting_keywords):
        val = storage[key]
        if isinstance(val, str):
            print(f"  {key}: str len={len(val)} prefix={val[:40]!r}")
        else:
            print(f"  {key}: {type(val).__name__} = {str(val)[:80]!r}")

print("\n=== All keys (first 80 chars) ===")
for key in sorted(storage.keys()):
    val = storage[key]
    if isinstance(val, str) and len(val) > 200:
        print(f"  {key}: str len={len(val)}")
    elif isinstance(val, str):
        print(f"  {key}: {val[:80]!r}")
    else:
        print(f"  {key}: {str(val)[:80]!r}")

# Check the encrypted values - look for tc\x05 prefix (TRAE custom encryption)
print("\n=== Encrypted values (tc\\x05 prefix) ===")
for key in sorted(storage.keys()):
    val = storage[key]
    if not isinstance(val, str) or not val:
        continue
    try:
        raw = base64.b64decode(val)
        if raw[:3] == b"tc\x05":
            print(f"  {key}: tc05 encrypted, raw len={len(raw)}, header={raw[:6].hex()}")
    except Exception:
        pass

# Check for v10/v11 (Electron safeStorage)
print("\n=== Encrypted values (v10/v11 Electron) ===")
for key in sorted(storage.keys()):
    val = storage[key]
    if not isinstance(val, str) or not val:
        continue
    try:
        raw = base64.b64decode(val)
        if raw[:3] in (b"v10", b"v11"):
            print(f"  {key}: {raw[:3]} encrypted, raw len={len(raw)}")
    except Exception:
        pass
