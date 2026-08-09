import sqlite3
import json

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

print("=== CONTINUATION ===")
r = c.execute("""
SELECT id,status,current_node,last_error_code,last_error_message,
       state_version,waiting_execution_id
FROM transformation_continuations
WHERE run_id=?
ORDER BY created_at DESC
LIMIT 1
""", (run_id,)).fetchone()

print(dict(r) if r else "NOT FOUND")

print("\n=== CURRENT STAGE REPAIR ATTEMPTS ===")

rows = c.execute("""
SELECT id,stage_id,attempt_number,status,
       failure_evidence_artifact_id,
       proposal_artifact_id,
       review_artifact_id,
       updated_at
FROM repair_attempts
WHERE run_id=?
ORDER BY created_at
""", (run_id,)).fetchall()

for row in rows:
    print(dict(row))

print("\n=== LATEST WORKFLOW EVENTS ===")

rows = c.execute("""
SELECT sequence,event_type,reason,payload,occurred_at
FROM workflow_events
WHERE run_id=?
ORDER BY sequence DESC
LIMIT 15
""", (run_id,)).fetchall()

for row in reversed(rows):
    print("\n#", row["sequence"], row["event_type"])
    print("reason:", row["reason"])
    print("payload:", row["payload"])

c.close()
