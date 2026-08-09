import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260807-B\control-tower.db"
run_id = "run-f7621c69be07"

c = sqlite3.connect(db)

print("=== CONTINUATION ===")
for r in c.execute("""
SELECT status,current_node,last_error_code,last_error_message,state_version,updated_at
FROM transformation_continuations
WHERE run_id=?
""", (run_id,)):
    print(r)

print("\n=== LAST 20 EVENTS ===")
for r in reversed(c.execute("""
SELECT sequence,event_type,reason,payload,occurred_at
FROM workflow_events
WHERE run_id=?
ORDER BY sequence DESC
LIMIT 20
""", (run_id,)).fetchall()):
    print("\n#", r[0], r[1], r[4])
    print("reason:", r[2])
    print("payload:", r[3])

c.close()
