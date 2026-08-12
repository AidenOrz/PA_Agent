"""Search TRAE main.js for tc\x05 decryption logic - more targeted patterns."""
import re

p = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"
data = open(p, encoding="utf-8", errors="replace").read()

# Search for tc prefix byte patterns and crypto near iCubeAuthInfo
patterns = [
    (r"116,.*?99,.*?5", "tc bytes 116,99,5"),
    (r"\[116,\s*99,\s*5\]", "tc bytes array"),
    (r'"tc".*?5', "tc string + 5"),
    (r"0x74.*?0x63.*?0x05", "tc hex"),
    (r"decrypt.*?[Aa]uth", "decrypt auth"),
    (r"[Aa]uth.*?decrypt", "auth decrypt"),
    (r"readAuthInfo", "readAuthInfo"),
    (r"getAuthInfo", "getAuthInfo"),
    (r"encryptValue", "encryptValue"),
    (r"safeStorage", "safeStorage"),
    (r"decryptString", "decryptString"),
    (r"encryptString", "encryptString"),
]

for pat, label in patterns:
    matches = list(re.finditer(pat, data, re.DOTALL))
    if not matches:
        print(f"NO MATCH: {label} ({pat})")
        continue
    print(f"\n=== {label}: {len(matches)} matches ===")
    for m in matches[:2]:
        start = max(0, m.start() - 200)
        end = min(len(data), m.end() + 200)
        print(f"--- at {m.start()} ---")
        print(data[start:end])
        print()
