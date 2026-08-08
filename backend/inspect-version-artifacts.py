import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
execution_id = "exec-2fde8a2cf32e"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

e = c.execute("""
SELECT stdout_artifact_id,stderr_artifact_id,result_artifact_id,manifest_artifact_id
FROM command_executions
WHERE id=?
""", (execution_id,)).fetchone()

for label, aid in dict(e).items():
    if not aid:
        continue
    print("\n", label, aid)
    rows = c.execute("""
    SELECT *
    FROM artifact_metadata
    WHERE id=? OR id=?
    """, (aid, "metadata-" + aid)).fetchall()
    for r in rows:
        print(dict(r))

c.close()
