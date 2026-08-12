"""Check state.vscdb for auth tokens."""
import sqlite3

db = sqlite3.connect(r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\globalStorage\state.vscdb")
cur = db.cursor()
cur.execute("SELECT key, length(value) FROM ItemTable WHERE key LIKE '%auth%' OR key LIKE '%token%' OR key LIKE '%cloudide%' OR key LIKE '%iCube%' OR key LIKE '%supabase%'")
rows = cur.fetchall()
for k, v in rows:
    print(f"{k}: len={v}")
if not rows:
    print("No matching keys found. Listing all keys:")
    cur.execute("SELECT key FROM ItemTable")
    for (k,) in cur.fetchall():
        print(f"  {k}")
db.close()
