"""Find doRequestWithStream payload construction and super_completion_query body."""
from pathlib import Path
import re

p = Path(r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\vs\workbench\workbench.desktop.main.solo-lite.js")
text = p.read_text(encoding="utf-8", errors="replace")

# Find doRequestWithStream and surrounding context (larger window)
idx = text.find("doRequestWithStream")
if idx >= 0:
    start = max(0, idx - 500)
    end = min(len(text), idx + 2000)
    snippet = text[start:end].replace("\n", "\\n")
    print("=== doRequestWithStream context ===")
    print(snippet)

# Find the payload construction method X(
# Look for "payload:await this.X" pattern
print("\n\n=== payload construction ===")
for m in re.finditer(r'payload\s*:\s*await\s+this\.(\w+)\s*\(', text):
    method_name = m.group(1)
    idx = m.start()
    start = max(0, idx - 200)
    end = min(len(text), idx + 500)
    snippet = text[start:end].replace("\n", "\\n")
    print(f"\n--- payload method: {method_name} @ {idx} ---")
    print(snippet)

# Search for "super_completion" to find request construction
print("\n\n=== super_completion references ===")
for m in re.finditer(r'super_completion', text):
    idx = m.start()
    start = max(0, idx - 500)
    end = min(len(text), idx + 500)
    snippet = text[start:end].replace("\n", "\\n")
    print(f"\n--- @ {idx} ---")
    print(snippet)

# Search for common chat request fields
print("\n\n=== Chat request field patterns ===")
for field in ["workspace_id", "project_id", "chat_id", "session_id", "message_id", "context_files"]:
    idx = text.find(field)
    if idx >= 0:
        start = max(0, idx - 200)
        end = min(len(text), idx + 300)
        snippet = text[start:end].replace("\n", "\\n")
        print(f"\n--- {field} @ {idx} ---")
        print(snippet)
