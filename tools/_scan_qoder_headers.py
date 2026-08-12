"""Search QoderCN.exe for context around auth headers and chat endpoint."""
from __future__ import annotations

import re
import sys
from pathlib import Path

BINARY = Path(r"C:\Program Files\QoderCN\resources\app\resources\bin\x86_64_windows\QoderCN.exe")

# Targeted patterns with surrounding context.
TARGETS = [
    # Auth header names containing "umid" or "machine" or "cosy".
    rb"[A-Za-z-]*[Uu]mid[A-Za-z-]*",
    rb"[Aa]uthorization[\x00-\xff]{0,80}",
    rb"[Cc]osy-[A-Z][a-zA-Z0-9-]+",
    rb"x-gw-[a-z-]+",
    rb"x-model-[a-z-]+",
    rb"x-fag-[a-z-]+",
    rb"x-dashscope-[a-z-]+",
    rb"x-qoder-[a-z-]+",
    # Endpoint paths.
    rb"/api/v1/chat[a-z/_-]*",
    rb"/v1/chat[a-z/_-]*",
    rb"/api/v1/models?",
    rb"/api/v1/inference[a-z/_-]*",
    rb"/api/v1/agent[a-z/_-]*",
]


def scan(data: bytes, pat: bytes, limit: int = 30) -> list[str]:
    """Return up to `limit` unique printable strings containing the pattern."""
    rx = re.compile(pat)
    seen: set[str] = set()
    out: list[str] = []
    for m in rx.finditer(data):
        s = m.group().decode("utf-8", errors="replace")
        # Clean: keep printable ASCII only.
        clean = "".join(c if 32 <= ord(c) < 127 else "·" for c in s)
        if clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def scan_with_context(data: bytes, pat: bytes, ctx: int = 80, limit: int = 20) -> list[str]:
    """Print each match with surrounding printable context."""
    rx = re.compile(pat)
    out: list[str] = []
    seen_pos: set[int] = set()
    for m in rx.finditer(data):
        if m.start() in seen_pos:
            continue
        seen_pos.add(m.start())
        start = max(0, m.start() - ctx)
        end = min(len(data), m.end() + ctx)
        chunk = data[start:end]
        # Render as printable, splitting on null bytes.
        s = chunk.decode("utf-8", errors="replace")
        clean = "".join(c if 32 <= ord(c) < 127 else "│" for c in s)
        # Collapse multiple separators.
        clean = re.sub(r"│{2,}", "│", clean)
        out.append(f"@{m.start():>10}: {clean}")
        if len(out) >= limit:
            break
    return out


def main() -> int:
    print(f"Scanning: {BINARY}")
    data = BINARY.read_bytes()

    for pat in TARGETS:
        print(f"\n=== Pattern: {pat.decode('utf-8', errors='ignore')} ===")
        results = scan_with_context(data, pat, ctx=80, limit=15)
        if not results:
            print("  (no matches)")
        for r in results:
            print(f"  {r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
