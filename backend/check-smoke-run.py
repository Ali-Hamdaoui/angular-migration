import sqlite3

p = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower\control-tower.db"
c = sqlite3.connect(p)

print("RUN:", c.execute(
    "SELECT id,status,state_version,preflight_id,source_path,target_output_path "
    "FROM migration_runs WHERE id='smoke-proof-run'"
).fetchall())

print("CLAIMS:", c.execute(
    "SELECT * FROM active_run_claims WHERE run_id='smoke-proof-run'"
).fetchall())

print("COMMANDS:", c.execute(
    "SELECT id,status,stage_id FROM command_executions "
    "WHERE run_id='smoke-proof-run' "
    "AND status IN ('queued','pending','running')"
).fetchall())

c.close()
