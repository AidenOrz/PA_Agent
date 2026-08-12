"""Search main.js for the header construction method used by generateTempToken."""
import re

JS_PATH = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"

with open(JS_PATH, "r", encoding="utf-8") as f:
    content = f.read()

idx = content.find("generateTempToken")
chunk = content[max(0, idx - 15000):idx + 5000]

# Search for header-related patterns
patterns = [
    r"Authorization",
    r"Cookie",
    r'headers\s*=\s*\{',
    r"x-",
    r"this\.m\s*=",
    r"\bm\s*\(",
]

for pat in patterns:
    matches = list(re.finditer(pat, chunk))
    print(f"=== Pattern: {pat} - {len(matches)} matches ===")
    for m in matches[:5]:
        pos = m.start()
        s = chunk[max(0, pos - 80):pos + 150]
        print(f"  At {pos}: {repr(s)}")
    print()
