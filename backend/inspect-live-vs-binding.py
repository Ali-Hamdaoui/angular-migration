import sqlite3
from pathlib import Path
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260807-C\control-tower.db"
run_id = "run-a2a348a950bb"
stage_id = "angular-20-to-21--1269ed5e61c08196"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

b = c.execute("""
SELECT workspace_path,workspace_fingerprint,last_verified_fingerprint
FROM stage_workspace_bindings
WHERE run_id=? AND stage_id=? AND active=1
""", (run_id, stage_id)).fetchone()

workspace = Path(b["workspace_path"])

print("WORKSPACE:", workspace)
print("BINDING:", b["workspace_fingerprint"])
print("LAST VERIFIED:", b["last_verified_fingerprint"])
print("LIVE:", STAGE_FINGERPRINT_PROFILE.fingerprint(workspace))

c.close()
