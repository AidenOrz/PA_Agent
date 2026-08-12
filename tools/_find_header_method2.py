"""Search main.js for auth header names."""
import re

JS_PATH = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"

with open(JS_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# Search for the actual header construction using these names
for name in ['x-cloudide-token', 'ideusertoken', 'userjwt', '"token"']:
    matches = list(re.finditer(re.escape(name), content))
    print(f"=== {name}: {len(matches)} matches ===")
    for m in matches[:8]:
        pos = m.start()
        s = content[max(0, pos - 100):pos + 150]
        print(f"  At {pos}: {repr(s)}")
    print()
