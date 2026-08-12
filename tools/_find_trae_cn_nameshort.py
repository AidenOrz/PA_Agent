"""Find the nameShort value and tc\\x05 decryption logic in Trae CN."""
import re
from pathlib import Path

# Check product.json / package.json for nameShort
app_dir = Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app")
for fname in ["product.json", "package.json"]:
    p = app_dir / fname
    if p.exists():
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"=== {fname} ===")
        for key in ("nameShort", "nameLong", "applicationName", "dataFolderName", "productName", "version"):
            if key in data:
                print(f"  {key}: {data[key]!r}")
        print()

# Search for tc\x05 in main.js and workbench files
main_js = Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out\main.js")
data = main_js.read_text(encoding="utf-8", errors="replace")

# Search for the iCubeAuthInfo handling and tc prefix
patterns = [
    (r"iCubeAuthInfo", "iCubeAuthInfo"),
    (r"\\x74\\x63\\x05|tc\\\\x05", "tc escape"),
    (r"0x74.*0x63.*0x05", "0x74 0x63 0x05"),
    (r"safeStorage", "safeStorage"),
    (r"decryptString", "decryptString"),
    (r"encryptString", "encryptString"),
    (r"Buffer\.from\(.tc.", "Buffer.from tc"),
]

for pat, label in patterns:
    matches = list(re.finditer(pat, data, re.IGNORECASE))
    if matches:
        print(f"\n=== {label}: {len(matches)} matches in main.js ===")
        for m in matches[:2]:
            start = max(0, m.start() - 150)
            end = min(len(data), m.end() + 300)
            print(f"--- at position {m.start()} ---")
            print(data[start:end])
            print()

# Also search the workbench file for the tc\x05 decryption
wb_dir = Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out\vs\workbench")
if wb_dir.exists():
    for wb_file in wb_dir.rglob("*.js"):
        try:
            wb_data = wb_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Search for tc\x05 or iCubeAuthInfo
        for pat in [r"iCubeAuthInfo", r"safeStorage", r"decryptString"]:
            matches = list(re.finditer(pat, wb_data, re.IGNORECASE))
            if matches:
                print(f"\n=== {pat}: {len(matches)} matches in {wb_file.name} ===")
                for m in matches[:2]:
                    start = max(0, m.start() - 200)
                    end = min(len(wb_data), m.end() + 400)
                    print(f"--- at position {m.start()} ---")
                    print(wb_data[start:end])
                    print()
                break  # Only need first file with matches
