"""Search for mode values in Qoder CN extension."""
import re
data = open(r'C:\Program Files\QoderCN\resources\app\extensions\aicoding-agent\dist\extension.js', 'r', encoding='utf-8', errors='replace').read()

# Search for mode: "xxx" patterns
for pattern in [r'mode["\']?\s*[:=]\s*["\'](\w+)["\']', r'"mode"\s*:\s*"(\w+)"', r'sessionType\s*[:=]\s*["\'](\w+)["\']']:
    matches = re.findall(pattern, data)
    if matches:
        unique = sorted(set(matches))
        print(f"Pattern {pattern}:")
        for m in unique:
            print(f"  {m}")
        print()

# Also search for chatTask values
for pattern in [r'chatTask\s*[:=]\s*["\'](\w+)["\']', r'"chatTask"\s*:\s*"(\w+)"']:
    matches = re.findall(pattern, data)
    if matches:
        unique = sorted(set(matches))
        print(f"Pattern {pattern}:")
        for m in unique:
            print(f"  {m}")
        print()
