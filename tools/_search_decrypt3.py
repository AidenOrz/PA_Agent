"""Find the decryption function near iCubeAuthInfo usage."""
import re

p = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"
data = open(p, encoding="utf-8", errors="replace").read()

# Search for crypto.createDecipheriv or createDecipher
for pat in [r"createDecipher", r"createCipher", r"safeStorage", r"decryptString", r"encryptString", r"Buffer\.from\(\[116"]:
    matches = list(re.finditer(pat, data))
    if matches:
        print(f"\n=== {pat}: {len(matches)} matches ===")
        for m in matches[:3]:
            start = max(0, m.start() - 150)
            end = min(len(data), m.end() + 300)
            print(f"--- at {m.start()} ---")
            print(data[start:end])
            print()

# Also search for the specific tc prefix check - could be "tc" as a string
# or 0x7463 or Buffer comparison
for pat in [r'"tc"', r"'tc'", r"0x74.*?0x63", r"\\x74\\x63", r"prefix.*?tc", r"tc.*?prefix"]:
    matches = list(re.finditer(pat, data))
    if matches:
        print(f"\n=== {pat}: {len(matches)} matches ===")
        for m in matches[:3]:
            start = max(0, m.start() - 200)
            end = min(len(data), m.end() + 200)
            print(f"--- at {m.start()} ---")
            print(data[start:end])
            print()
