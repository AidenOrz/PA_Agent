"""Search Trae CN main.js for the tc\\x05 decryption logic and key derivation."""
import re
from pathlib import Path

# Trae CN main.js location
main_js = Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out\main.js")

if not main_js.exists():
    print(f"main.js not found at {main_js}")
    # Try alternative locations
    for alt in [
        Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out\vs\code\electron-main\main.js"),
    ]:
        if alt.exists():
            main_js = alt
            print(f"Found at: {main_js}")
            break

data = main_js.read_text(encoding="utf-8", errors="replace")
print(f"main.js size: {len(data)} chars")

# Search for the tc\x05 header pattern (tc + 0x05)
# The header bytes are: 0x74 0x63 0x05 (tc\x05)
patterns = [
    (r"createDecipheriv", "createDecipheriv"),
    (r"Buffer\.from\(\[0x74,\s*0x63,\s*0x05\]", "Buffer.from([0x74,0x63,0x05])"),
    (r"\\x74\\x63\\x05", "tc\\x05 string"),
    (r"tc\\x05", "tc\\x05"),
    (r"nameShort", "nameShort"),
    (r"aes-256-cbc", "aes-256-cbc"),
    (r"createHash\(.md5.\)", "md5 hash"),
    (r"md5\(", "md5("),
    (r"productName", "productName"),
]

for pat, label in patterns:
    matches = list(re.finditer(pat, data, re.IGNORECASE))
    if matches:
        print(f"\n=== {label}: {len(matches)} matches ===")
        for m in matches[:3]:
            start = max(0, m.start() - 200)
            end = min(len(data), m.end() + 300)
            print(f"--- at position {m.start()} ---")
            print(data[start:end])
            print()
