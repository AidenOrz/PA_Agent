"""Search ALL js files in TRAE out/ for tc\x05 decryption patterns."""
import os
import re

base = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out"
patterns = [
    r"116.*?99.*?5",        # tc\x05 as byte array
    r"\\x74\\x63\\x05",     # tc\x05 as escaped string
    r"746305",              # hex
    r"createDecipheriv",    # Node.js crypto
    r"createDecipher",
    r"safeStorage",
    r"decryptString",
    r"encryptString",
    r"fromCrypto",
    r"tc\\\\x05",
]

for root, dirs, files in os.walk(base):
    for f in files:
        if not f.endswith(".js"):
            continue
        p = os.path.join(root, f)
        try:
            if os.path.getsize(p) > 50 * 1024 * 1024:
                continue
            data = open(p, encoding="utf-8", errors="replace").read()
        except:
            continue
        for pat in patterns:
            for m in re.finditer(pat, data):
                start = max(0, m.start() - 200)
                end = min(len(data), m.end() + 200)
                snippet = data[start:end]
                # Only print if it looks crypto-related
                if any(kw in snippet.lower() for kw in ["crypt", "cipher", "aes", "decrypt", "tc", "safe", "key", "iv", "prefix"]):
                    rel = os.path.relpath(p, base)
                    print(f"\n=== {rel} at {m.start()} pattern={pat} ===")
                    print(snippet)
                    print()
