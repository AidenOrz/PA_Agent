"""Search state.vscdb for model list data."""
import sqlite3, json

db_path = r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# VS Code state is usually in ItemTable: (key, value)
for t in tables:
    cur.execute(f"SELECT key FROM {t}")
    keys = [r[0] for r in cur.fetchall()]
    model_keys = [k for k in keys if "model" in k.lower() or "llm" in k.lower() or "MODEL_LIST" in k]
    if model_keys:
        print(f"\n=== Model-related keys in {t} ===")
        for k in model_keys:
            cur.execute(f"SELECT value FROM {t} WHERE key=?", (k,))
            row = cur.fetchone()
            if row:
                val = row[0]
                if isinstance(val, bytes):
                    val = val.decode("utf-8", errors="replace")
                print(f"\n  KEY: {k}")
                # Try to parse as JSON
                try:
                    data = json.loads(val)
                    s = json.dumps(data, indent=2, ensure_ascii=False)
                    print(f"  {s[:3000]}")
                except:
                    print(f"  {str(val)[:2000]}")

conn.close()
