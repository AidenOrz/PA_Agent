"""Search for SSE streaming response format in Trae CN ai-agent logs."""
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")

# Search all ai-agent logs for streaming response patterns
for log_dir in sorted((BASE / "logs").iterdir()):
    if not log_dir.is_dir():
        continue
    for log_file in log_dir.rglob("ai-agent*stdout*.log"):
        try:
            data = log_file.read_bytes()
        except Exception:
            continue
        if len(data) > 200 * 1024 * 1024:
            continue
        
        # Search for streaming data patterns
        # The aha_net module logs OnData events with chunk data
        patterns = [
            (b"OnData", "OnData events"),
            (b"chunk", "chunk references"),
            (b"delta", "delta references"),
            (b"reasoning_content", "reasoning_content"),
            (b"reasoning_text", "reasoning_text"),
            (b'"text":"', "text field"),
            (b"event:msg", "event:msg"),
            (b"event:message", "event:message"),
            (b"event:delta", "event:delta"),
            (b"event:end", "event:end"),
            (b"event:error", "event:error"),
            (b"event:done", "event:done"),
            (b"data:{", "data:{ JSON"),
            (b'data:{"', 'data:{" JSON'),
            (b"content_block", "content_block"),
            (b"output_text", "output_text"),
            (b"message_delta", "message_delta"),
        ]
        
        found_any = False
        for pat, label in patterns:
            matches = list(re.finditer(re.escape(pat), data, re.IGNORECASE))
            if matches:
                found_any = True
                print(f"\n{log_file.relative_to(BASE)}: '{label}' - {len(matches)} matches")
                m = matches[0]
                start = max(0, m.start() - 200)
                end = min(len(data), m.end() + 600)
                snippet = data[start:end].decode("utf-8", errors="replace")
                print(f"  {snippet[:800]}")
        
        if found_any:
            break
    if found_any:
        break

# Also search for the actual response body of create_agent_task
print("\n\n=== Searching for create_agent_task response ===")
for log_dir in sorted((BASE / "logs").iterdir()):
    if not log_dir.is_dir():
        continue
    for log_file in log_dir.rglob("ai-agent*stdout*.log"):
        try:
            data = log_file.read_bytes()
        except Exception:
            continue
        if len(data) > 200 * 1024 * 1024:
            continue
        
        # Find create_agent_task calls
        idx = 0
        count = 0
        while True:
            idx = data.find(b"create_agent_task", idx)
            if idx == -1:
                break
            count += 1
            if count <= 1:
                # Get context after the call to see response
                end = min(len(data), idx + 5000)
                snippet = data[idx:end].decode("utf-8", errors="replace")
                # Look for response data
                if any(kw in snippet for kw in ["OnData", "chunk", "delta", "content", "response", "SSE", "stream"]):
                    print(f"\n{log_file.relative_to(BASE)} - create_agent_task at {idx}:")
                    # Find the relevant part
                    for kw in ["OnData", "chunk", "delta", "content", "SSE", "stream", "DONE", "EOF"]:
                        kw_idx = snippet.find(kw)
                        if kw_idx >= 0:
                            print(f"  ...{snippet[max(0,kw_idx-100):kw_idx+400]}...")
                            break
            idx += 1
            if count >= 3:
                break
        if count > 0:
            break
    if count > 0:
        break
