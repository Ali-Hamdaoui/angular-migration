import sqlite3

p = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower\control-tower.db"
c = sqlite3.connect(p)

c.execute("BEGIN IMMEDIATE")

cur = c.execute("""
UPDATE migration_runs
SET
    status = 'CANCELLED',
    phase_status = 'cancelled',
    state_version = state_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 'smoke-proof-run'
  AND status = 'RUNNING'
  AND preflight_id IS NULL
  AND source_path IS NULL
  AND target_output_path IS NULL
""")

print("ROWS UPDATED:", cur.rowcount)

c.commit()

print("RESULT:", c.execute(
    "SELECT id,status,phase_status,state_version FROM migration_runs "
    "WHERE id='smoke-proof-run'"
).fetchall())

c.close()
