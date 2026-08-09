import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260807-B\control-tower.db"
execution_id = "exec-1489e75dedec"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

print("=== COMMAND EXECUTION ===")
row = c.execute(
    "SELECT * FROM command_executions WHERE id=?",
    (execution_id,)
).fetchone()

print(dict(row) if row else "NOT FOUND")

print("\n=== TABLES WITH EXECUTION_ID ===")
tables = [
    r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
]

for table in tables:
    cols = [r[1] for r in c.execute(f'PRAGMA table_info("{table}")')]
    if "execution_id" not in cols:
        continue

    rows = c.execute(
        f'SELECT * FROM "{table}" WHERE execution_id=?',
        (execution_id,)
    ).fetchall()

    if rows:
        print(f"\n--- {table} ---")
        for item in rows:
            print(dict(item))

c.close()
