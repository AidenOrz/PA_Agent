"""Search for the iCubeAuthInfo decryption code in TRAE main.js."""
import re

p = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"
data = open(p, encoding="utf-8", errors="replace").read()

# Find all occurrences of iCubeAuthInfo and show surrounding context
# (looking for crypto/decrypt logic nearby)
matches = list(re.finditer(r"iCubeAuthInfo", data))
print(f"Found {len(matches)} occurrences of iCubeAuthInfo")

for i, m in enumerate(matches):
    start = max(0, m.start() - 500)
    end = min(len(data), m.end() + 2000)
    ctx = data[start:end]
    # Check if this context has crypto-related code
    has_crypto = any(kw in ctx.lower() for kw in [
        "crypt", "cipher", "aes", "decrypt", "key", "iv",
        "buffer", "prefix", "tc", "safe", "encrypt",
        "createDecipher", "createCipher", "fromBase64", "fromHex"
    ])
    if has_crypto:
        print(f"\n=== Match {i} at {m.start()} (has crypto keywords) ===")
        print(ctx[:2500])
        print("---")

# Also search for functions that read storage with iCubeAuthInfo prefix
print("\n\n=== Searching for getAuthInfo/readAuth functions ===")
for pat in [r"getAuthInfo", r"readAuth", r"getAuth\b", r"authInfo", r"getIcubeAuth", r"readIcubeAuth"]:
    for m in re.finditer(pat, data):
        start = max(0, m.start() - 200)
        end = min(len(data), m.end() + 500)
        print(f"\n--- {pat} at {m.start()} ---")
        print(data[start:end])
