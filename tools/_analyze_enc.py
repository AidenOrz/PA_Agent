"""Analyze the tc\x05 encrypted value structure."""
import base64
import json
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN")
storage = json.loads(
    (BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8")
)

for key in (
    "iCubeAuthInfo://icube.cloudide",
    "iCubeAuthInfo://icube-dc:3951005750868043",
    "iCubeAuthInfo://usertag",
):
    val = storage.get(key, "")
    if not val:
        continue
    raw = base64.b64decode(val)
    print(f"\n=== {key} ===")
    print(f"  b64 length: {len(val)}")
    print(f"  raw length: {len(raw)}")
    print(f"  first 32 bytes (hex): {raw[:32].hex()}")
    print(f"  first 6 bytes: {raw[:6]}")
    # Check if bytes 6+ start with v10/v11 (Electron safeStorage)
    after_header = raw[6:]
    print(f"  bytes[6:9]: {after_header[:3]}")
    print(f"  bytes[6:9] hex: {after_header[:3].hex()}")

    # Also check the Local State os_crypt to see if there's a different key
    ls = json.loads((BASE / "Local State").read_text(encoding="utf-8"))
    os_crypt = ls.get("os_crypt", {})
    print(f"\n  os_crypt keys: {list(os_crypt.keys())}")
    for k, v in os_crypt.items():
        print(f"    {k}: {str(v)[:60]}...")
