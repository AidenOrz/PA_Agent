"""Check iCubeServerData and search for tc\\x05 encryption in workbench files."""
import json
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
storage = json.loads(
    (BASE / "User" / "globalStorage" / "storage.json").read_text(encoding="utf-8")
)

# 1. Check the unencrypted iCubeServerData
server_data = storage.get("iCubeServerData://icube.cloudide", "")
print("=== iCubeServerData://icube.cloudide ===")
if server_data:
    try:
        data = json.loads(server_data)
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    except json.JSONDecodeError:
        print(f"Raw: {server_data[:500]}")

# 2. Search workbench files for tc\x05 or iCubeAuthInfo encryption
print("\n=== Searching workbench files for encryption logic ===")
wb_files = list(Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out\vs\workbench").rglob("*.js"))
print(f"Found {len(wb_files)} workbench JS files")

for wb_file in wb_files:
    try:
        data = wb_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    # Search for iCubeAuthInfo usage
    if "iCubeAuthInfo" in data:
        matches = list(re.finditer(r"iCubeAuthInfo", data))
        print(f"\n  {wb_file.name}: {len(matches)} iCubeAuthInfo matches")
        for m in matches[:3]:
            start = max(0, m.start() - 300)
            end = min(len(data), m.end() + 500)
            print(f"  --- at {m.start()} ---")
            print(data[start:end])
            print()

# 3. Search for "tc" prefix in encryption context across ALL js files
print("\n=== Searching for 'tc' encryption prefix ===")
out_dir = Path(r"C:\Users\Administrator\AppData\Local\Programs\Trae CN\resources\app\out")
for js_file in out_dir.rglob("*.js"):
    try:
        data = js_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    # Search for patterns like "tc" + encrypt or prefix + "tc"
    for pat in [r'\.tc\b.*encrypt', r'encrypt.*\.tc\b', r'"tc".*encrypt', r'prefix.*"tc"']:
        matches = list(re.finditer(pat, data, re.IGNORECASE))
        if matches:
            print(f"\n  {js_file.relative_to(out_dir)}: pattern '{pat}' - {len(matches)} matches")
            for m in matches[:1]:
                start = max(0, m.start() - 200)
                end = min(len(data), m.end() + 400)
                print(f"  {data[start:end][:600]}")
