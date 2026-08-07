import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260807-C\control-tower.db"
run_id = "run-a2a348a950bb"
execution_id = "exec-99ac3ffb4b54"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

print("\n=== FAILED COMMAND ===")
r = c.execute(
    "SELECT * FROM command_executions WHERE id=?",
    (execution_id,)
).fetchone()
print(dict(r) if r else "NOT FOUND")

print("\n=== CONTINUATION ===")
for r in c.execute("""
SELECT status,current_node,last_error_code,last_error_message,state_version,updated_at
FROM transformation_continuations
WHERE run_id=?
""", (run_id,)):
    print(dict(r))

print("\n=== LATEST 20 EVENTS ===")
rows = c.execute("""
SELECT sequence,event_type,reason,payload,occurred_at
FROM workflow_events
WHERE run_id=?
ORDER BY sequence DESC
LIMIT 20
""", (run_id,)).fetchall()

for r in reversed(rows):
    print("\n#", r["sequence"], r["event_type"], r["occurred_at"])
    print("reason:", r["reason"])
    print("payload:", r["payload"])

print("\n=== FAILURE ARTIFACTS ===")
for artifact_id in (
    "artifact-ab9f35de64f74aa2b42c2b8a2b80ffc7",
    "artifact-8ad185077a2a4c2399c90226f6cbd985",
    "artifact-1aa6f1c043f14d90b2a967dacf3ed3cc",
    "artifact-050615bd9be54236927976946171fca1",
    "artifact-2089727f220c443ca35dfa1685cb70e1",
):
    r = c.execute(
        "SELECT id,relative_path,artifact_type,checksum FROM artifact_metadata WHERE id=?",
        (artifact_id,)
    ).fetchone()
    print(dict(r) if r else artifact_id + " NOT FOUND")

c.close()
