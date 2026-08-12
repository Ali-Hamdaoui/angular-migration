import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
execution_id = "exec-2fde8a2cf32e"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

rows = c.execute("""
SELECT sequence, stream, text
FROM command_log_chunks
WHERE execution_id=?
ORDER BY sequence
""", (execution_id,)).fetchall()

output = "".join(row["text"] or "" for row in rows)

print("=== CHUNKS ===")
for row in rows:
    print("sequence:", row["sequence"])
    print("stream:", row["stream"])
    print("repr:", repr(row["text"]))

print("\n=== ANGULAR LINES ===")
for line in output.splitlines():
    if "Angular" in line:
        print(repr(line))

c.close()
