"""Find context around chat/completions and Cosy-MachineToken in QoderCN.exe."""
from __future__ import annotations

import re
import sys
from pathlib import Path

BINARY = Path(r"C:\Program Files\QoderCN\resources\app\resources\bin\x86_64_windows\QoderCN.exe")
data = BINARY.read_bytes()


def find_context(pattern: bytes, ctx_before: int = 200, ctx_after: int = 200, limit: int = 10) -> None:
    print(f"\n=== {pattern.decode('utf-8', errors='ignore')} ===")
    rx = re.compile(re.escape(pattern))
    matches = list(rx.finditer(data))
    print(f"  {len(matches)} matches")
    seen: set[int] = set()
    for m in matches[:limit]:
        if m.start() in seen:
            continue
        seen.add(m.start())
        start = max(0, m.start() - ctx_before)
        end = min(len(data), m.end() + ctx_after)
        chunk = data[start:end]
        # Render nulls as separators, others as printable.
        s = chunk.decode("utf-8", errors="replace")
        clean = "".join(c if 32 <= ord(c) < 127 else "│" for c in s)
        clean = re.sub(r"│{2,}", "│", clean)
        print(f"  @{m.start()}: {clean}")


find_context(b"chat/completions", 200, 200, 5)
find_context(b"Cosy-MachineToken", 150, 300, 5)
find_context(b"Cosy-Key", 100, 300, 5)
find_context(b"Cosy-Date", 100, 300, 5)
find_context(b"task/execute", 150, 250, 5)
find_context(b"task/create", 150, 250, 5)
find_context(b"auth/status", 150, 250, 3)
# Look for HTTP paths.
find_context(b"/chat/completions", 80, 80, 5)
find_context(b"chatCompletions", 80, 200, 5)
find_context(b"ChatCompletions", 80, 200, 5)
