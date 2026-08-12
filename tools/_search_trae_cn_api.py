"""Search Trae CN ai-agent logs and database for API endpoint and JWT tokens."""
import sqlite3
import re
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Roaming\Trae CN")

# 1. Check ai-agent database
db_path = BASE / "ModularData" / "ai-agent" / "database.db"
print(f"=== ai-agent database: {db_path} ===")
if db_path.exists():
    try:
        db = sqlite3.connect(str(db_path))
        cur = db.cursor()
        # List tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"Tables: {tables}")
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
            # Get columns
            cur.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cur.fetchall()]
            print(f"    columns: {cols}")
        db.close()
    except Exception as exc:
        print(f"  Error: {exc}")

# 2. Search ckg_server logs for JWT tokens and API calls
print("\n=== Searching ckg_server logs ===")
ckg_dir = BASE / "ModularData" / "ckg_server"
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")
API_RE = re.compile(rb"https?://[a-zA-Z0-9._\-]+/api/[a-zA-Z0-9/_\-]+")

for log_file in sorted(ckg_dir.glob("*.log*")):
    try:
        data = log_file.read_bytes()
    except Exception:
        continue
    jwt_hits = set(m.group() for m in JWT_RE.finditer(data))
    api_hits = set(m.group() for m in API_RE.finditer(data))
    if jwt_hits or api_hits:
        print(f"\n  {log_file.name}:")
        for api in list(api_hits)[:5]:
            print(f"    API: {api.decode('ascii', errors='replace')}")
        for jwt in list(jwt_hits)[:2]:
            print(f"    JWT: {jwt[:60].decode('ascii', errors='replace')}...")

# 3. Search all logs under Trae CN for chat API and JWT
print("\n=== Searching all logs for chat API ===")
logs_dir = BASE / "logs"
if logs_dir.exists():
    for log_file in sorted(logs_dir.rglob("*.log")):
        try:
            data = log_file.read_bytes()
            if len(data) > 50 * 1024 * 1024:
                continue
        except Exception:
            continue
        api_hits = set(m.group() for m in API_RE.finditer(data))
        jwt_hits = set(m.group() for m in JWT_RE.finditer(data))
        if api_hits or jwt_hits:
            print(f"\n  {log_file.relative_to(BASE)}:")
            for api in list(api_hits)[:5]:
                print(f"    API: {api.decode('ascii', errors='replace')}")
            for jwt in list(jwt_hits)[:2]:
                print(f"    JWT: {jwt[:60].decode('ascii', errors='replace')}...")
