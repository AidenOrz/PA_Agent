"""Read model configs from TRAE's database."""
import sqlite3, json

db_path = r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\database.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for t in tables:
    if "model" in t.lower() or "config" in t.lower() or "llm" in t.lower():
        print(f"\n=== Table: {t} ===")
        cur.execute(f"SELECT * FROM {t} LIMIT 20")
        cols = [d[0] for d in cur.description]
        print(f"Columns: {cols}")
        for row in cur.fetchall():
            print(f"  {dict(zip(cols, row))}")

conn.close()
