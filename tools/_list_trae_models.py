"""Extract all model names from TRAE's state.vscdb."""
import sqlite3, json

db_path = r"C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT value FROM ItemTable WHERE key=?", ("2719552726382864:AI.agent.model.model_list_map",))
row = cur.fetchone()
val = row[0]
if isinstance(val, bytes):
    val = val.decode("utf-8", errors="replace")
data = json.loads(val)

print("=== Model labels and names ===")
for label, models in data.items():
    print(f"\n--- Label: {label} ({len(models)} models) ---")
    for m in models:
        name = m.get("name", "?")
        display = m.get("display_name", "?")
        model_type = m.get("model_type", "?")
        use_remote = m.get("use_remote_service", "?")
        max_tokens = m.get("max_tokens", "?")
        print(f"  name={name}  display={display}  type={model_type}  remote={use_remote}  max_tokens={max_tokens}")

# Also check the other key
cur.execute("SELECT value FROM ItemTable WHERE key=?", ("2719552726382864_AI.agent.model.model_list_map",))
row = cur.fetchone()
if row:
    val = row[0]
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="replace")
    data2 = json.loads(val)
    print("\n\n=== Builder model list ===")
    for label, models in data2.items():
        print(f"\n--- Label: {label} ({len(models)} models) ---")
        for m in models:
            name = m.get("name", "?")
            display = m.get("display_name", "?")
            print(f"  name={name}  display={display}")

conn.close()
