"""Search for iCubeAuthInfo:// usage to find the actual decryption code."""
import re

# Search all JS files for iCubeAuthInfo:// pattern
base = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out"
for root, dirs, files in __import__("os").walk(base):
    for f in files:
        if not f.endswith(".js"):
            continue
        p = __import__("os").path.join(root, f)
        try:
            if __import__("os").path.getsize(p) > 100 * 1024 * 1024:
                continue
            data = open(p, "rb").read()
        except:
            continue

        # Search for iCubeAuthInfo:// pattern
        for m in re.finditer(rb"iCubeAuthInfo", data):
            start = max(0, m.start() - 100)
            end = min(len(data), m.end() + 300)
            ctx = data[start:end].decode("utf-8", errors="replace")
            rel = __import__("os").path.relpath(p, base)
            print(f"\n=== {rel} at {m.start()} ===")
            print(ctx)
            print()

# Also search for the tc\x05 prefix in binary form
print("\n\n=== Searching for tc prefix byte patterns ===")
for root, dirs, files in __import__("os").walk(base):
    for f in files:
        if not f.endswith(".js"):
            continue
        p = __import__("os").path.join(root, f)
        try:
            if __import__("os").path.getsize(p) > 100 * 1024 * 1024:
                continue
            data = open(p, "rb").read()
        except:
            continue
        # Search for Buffer.from([116,99,5]) or "tc\x05"
        for pat in [rb"\[116,\s*99,\s*5\]", rb'\\x74\\x63\\x05', rb"746305", rb"from.*116.*99"]:
            for m in re.finditer(pat, data):
                start = max(0, m.start() - 200)
                end = min(len(data), m.end() + 200)
                ctx = data[start:end].decode("utf-8", errors="replace")
                rel = __import__("os").path.relpath(p, base)
                print(f"\n=== {rel} pattern={pat} at {m.start()} ===")
                print(ctx)
