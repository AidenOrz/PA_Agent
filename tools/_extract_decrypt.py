"""Extract the full decryption context from main.js and bootstrap-fork.js."""
import re

# main.js - get more context around position 2220967 (nameShort decryption)
p = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\main.js"
data = open(p, encoding="utf-8", errors="replace").read()

# Find the nameShort decryption function
idx = data.find("createDecipheriv", 2220000)
if idx > 0:
    start = max(0, idx - 800)
    end = min(len(data), idx + 400)
    print("=== main.js nameShort decryption context ===")
    print(data[start:end])
    print()

# Also find the safeStorage/decryptString code
idx2 = data.find("safeStorage", 666000)
if idx2 > 0:
    start = max(0, idx2 - 200)
    end = min(len(data), idx2 + 1500)
    print("\n=== main.js safeStorage context ===")
    print(data[start:end])
    print()

# bootstrap-fork.js - get the full decryption function
p2 = r"C:\Users\Administrator\AppData\Local\Programs\TRAE SOLO CN\resources\app\out\bootstrap-fork.js"
data2 = open(p2, encoding="utf-8", errors="replace").read()
idx3 = data2.find("createDecipheriv")
if idx3 > 0:
    start = max(0, idx3 - 800)
    end = min(len(data2), idx3 + 400)
    print("\n=== bootstrap-fork.js decryption context ===")
    print(data2[start:end])
