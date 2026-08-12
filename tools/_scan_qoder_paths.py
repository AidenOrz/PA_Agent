"""Scan QoderCN.exe binary for all /algo/ path patterns."""
import re

BIN = r"C:\Program Files\QoderCN\resources\app\resources\bin\x86_64_windows\QoderCN.exe"
with open(BIN, "rb") as f:
    data = f.read()

ascii_text = data.decode("ascii", errors="replace")

# Find all /algo/xxx paths
pattern = re.compile(r"/algo/[a-zA-Z0-9_/\-\.]{3,80}")
paths = {}
for m in pattern.finditer(ascii_text):
    p = m.group(0)
    if p not in paths:
        paths[p] = m.start()

print(f"=== Found {len(paths)} unique /algo/ paths ===")
for p in sorted(paths.keys()):
    print(f"  {p}  (@{paths[p]})")

print("\n\n=== All /api/v1/ paths ===")
pattern2 = re.compile(r"/api/v1/[a-zA-Z0-9_/\-\.]{3,80}")
paths2 = {}
for m in pattern2.finditer(ascii_text):
    p = m.group(0)
    if p not in paths2:
        paths2[p] = m.start()
for p in sorted(paths2.keys()):
    print(f"  {p}  (@{paths2[p]})")

print("\n\n=== All /api/v2/ paths ===")
pattern3 = re.compile(r"/api/v2/[a-zA-Z0-9_/\-\.]{3,80}")
paths3 = {}
for m in pattern3.finditer(ascii_text):
    p = m.group(0)
    if p not in paths3:
        paths3[p] = m.start()
for p in sorted(paths3.keys()):
    print(f"  {p}  (@{paths3[p]})")
