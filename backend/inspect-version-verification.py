import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"
execution_id = "exec-2fde8a2cf32e"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

r = c.execute("""
SELECT id,stage_id,command_id,status,executable,arguments,
       timeout_seconds,exit_code,failure_code,failure_message,
       stdout_artifact_id,stderr_artifact_id,
       result_artifact_id,manifest_artifact_id,
       start_fingerprint,end_fingerprint
FROM command_executions
WHERE id=?
""", (execution_id,)).fetchone()

print("=== EXECUTION ===")
print(dict(r) if r else "NOT FOUND")

print("\n=== CONTINUATION ===")
r = c.execute("""
SELECT status,current_node,last_error_code,last_error_message,state_version
FROM transformation_continuations
WHERE run_id=?
ORDER BY created_at DESC
LIMIT 1
""", (run_id,)).fetchone()
print(dict(r) if r else "NOT FOUND")

c.close()
