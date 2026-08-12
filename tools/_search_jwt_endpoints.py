"""Find all Cloud-IDE-JWT endpoints and chat-related API calls."""
from pathlib import Path
import re

p = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\vs\workbench\workbench.desktop.main.solo-lite.js")
text = p.read_text(encoding="utf-8", errors="replace")

# Find all Cloud-IDE-JWT contexts with more surrounding text
print("=== Cloud-IDE-JWT usages ===")
for m in re.finditer(r"Cloud-IDE-JWT", text):
    idx = m.start()
    start = max(0, idx - 500)
    end = min(len(text), idx + 500)
    snippet = text[start:end].replace("\n", "\\n")
    print(f"\n--- @ {idx} ---")
    print(snippet)
    print()

# Find all URL patterns with /api/ or /trae/ or /cloudide/
print("\n=== API URL patterns ===")
for m in re.finditer(r'[\'"`](/[a-z]+/api/v\d+/[a-z_]+)', text):
    idx = m.start()
    start = max(0, idx - 100)
    end = min(len(text), idx + 200)
    snippet = text[start:end].replace("\n", "\\n")
    print(f"@ {idx}: {snippet}")
