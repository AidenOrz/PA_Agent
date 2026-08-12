import sqlite3
DB = r"C:\Users\Administrator\AppData\Roaming\QoderCN\SharedClientCache\cache\db\local.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables ({len(tables)}): {tables}")
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM `{t}`")
        cnt = cur.fetchone()[0]
        cur.execute(f"PRAGMA table_info(`{t}`)")
        cols = [r[1] for r in cur.fetchall()]
        print(f"\n=== {t} ({cnt} rows) ===")
        print(f"  cols: {cols}")
        if cnt > 0 and any('token' in c.lower() or 'jwt' in c.lower() or 'auth' in c.lower() or 'key' in c.lower() for c in cols):
            cur.execute(f"SELECT * FROM `{t}` LIMIT 3")
            for row in cur.fetchall():
                print(f"  row: {str(row)[:300]}")
    except Exception as e:
        print(f"  ERROR: {e}")
conn.close()
