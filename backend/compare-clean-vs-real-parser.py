import sqlite3
from pathlib import Path

from app.services.angular_transformation_evidence_service import (
    AngularTransformationEvidenceService,
)

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"
artifact_id = "artifact-a9c9a9b7fffb40beb182936b95cd0f42"

svc = AngularTransformationEvidenceService()

print("=== CLEAN CONTROL INPUT ===")
clean = (
    "Angular CLI       : 21.2.20\n"
    "Angular           : 21.2.19\n"
)
print("CLI :", svc._line_version(clean, "Angular CLI:"))
print("CORE:", svc._line_version(clean, "Angular:"))

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

run = c.execute(
    "SELECT artifact_root FROM migration_runs WHERE id=?",
    (run_id,),
).fetchone()

artifact = c.execute(
    "SELECT relative_path FROM artifact_metadata WHERE id=? OR id=?",
    (artifact_id, "metadata-" + artifact_id),
).fetchone()

path = Path(run["artifact_root"]) / artifact["relative_path"]
output = path.read_text(encoding="utf-8", errors="replace")

print("\n=== REAL ARTIFACT ===")
print("CLI :", svc._line_version(output, "Angular CLI:"))
print("CORE:", svc._line_version(output, "Angular:"))

c.close()
