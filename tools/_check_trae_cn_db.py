"""Check state.vscdb and config.db for auth tokens in Trae CN."""
import json
import sqlite3
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")

# 1. Check state.vscdb
print("=== state.vscdb ===")
vscdb_path = BASE / "User" / "globalStorage" / "state.vscdb"
if vscdb_path.exists():
    try:
        db = sqlite3.connect(str(vscdb_path))
        cur = db.cursor()
        cur.execute("SELECT key, length(value) FROM ItemTable WHERE key LIKE '%auth%' OR key LIKE '%token%' OR key LIKE '%cloudide%' OR key LIKE '%iCube%' OR key LIKE '%trae%' OR key LIKE '%credential%' OR key LIKE '%session%'")
        rows = cur.fetchall()
        print(f"Found {len(rows)} matching keys:")
        for k, v in rows:
            print(f"  {k}: value_len={v}")
        # Also check ALL keys
        cur.execute("SELECT key FROM ItemTable ORDER BY key")
        all_keys = [r[0] for r in cur.fetchall()]
        print(f"\nAll keys ({len(all_keys)}):")
        for k in all_keys:
            print(f"  {k}")
        db.close()
    except Exception as e:
        print(f"Error: {e}")

# 2. Check config.db (encrypted with MD5(nameShort))
print("\n=== config.db ===")
config_db = BASE / "Local Storage" / "config.db"
if config_db.exists():
    raw = config_db.read_bytes()
    print(f"Size: {len(raw)} bytes")
    print(f"First 32 bytes (hex): {raw[:32].hex()}")
    
    # Decrypt with MD5("Trae CN")
    name_short = "Trae CN"
    key = hashlib.md5(name_short.encode()).hexdigest().encode()
    iv = raw[:16]
    ct = raw[16:]
    try:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()
        pad_len = padded[-1]
        if 0 < pad_len <= 16:
            plain = padded[:-pad_len]
        else:
            plain = padded
        text = plain.decode("utf-8", errors="replace")
        print(f"Decrypted config.db ({len(text)} chars):")
        print(text[:2000])
        # Try to parse as JSON
        try:
            config = json.loads(text)
            print(f"\nParsed as JSON, keys: {list(config.keys())}")
            # Look for auth/token info
            for k, v in config.items():
                if isinstance(v, str) and len(v) > 60:
                    print(f"  {k}: {v[:80]}... (len={len(v)})")
                else:
                    print(f"  {k}: {v!r}")
        except json.JSONDecodeError:
            pass
    except Exception as e:
        print(f"Decryption failed: {e}")

# 3. Check Local Storage leveldb for auth tokens
print("\n=== Local Storage leveldb ===")
ldb_dir = BASE / "Local Storage" / "leveldb"
if ldb_dir.exists():
    import re
    JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")
    for f in sorted(ldb_dir.iterdir()):
        if f.is_file():
            try:
                data = f.read_bytes()
            except Exception:
                continue
            # Search for JWT tokens
            for m in JWT_RE.finditer(data):
                jwt = m.group().decode("ascii", errors="replace")
                print(f"  {f.name}: JWT found: {jwt[:60]}...")
            # Search for auth/token strings
            for pattern in [b"accessToken", b"access_token", b"refresh_token", b"authToken", b"icubeAuthInfo"]:
                if pattern.lower() in data.lower():
                    idx = data.lower().find(pattern.lower())
                    snippet = data[max(0,idx-50):idx+200].decode("utf-8", errors="replace")
                    print(f"  {f.name}: '{pattern.decode()}' found: {snippet[:200]}")
