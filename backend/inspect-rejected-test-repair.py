import sqlite3
from pathlib import Path

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"

artifact_ids = [
    "artifact-f313b8e2f2f94a1cb97190b9794af40f",
    "artifact-c0ff7003bce74e12b335a32177624665",
]

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

run = c.execute(
    "SELECT artifact_root FROM migration_runs WHERE id=?",
    (run_id,),
).fetchone()

for artifact_id in artifact_ids:
    row = c.execute("""
        SELECT id,relative_path
        FROM artifact_metadata
        WHERE id=? OR id=?
    """, (artifact_id, "metadata-" + artifact_id)).fetchone()

    print("\n" + "=" * 80)
    print(artifact_id)

    if row is None:
        print("NOT FOUND")
        continue

    path = Path(run["artifact_root"]) / row["relative_path"]

    print("PATH:", path)
    print("-" * 80)
    print(path.read_text(encoding="utf-8", errors="replace"))

c.close()
