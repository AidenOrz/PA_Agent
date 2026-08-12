"""Scan QoderCN.exe for HTTP header strings to discover auth header names."""
from __future__ import annotations

import re
import sys
from pathlib import Path

BINARY = Path(r"C:\Program Files\QoderCN\resources\app\resources\bin\x86_64_windows\QoderCN.exe")

# Patterns to look for.
PATTERNS = [
    rb"Authorization",
    rb"Bearer\s",
    rb"X-[A-Z][a-zA-Z0-9-]+",
    rb"x-[a-z][a-z0-9-]+",
    rb"umid",
    rb"UMID",
    rb"machine[-_]?[Tt]oken",
    rb"machine[-_]?[Ii]d",
    rb"device[-_]?[Ii]d",
    rb"client[-_]?[Ii]d",
    rb"chat/completions",
    rb"/api/v1/[a-z/_-]+",
    rb"/v1/chat/completions",
    rb"/v1/models",
    rb"openapi\.qoder",
    rb"gateway\.qoder",
]


def main() -> int:
    print(f"Scanning: {BINARY}")
    print(f"  size: {BINARY.stat().st_size:,} bytes")
    data = BINARY.read_bytes()

    for pat in PATTERNS:
        rx = re.compile(pat)
        matches = rx.findall(data)
        if not matches:
            continue
        # Decode and dedupe.
        seen: set[str] = set()
        unique: list[str] = []
        for m in matches[:200]:
            try:
                s = m.decode("utf-8", errors="ignore") if isinstance(m, bytes) else str(m)
            except Exception:
                continue
            if s and s not in seen:
                seen.add(s)
                unique.append(s)
        print(f"\n[{pat.decode('utf-8', errors='ignore')}]  {len(matches)} hits, {len(unique)} unique")
        for s in unique[:25]:
            print(f"  {s}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
