"""Extract llm_utils_chat request body and response format from Trae CN logs."""
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")
log_file = BASE / "logs" / "20260615T172825" / "Modular" / "ai-agent_0_1781515705637_stdout.log"

data = log_file.read_bytes()
print(f"Log file size: {len(data)} bytes")

# Find llm_utils_chat calls and extract body/response
idx = 0
call_count = 0
while True:
    idx = data.find(b"llm_utils_chat", idx)
    if idx == -1:
        break
    call_count += 1
    
    # Get a large context window around the match
    start = max(0, idx - 500)
    end = min(len(data), idx + 3000)
    snippet = data[start:end].decode("utf-8", errors="replace")
    
    print(f"\n{'='*60}")
    print(f"=== llm_utils_chat call #{call_count} at position {idx} ===")
    print(f"{'='*60}")
    print(snippet[:3000])
    
    idx += 1
    if call_count >= 2:
        break

# Also search for the request body fields
print("\n\n=== Searching for request body fields ===")
for pattern in [b'"user_input"', b'"chat_history"', b'"intent_name"', b'"function"', b'"model_name"']:
    matches = list(re.finditer(pattern, data))
    if matches:
        print(f"\n'{pattern.decode()}': {len(matches)} matches")
        m = matches[0]
        start = max(0, m.start() - 200)
        end = min(len(data), m.end() + 500)
        snippet = data[start:end].decode("utf-8", errors="replace")
        print(f"  {snippet[:700]}")

# Search for the response format (SSE events)
print("\n\n=== Searching for SSE response format ===")
for pattern in [b'event:msg', b'event:message', b'"content":"', b'"reasoning":"', b'data:{', b'event:data', b'event:end', b'event:error']:
    matches = list(re.finditer(pattern, data, re.IGNORECASE))
    if matches:
        print(f"\n'{pattern.decode()}': {len(matches)} matches")
        m = matches[0]
        start = max(0, m.start() - 100)
        end = min(len(data), m.end() + 400)
        snippet = data[start:end].decode("utf-8", errors="replace")
        print(f"  {snippet[:500]}")
