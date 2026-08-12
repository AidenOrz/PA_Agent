"""Search for tc\\x05 prefix handling in Trae CN workbench files."""
import re
from pathlib import Path

base = Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out")

# Search all .js files for tc\x05 pattern or the encryption prefix handling
# The header is 0x74 0x63 0x05 (tc\x05)
search_patterns = [
    (r'"tc\\x05"', "tc\\x05 string"),
    (r"'tc\\x05'", "tc\\x05 single"),
    (r"\\x74\\x63\\x05", "\\x74\\x63\\x05"),
    (r"0x74,\s*0x63,\s*0x05", "0x74,0x63,0x05 hex array"),
    (r"\[116,\s*99,\s*5\]", "[116,99,5] decimal"),
    (r"Buffer\.from\(.tc.", "Buffer.from tc"),
    (r"prefix.*tc|tc.*prefix", "prefix tc"),
    (r"iCubeEncrypt|iCubeDecrypt", "iCubeEncrypt/Decrypt"),
    (r"encryptAuthInfo|decryptAuthInfo", "encryptAuthInfo"),
    (r"tcEncrypt|tcDecrypt", "tcEncrypt/Decrypt"),
]

found_files = set()
for js_file in base.rglob("*.js"):
    try:
        data = js_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for pat, label in search_patterns:
        matches = list(re.finditer(pat, data, re.IGNORECASE))
        if matches and js_file not in found_files:
            found_files.add(js_file)
            print(f"\n=== {label}: {len(matches)} matches in {js_file.name} ===")
            for m in matches[:2]:
                start = max(0, m.start() - 300)
                end = min(len(data), m.end() + 500)
                print(f"--- at position {m.start()} ---")
                print(data[start:end])
                print()
            break

if not found_files:
    print("No tc\\x05 patterns found. Searching for the iCubeAuthInfo write/read logic...")
    # Search for where iCubeAuthInfo values are stored/read
    for js_file in base.rglob("*.js"):
        try:
            data = js_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "iCubeAuthInfo" in data:
            matches = list(re.finditer(r"iCubeAuthInfo", data))
            if matches:
                print(f"\n=== iCubeAuthInfo in {js_file.name}: {len(matches)} matches ===")
                for m in matches[:3]:
                    start = max(0, m.start() - 200)
                    end = min(len(data), m.end() + 400)
                    print(f"--- at position {m.start()} ---")
                    print(data[start:end])
                    print()
