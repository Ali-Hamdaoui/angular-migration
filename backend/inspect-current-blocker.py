import sqlite3, json

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260807\control-tower.db"
run_id = "run-866690a7ca62"

c = sqlite3.connect(db)

print("\n=== CONTINUATION ===")
for r in c.execute("""
SELECT status,current_node,last_error_code,last_error_message,state_version,updated_at
FROM transformation_continuations
WHERE run_id=?
""", (run_id,)):
    print(r)

print("\n=== LATEST EVENTS ===")
rows = c.execute("""
SELECT sequence,event_type,reason,payload,occurred_at
FROM workflow_events
WHERE run_id=?
ORDER BY sequence DESC
LIMIT 15
""", (run_id,)).fetchall()

for r in reversed(rows):
    print("\n#", r[0], r[1], r[4])
    print("reason:", r[2])
    print("payload:", r[3])

print("\n=== REPAIR ATTEMPTS ===")
for r in c.execute("""
SELECT id,attempt_number,status,state_version,
       proposal_artifact_id,review_artifact_id,updated_at
FROM repair_attempts
WHERE run_id=?
ORDER BY attempt_number
""", (run_id,)):
    print(r)

c.close()
