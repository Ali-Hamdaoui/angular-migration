import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

print("=== CONTINUATION ===")
r = c.execute("""
SELECT id,status,current_node,state_version,
       last_error_code,last_error_message,
       waiting_execution_id,updated_at
FROM transformation_continuations
WHERE run_id=?
ORDER BY created_at DESC
LIMIT 1
""", (run_id,)).fetchone()
print(dict(r))

print("\n=== VERSION COMMAND ===")
r = c.execute("""
SELECT id,stage_id,status,command_id,exit_code,
       stdout_artifact_id,result_artifact_id,
       timeout_seconds,finished_at
FROM command_executions
WHERE id='exec-2fde8a2cf32e'
""").fetchone()
print(dict(r))

c.close()
