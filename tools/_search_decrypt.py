"""Search TRAE main.js for the tc\x05 decryption logic."""
import re

p = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"
data = open(p, encoding="utf-8", errors="replace").read()
print("file size:", len(data))

patterns = [
    r"createDecipheriv",
    r"decryptValue",
    r"AES-256-CBC",
    r"aes-256-cbc",
    r"tc\\x05",
    r"\\x74\\x63\\x05",
    r"fromCrypto",
    r"safeStorage",
    r"decryptString",
    r"prefix.*tc",
]

for pat in patterns:
    matches = list(re.finditer(pat, data))
    if not matches:
        continue
    print(f"\n=== pattern: {pat} ({len(matches)} matches) ===")
    for m in matches[:3]:
        start = max(0, m.start() - 300)
        end = min(len(data), m.end() + 300)
        print(f"--- at {m.start()} ---")
        print(data[start:end])
        print()
