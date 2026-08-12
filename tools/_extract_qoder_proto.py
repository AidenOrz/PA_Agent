"""Extract WebSocket/chat protocol patterns from Qoder's minified extension.js.

The file is one giant minified line. We use regex to find:
  - WebSocket connection URLs / protocols
  - JSON-RPC method names
  - Chat completion request shapes
"""
from __future__ import annotations

import re
from pathlib import Path

EXT = Path(r"C:\Program Files\QoderCN\resources\app\extensions\aicoding-agent\dist\extension.js")
TEXT = EXT.read_text(encoding="utf-8", errors="replace")
print(f"文件大小: {len(TEXT):,} 字符")

# 1. Find all string literals that look like method names / paths.
print("\n" + "=" * 60)
print("1. 字符串中的 'method' / 'path' / 'rpc' 相关")
print("=" * 60)

# Look for method:"..." patterns
method_re = re.compile(r'method:"([a-zA-Z0-9_./\-]{3,80})"')
methods = sorted(set(method_re.findall(TEXT)))
print(f"\n找到 {len(methods)} 个 method 值:")
for m in methods:
    print(f"  • {m}")

# 2. Find chat-related strings.
print("\n" + "=" * 60)
print("2. chat / completion / inference 相关字符串")
print("=" * 60)
chat_re = re.compile(r'"([^"]*(?:chat|completion|inference|llm|stream)[^"]{0,80})"', re.IGNORECASE)
chats = sorted(set(chat_re.findall(TEXT)))
# Filter to interesting ones
interesting = [c for c in chats if len(c) > 5 and len(c) < 100 and not c.startswith("http")]
print(f"\n找到 {len(interesting)} 个相关字符串:")
for c in interesting[:50]:
    print(f"  • {c}")

# 3. Find WebSocket related code.
print("\n" + "=" * 60)
print("3. WebSocket 相关")
print("=" * 60)
ws_re = re.compile(r'(new WebSocket|websocketPort|ws://[^\s"\'`]+|wss?://[^\s"\'`]+|\.send\([^)]{0,200})', re.IGNORECASE)
ws_matches = ws_re.findall(TEXT)
print(f"\n找到 {len(ws_matches)} 个 WebSocket 相关:")
for w in ws_matches[:20]:
    print(f"  • {w[:150]}")

# 4. Find jsonrpc patterns.
print("\n" + "=" * 60)
print("4. JSON-RPC patterns")
print("=" * 60)
rpc_re = re.compile(r'jsonrpc[^a-z]{0,5}["\']?2\.0', re.IGNORECASE)
rpc_count = len(rpc_re.findall(TEXT))
print(f"jsonrpc 2.0 出现次数: {rpc_count}")

# 5. Find URL paths starting with /
print("\n" + "=" * 60)
print("5. API 路径 (/v1/, /api/, /cosy/, /qoder/)")
print("=" * 60)
path_re = re.compile(r'"(/(?:v1|api|cosy|qoder|openai|inference|chat)[a-zA-Z0-9_./\-]{2,80})"')
paths = sorted(set(path_re.findall(TEXT)))
print(f"\n找到 {len(paths)} 个路径:")
for p in paths:
    print(f"  • {p}")

# 6. Look for the specific pattern around "send" calls
print("\n" + "=" * 60)
print("6. WebSocket .send() 调用上下文")
print("=" * 60)
send_re = re.compile(r'\.send\(([^)]{1,300})\)')
sends = send_re.findall(TEXT)
print(f"\n找到 {len(sends)} 个 .send() 调用:")
for s in sends[:10]:
    print(f"  • {s[:200]}")
