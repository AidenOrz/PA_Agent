"""Search for HTTP request and chat-sending patterns in extension.js."""
import re

EXT = r"C:\Program Files\QoderCN\resources\app\extensions\aicoding-agent\dist\extension.js"
with open(EXT, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

# Search for fetch() calls with URLs
print("=== fetch() calls with URLs ===")
fetch_re = re.compile(r'fetch\(`?["\']?(https?://[^`"\']{5,150})[`"\']?')
urls = sorted(set(fetch_re.findall(text)))
for u in urls[:30]:
    print(f"  {u}")

# Search for axios/http request patterns
print("\n\n=== axios/http patterns ===")
http_re = re.compile(r'(?:axios|http\.request|https\.request|got\(|request\()\([^)]{0,200}')
for m in list(http_re.finditer(text))[:10]:
    print(f"  {m.group(0)[:200]}")

# Search for API endpoint strings
print("\n\n=== API endpoint strings ===")
api_re = re.compile(r'["\'`](/api/v[12]/[a-zA-Z0-9_/\-]+)["\'`]')
apis = sorted(set(api_re.findall(text)))
print(f"Found {len(apis)} API paths:")
for a in apis:
    print(f"  {a}")

# Search for chat-related function names
print("\n\n=== Chat-related function calls ===")
chat_re = re.compile(r'(?:send|create|start|submit|post)(?:Chat|Message|Question|Request|Query|Task|Agent)[a-zA-Z]*\(')
chats = sorted(set(chat_re.findall(text)))
for c in chats[:30]:
    print(f"  {c}")

# Search for "chat" + "send" proximity
print("\n\n=== chat + send proximity ===")
cs_re = re.compile(r'.{0,80}chat.{0,30}(?:send|create|start|submit|request).{0,80}', re.IGNORECASE)
for m in list(cs_re.finditer(text))[:10]:
    s = m.group(0)
    if "sendChat" in s or "createChat" in s or "startChat" in s or "chatSend" in s or "sendMessage" in s:
        print(f"  {s[:250]}")

# Search for "broker" patterns (the sidecar is called "broker")
print("\n\n=== broker patterns ===")
broker_re = re.compile(r'.{0,60}broker\.[a-zA-Z]+.{0,60}')
for m in list(broker_re.finditer(text))[:10]:
    print(f"  {m.group(0)[:200]}")

# Search for "session" + "create" patterns
print("\n\n=== session create patterns ===")
session_re = re.compile(r'(?:create|new|start)(?:Session|Task|Chat|Agent)\(')
for m in list(session_re.finditer(text))[:10]:
    idx = m.start()
    context = text[max(0, idx-50):min(len(text), idx+150)]
    print(f"  {context[:250]}")
