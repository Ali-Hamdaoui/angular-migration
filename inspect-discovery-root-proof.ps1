param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [string]$PythonPath = "$PSScriptRoot\backend\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
    throw "Database not found: $DatabasePath"
}

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python not found: $PythonPath"
}

$tempPy = Join-Path $env:TEMP ("inspect-discovery-root-" + [guid]::NewGuid().ToString("N") + ".py")

$code = @'
import json
import sqlite3
import sys
from pathlib import Path

db_path, run_id = sys.argv[1:3]

conn = sqlite3.connect(db_path, timeout=30)
conn.row_factory = sqlite3.Row

tables = {
    row["name"]
    for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
}

def columns(table):
    return {
        row["name"]
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }

def parse_json(value):
    if not value:
        return {}
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}

print(f"\nRun:      {run_id}")
print(f"Database: {db_path}")

print("\n=== PERSISTED SOURCE SNAPSHOT ===")
snapshot_table = None
for candidate in ("source_snapshots", "source_snapshot"):
    if candidate in tables:
        snapshot_table = candidate
        break

if not snapshot_table:
    for table in sorted(tables):
        if "source" in table.lower() and "snapshot" in table.lower():
            snapshot_table = table
            break

snapshot_paths = []
snapshot_ids = []

if snapshot_table and "run_id" in columns(snapshot_table):
    rows = conn.execute(
        f'SELECT * FROM "{snapshot_table}" WHERE run_id = ?',
        (run_id,),
    ).fetchall()

    if not rows:
        print("No source snapshot row found.")
    else:
        for raw in rows:
            row = dict(raw)
            snapshot_id = row.get("snapshot_id") or row.get("id")
            snapshot_path = (
                row.get("snapshot_path")
                or row.get("path")
                or row.get("root_path")
            )
            print(f"table         : {snapshot_table}")
            print(f"snapshot_id   : {snapshot_id}")
            print(f"snapshot_path : {snapshot_path}")
            if snapshot_id:
                snapshot_ids.append(str(snapshot_id))
            if snapshot_path:
                snapshot_paths.append(str(snapshot_path))
else:
    print("Source snapshot table not found.")

print("\n=== SCANNER EVENT ROOTS ===")
event_table = "workflow_events" if "workflow_events" in tables else None
if not event_table:
    for table in sorted(tables):
        if "workflow" in table.lower() and "event" in table.lower():
            event_table = table
            break

scanner_roots = []
scanner_snapshot_ids = []
scanner_events = []

if event_table and "run_id" in columns(event_table):
    rows = conn.execute(
        f'SELECT * FROM "{event_table}" WHERE run_id = ? ORDER BY sequence',
        (run_id,),
    ).fetchall()

    for raw in rows:
        row = dict(raw)
        event_type = row.get("event_type") or row.get("type") or row.get("name")
        if event_type not in ("SCANNER_COMPLETED", "DISCOVERY_BLOCKED"):
            continue

        payload = {}
        for key in ("payload", "payload_json", "event_payload", "details"):
            if key in row:
                payload = parse_json(row.get(key))
                if payload:
                    break

        scanner = payload.get("scanner") or payload.get("scanner_name")
        discovery_root = payload.get("discovery_root")
        snapshot_id = payload.get("snapshot_id")

        scanner_events.append(
            {
                "sequence": row.get("sequence"),
                "event_type": event_type,
                "scanner": scanner,
                "discovery_root": discovery_root,
                "snapshot_id": snapshot_id,
                "payload": payload,
            }
        )

        if discovery_root:
            scanner_roots.append(str(discovery_root))
        if snapshot_id:
            scanner_snapshot_ids.append(str(snapshot_id))

    for event in scanner_events:
        print(
            f'#{event["sequence"]} {event["event_type"]} '
            f'scanner={event["scanner"]} '
            f'snapshot_id={event["snapshot_id"]} '
            f'discovery_root={event["discovery_root"]}'
        )
else:
    print("Workflow event table not found.")

all_roots = []
for value in snapshot_paths + scanner_roots:
    if value and value not in all_roots:
        all_roots.append(value)

print("\n=== FILESYSTEM PROBE ===")
if not all_roots:
    print("No persisted or event discovery roots were found.")
else:
    for raw_root in all_roots:
        root = Path(raw_root)
        try:
            resolved = root.resolve(strict=False)
        except Exception:
            resolved = root

        package = resolved / "package.json"
        angular = resolved / "angular.json"

        print(f"\nroot raw      : {raw_root}")
        print(f"root resolved : {resolved}")
        print(f"root exists   : {resolved.exists()}")
        print(f"package.json  : {package.exists()} -> {package}")
        print(f"angular.json  : {angular.exists()} -> {angular}")

        matches = []
        if resolved.exists():
            try:
                matches = list(resolved.rglob("angular.json"))
            except Exception as exc:
                print(f"recursive scan failed: {exc}")

        print(f"recursive angular.json count: {len(matches)}")
        for match in matches[:20]:
            print(f"  - {match}")

print("\n=== CONSISTENCY VERDICT ===")
unique_snapshot_paths = sorted(set(snapshot_paths))
unique_event_roots = sorted(set(scanner_roots))
unique_snapshot_ids = sorted(set(snapshot_ids))
unique_event_snapshot_ids = sorted(set(scanner_snapshot_ids))

print(f"persisted snapshot paths : {unique_snapshot_paths}")
print(f"event discovery roots    : {unique_event_roots}")
print(f"persisted snapshot IDs   : {unique_snapshot_ids}")
print(f"event snapshot IDs       : {unique_event_snapshot_ids}")

if unique_snapshot_paths and unique_event_roots:
    persisted_resolved = {
        str(Path(value).resolve(strict=False)).lower()
        for value in unique_snapshot_paths
    }
    event_resolved = {
        str(Path(value).resolve(strict=False)).lower()
        for value in unique_event_roots
    }

    if persisted_resolved == event_resolved:
        print("PASS: event discovery_root matches persisted snapshot_path.")
    else:
        print("FAIL: event discovery_root differs from persisted snapshot_path.")

for root_value in unique_event_roots:
    root = Path(root_value).resolve(strict=False)
    package_exists = (root / "package.json").exists()
    angular_exists = (root / "angular.json").exists()

    if package_exists and angular_exists:
        print(
            "PATH RESULT: both package.json and angular.json exist at the "
            "event discovery_root. The remaining defect is inside shared "
            "Angular scanner path handling."
        )
    elif package_exists and not angular_exists:
        print(
            "PATH RESULT: package.json exists but angular.json does not exist "
            "at the event discovery_root. The persisted snapshot path points "
            "to the wrong project directory or angular.json is nested."
        )
    elif not package_exists:
        print(
            "PATH RESULT: package.json is also absent at the event root. "
            "Inspect scanner fallback behavior because package scanners "
            "succeeded from another path."
        )

conn.close()
'@

Set-Content -LiteralPath $tempPy -Value $code -Encoding UTF8

try {
    & $PythonPath $tempPy $DatabasePath $RunId

    if ($LASTEXITCODE -ne 0) {
        throw "Inspection failed with exit code $LASTEXITCODE."
    }
}
finally {
    Remove-Item -LiteralPath $tempPy -Force -ErrorAction SilentlyContinue
}
