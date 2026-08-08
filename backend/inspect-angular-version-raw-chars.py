import sqlite3
from pathlib import Path

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260808-D\control-tower.db"
run_id = "run-d3d0222baf58"
artifact_id = "artifact-a9c9a9b7fffb40beb182936b95cd0f42"

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

print("=== RAW ANGULAR LINES ===")

for line in output.splitlines():
    if "Angular" in line:
        print("\nVISIBLE:")
        print(line)

        print("REPR:")
        print(repr(line))

        print("CODEPOINTS:")
        print(" ".join(f"U+{ord(ch):04X}" for ch in line))

c.close()
