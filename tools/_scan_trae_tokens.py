"""Scan TRAE Work CN local storage for fresh IDE JWTs and refresh tokens.

One-off diagnostic used while wiring up the openclaw_twc connector.
"""
import base64
import os
import re

BASE = r"C:\Users\Administrator\AppData\Roaming\Trae CN"
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")
REFRESH_RE = re.compile(rb"refresh[_a-z]*[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-.]{40,})", re.I)

hits = []
for root, _dirs, files in os.walk(BASE):
    for f in files:
        p = os.path.join(root, f)
        try:
            if os.path.getsize(p) > 8 * 1024 * 1024:
                continue
            data = open(p, "rb").read()
        except OSError:
            continue
        for m in JWT_RE.finditer(data):
            s = m.group().decode("ascii", "ignore")
            try:
                parts = s.split(".")
                pad = parts[1] + "=" * (-len(parts[1]) % 4)
                payload = base64.urlsafe_b64decode(pad)
                if b'"iss":"trae"' in payload or b"trae" in payload:
                    hits.append((p, "JWT", s[:50] + "...", len(s)))
            except Exception:
                pass
        for m in REFRESH_RE.finditer(data):
            hits.append((p, "REFRESH", m.group(1).decode("ascii", "ignore")[:40], 0))

seen = set()
for p, kind, s, l in hits:
    key = (p, s)
    if key in seen:
        continue
    seen.add(key)
    print(f"{kind}\t{os.path.relpath(p, BASE)}\t{s}\tlen={l}")
print(f"---total hits: {len(hits)}")
