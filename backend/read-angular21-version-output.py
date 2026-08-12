import sqlite3
from pathlib import Path

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"
artifact_id = "artifact-a9c9a9b7fffb40beb182936b95cd0f42"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

run = c.execute("""
SELECT id, artifact_root
FROM migration_runs
WHERE id=?
""", (run_id,)).fetchone()

artifact = c.execute("""
SELECT id, relative_path, checksum, size_bytes
FROM artifact_metadata
WHERE id=? OR id=?
""", (artifact_id, "metadata-" + artifact_id)).fetchone()

print("=== RUN ===")
print(dict(run))

print("\n=== ARTIFACT ===")
print(dict(artifact))

full_path = Path(run["artifact_root"]) / artifact["relative_path"]

print("\n=== FULL PATH ===")
print(full_path)
print("EXISTS:", full_path.exists())

print("\n=== STDOUT ===")
if full_path.exists():
    print(full_path.read_text(encoding="utf-8", errors="replace"))
else:
    print("FILE NOT FOUND AT AUTHORITATIVE PATH")

c.close()
