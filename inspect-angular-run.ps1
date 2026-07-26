[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [string]$BackendUrl = "http://127.0.0.1:8000",

    [string]$DatabasePath = "",

    [string]$RepoRoot = (Get-Location).Path,

    [string]$Actor = "control-tower",

    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")

if (-not $OutputRoot) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputRoot = Join-Path $RepoRoot "run-inspection\$RunId-$stamp"
}

$apiRoot = Join-Path $OutputRoot "api"
$dbRoot = Join-Path $OutputRoot "database"
New-Item -ItemType Directory -Path $apiRoot -Force | Out-Null
New-Item -ItemType Directory -Path $dbRoot -Force | Out-Null

$headers = @{
    Accept = "application/json"
    "X-Authenticated-Actor" = $Actor
}

function Save-ApiEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $uri = "$BackendUrl$Path"
    $destination = Join-Path $apiRoot "$Name.json"

    try {
        $response = Invoke-WebRequest `
            -Uri $uri `
            -Method GET `
            -Headers $headers `
            -UseBasicParsing

        $response.Content | Set-Content -Path $destination -Encoding utf8

        return [pscustomobject]@{
            Name = $Name
            Method = "GET"
            Path = $Path
            Status = [int]$response.StatusCode
            File = $destination
            Error = $null
        }
    }
    catch {
        $status = 0
        $body = $_.Exception.Message

        if ($_.Exception.Response) {
            try {
                $status = [int]$_.Exception.Response.StatusCode
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $body = $reader.ReadToEnd()
                    $reader.Dispose()
                }
            }
            catch {
                # Preserve the original exception message.
            }
        }

        $errorPayload = [ordered]@{
            method = "GET"
            uri = $uri
            status = $status
            response = $body
        }
        $errorPayload | ConvertTo-Json -Depth 20 |
            Set-Content -Path $destination -Encoding utf8

        return [pscustomobject]@{
            Name = $Name
            Method = "GET"
            Path = $Path
            Status = $status
            File = $destination
            Error = $body
        }
    }
}

$endpoints = @(
    @{ Name = "state"; Path = "/api/v1/runs/$RunId/state" },
    @{ Name = "discovery"; Path = "/api/v1/runs/$RunId/discovery" },
    @{ Name = "analysis"; Path = "/api/v1/runs/$RunId/analysis" },
    @{ Name = "feasibility"; Path = "/api/v1/runs/$RunId/feasibility" },
    @{ Name = "plan"; Path = "/api/v1/runs/$RunId/plan" },
    @{ Name = "plan-review"; Path = "/api/v1/runs/$RunId/plan/review" },
    @{ Name = "llm-readiness"; Path = "/api/v1/llm/readiness" },
    @{ Name = "llm-activity"; Path = "/api/v1/runs/$RunId/llm/activity" },
    @{ Name = "llm-usage"; Path = "/api/v1/runs/$RunId/usage" },
    @{ Name = "execution-profiles"; Path = "/api/v1/runs/$RunId/execution-profiles" },
    @{ Name = "baseline"; Path = "/api/v1/runs/$RunId/baseline" },
    @{ Name = "baseline-summary"; Path = "/api/v1/runs/$RunId/baseline/summary" },
    @{ Name = "baseline-targets"; Path = "/api/v1/runs/$RunId/baseline/targets" },
    @{ Name = "baseline-build"; Path = "/api/v1/runs/$RunId/baseline/build" },
    @{ Name = "baseline-test"; Path = "/api/v1/runs/$RunId/baseline/test" },
    @{ Name = "baseline-lint"; Path = "/api/v1/runs/$RunId/baseline/lint" },
    @{ Name = "baseline-failures"; Path = "/api/v1/runs/$RunId/baseline/failures" },
    @{ Name = "baseline-routes"; Path = "/api/v1/runs/$RunId/baseline/routes" },
    @{ Name = "baseline-anchors"; Path = "/api/v1/runs/$RunId/baseline/anchors" },
    @{ Name = "baseline-backend-integration"; Path = "/api/v1/runs/$RunId/baseline/backend-integration" }
)

Write-Host ""
Write-Host "Collecting API projections..." -ForegroundColor Cyan
$apiResults = foreach ($endpoint in $endpoints) {
    Save-ApiEndpoint -Name $endpoint.Name -Path $endpoint.Path
}

$apiResults |
    Export-Csv -Path (Join-Path $OutputRoot "api-status.csv") -NoTypeInformation -Encoding utf8

$apiResults |
    Format-Table Name, Status, Path -AutoSize

if (-not $DatabasePath) {
    $databaseBase = Join-Path $env:LOCALAPPDATA "AngularMigrationControlTower"
    $candidate = Get-ChildItem `
        -Path $databaseBase `
        -Filter "control-tower.db" `
        -File `
        -Recurse `
        -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $candidate) {
        throw "No control-tower.db was found below $databaseBase. Pass -DatabasePath explicitly."
    }

    $DatabasePath = $candidate.FullName
}

if (-not (Test-Path $DatabasePath)) {
    throw "SQLite database does not exist: $DatabasePath"
}

$python = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Expected $python or a python command on PATH."
    }
    $python = $pythonCommand.Source
}

$databaseInspector = @'
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

database_path = Path(sys.argv[1]).resolve()
run_id = sys.argv[2]
output_root = Path(sys.argv[3]).resolve()
output_root.mkdir(parents=True, exist_ok=True)

connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row

def parse_json_value(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value

def normalize_row(row):
    result = {}
    for key in row.keys():
        value = row[key]
        if isinstance(value, bytes):
            value = value.hex()
        result[key] = parse_json_value(value)
    return result

def safe_table_name(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Unsafe SQLite table name: {name}")
    return name

def query_rows(table, columns):
    table = safe_table_name(table)
    order = ""
    if "sequence" in columns:
        order = " ORDER BY sequence"
    elif "event_sequence" in columns:
        order = " ORDER BY event_sequence"
    elif "created_at" in columns:
        order = " ORDER BY created_at"

    if "run_id" in columns:
        cursor = connection.execute(
            f'SELECT * FROM "{table}" WHERE run_id = ?{order}',
            (run_id,),
        )
    else:
        cursor = connection.execute(f'SELECT * FROM "{table}" LIMIT 200')
    return [normalize_row(row) for row in cursor.fetchall()]

integrity_check = connection.execute("PRAGMA integrity_check").fetchone()[0]
foreign_key_issues = [
    normalize_row(row)
    for row in connection.execute("PRAGMA foreign_key_check").fetchall()
]

tables = [
    row["name"]
    for row in connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
]

schema = {}
table_rows = {}
table_counts = {}

for table in tables:
    safe = safe_table_name(table)
    columns = [
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{safe}")').fetchall()
    ]
    total_count = connection.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0]

    if "run_id" in columns:
        run_count = connection.execute(
            f'SELECT COUNT(*) FROM "{safe}" WHERE run_id = ?',
            (run_id,),
        ).fetchone()[0]
    else:
        run_count = None

    schema[table] = columns
    table_counts[table] = {
        "total_rows": total_count,
        "run_rows": run_count,
    }

    rows = query_rows(table, columns)
    table_rows[table] = rows

    if "run_id" in columns or table in {
        "alembic_version",
        "compatibility_catalogues",
    }:
        (output_root / f"{table}.json").write_text(
            json.dumps(rows, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

run_rows = table_rows.get("migration_runs", [])
run = run_rows[-1] if run_rows else None

events = table_rows.get("workflow_events", [])
event_types = [str(row.get("event_type")) for row in events]

llm_rows = table_rows.get("llm_invocations", [])
usage_rows = table_rows.get("usage_cost_records", [])
analysis_rows = table_rows.get("analysis_metadata", [])
discovery_rows = table_rows.get("discovery_evidence", [])
compatibility_rows = table_rows.get("compatibility_resolutions", [])
g04_rows = table_rows.get("g04_approvals", [])
g05_rows = table_rows.get("g05_approvals", [])
plans = table_rows.get("migration_plans", [])
stage_plans = table_rows.get("stage_execution_plans", [])
planning_reviews = table_rows.get("planning_reviews", [])
g06_rows = table_rows.get("g06_approvals", [])
source_snapshots = table_rows.get("source_snapshots", [])
artifacts = table_rows.get("artifact_metadata", [])

diagnosis = []

if "DISCOVERY_COMPLETED" in event_types:
    diagnosis.append("Discovery completed.")
else:
    diagnosis.append("Discovery did not complete.")

if "ANALYSIS_AGENT_STARTED" not in event_types:
    diagnosis.append(
        "AI analysis was never started: ANALYSIS_AGENT_STARTED is absent."
    )
elif analysis_rows:
    latest = analysis_rows[-1]
    diagnosis.append(
        f"AI analysis started; latest persisted status={latest.get('status')} "
        f"error_code={latest.get('error_code')}."
    )

if not llm_rows:
    diagnosis.append("No LLM invocation row exists for this run.")
else:
    latest = llm_rows[-1]
    diagnosis.append(
        f"LLM rows={len(llm_rows)}; latest status={latest.get('status')} "
        f"role={latest.get('role')} task_type={latest.get('task_type')} "
        f"failure_code={latest.get('failure_code')}."
    )

if not usage_rows:
    diagnosis.append("No LLM usage/cost row exists for this run.")
else:
    total_tokens = sum(int(row.get("total_tokens") or 0) for row in usage_rows)
    total_cost = sum(float(row.get("total_cost_usd") or 0) for row in usage_rows)
    diagnosis.append(
        f"LLM usage rows={len(usage_rows)} total_tokens={total_tokens} "
        f"total_cost_usd={total_cost:.6f}."
    )

if "G04_APPROVED" not in event_types:
    diagnosis.append("G04 was not approved, so feasibility was not unlocked.")
if "G05_APPROVED" not in event_types:
    diagnosis.append("G05 was not approved, so MigrationPlan generation was not unlocked.")
if "MIGRATION_PLAN_CREATED" not in event_types:
    diagnosis.append("MigrationPlan generation was never invoked.")
if not planning_reviews:
    diagnosis.append("No planning-review record exists.")
if not g06_rows:
    diagnosis.append("No G06 gate record exists.")

root_probe = {}
artifact_root = None

if run:
    aliases = run.get("workspace_aliases") or {}
    if isinstance(aliases, str):
        aliases = parse_json_value(aliases)
    alias_snapshot = Path(str((aliases or {}).get("SOURCE_SNAPSHOT", "")))
    artifact_root_value = run.get("artifact_root")
    if artifact_root_value:
        artifact_root = Path(str(artifact_root_value))

    latest_snapshot = source_snapshots[-1] if source_snapshots else None
    actual_snapshot = (
        Path(str(latest_snapshot.get("snapshot_path")))
        if latest_snapshot and latest_snapshot.get("snapshot_path")
        else None
    )

    root_probe = {
        "workspace_alias_source_snapshot": str(alias_snapshot),
        "persisted_snapshot_path": str(actual_snapshot) if actual_snapshot else None,
        "alias_package_json_exists": (alias_snapshot / "package.json").is_file(),
        "alias_angular_json_exists": (alias_snapshot / "angular.json").is_file(),
        "persisted_package_json_exists": (
            (actual_snapshot / "package.json").is_file()
            if actual_snapshot else False
        ),
        "persisted_angular_json_exists": (
            (actual_snapshot / "angular.json").is_file()
            if actual_snapshot else False
        ),
    }

    if (
        actual_snapshot
        and alias_snapshot != actual_snapshot
        and not root_probe["alias_package_json_exists"]
        and root_probe["persisted_package_json_exists"]
    ):
        diagnosis.append(
            "Discovery root mismatch detected: SOURCE_SNAPSHOT points to the "
            "snapshot parent, while package.json/angular.json are inside the "
            "persisted snapshot_path."
        )

artifact_verification = []
if artifact_root:
    for row in artifacts:
        relative = row.get("relative_path")
        expected = row.get("checksum")
        path = artifact_root / str(relative)
        exists = path.is_file()
        actual = None
        if exists:
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        artifact_verification.append(
            {
                "artifact_id": str(row.get("id", "")).removeprefix("metadata-"),
                "relative_path": relative,
                "exists": exists,
                "expected_checksum": expected,
                "actual_checksum": actual,
                "checksum_matches": bool(exists and expected == actual),
            }
        )

analysis_artifact_summary = []
if artifact_root:
    analysis_dir = artifact_root / "02_analysis"
    if analysis_dir.is_dir():
        for path in sorted(analysis_dir.glob("*.json")):
            if path.name.endswith(".meta.json"):
                continue
            record = {
                "file": str(path),
                "name": path.name,
                "size_bytes": path.stat().st_size,
            }
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                record.update(
                    {
                        "scanner": payload.get("scanner"),
                        "status": payload.get("status"),
                        "finding_count": len(payload.get("findings", [])),
                        "unknowns": payload.get("unknowns", []),
                        "warnings": payload.get("warnings", []),
                    }
                )
            except Exception as error:
                record["read_error"] = type(error).__name__
            analysis_artifact_summary.append(record)

unknown_scanners = [
    item for item in analysis_artifact_summary
    if item.get("status") == "unknown"
]
if unknown_scanners:
    diagnosis.append(
        "Discovery produced unknown scanner results: "
        + ", ".join(
            f"{item.get('scanner')}={item.get('unknowns')}"
            for item in unknown_scanners
        )
    )

summary = {
    "database_path": str(database_path),
    "database_integrity_check": integrity_check,
    "foreign_key_issues": foreign_key_issues,
    "run_id": run_id,
    "run": run,
    "table_counts": table_counts,
    "phase_counts": {
        "workflow_events": len(events),
        "discovery_evidence": len(discovery_rows),
        "analysis_metadata": len(analysis_rows),
        "llm_invocations": len(llm_rows),
        "usage_cost_records": len(usage_rows),
        "g04_approvals": len(g04_rows),
        "compatibility_resolutions": len(compatibility_rows),
        "g05_approvals": len(g05_rows),
        "migration_plans": len(plans),
        "stage_execution_plans": len(stage_plans),
        "planning_reviews": len(planning_reviews),
        "g06_approvals": len(g06_rows),
    },
    "event_types": event_types,
    "snapshot_root_probe": root_probe,
    "analysis_artifact_summary": analysis_artifact_summary,
    "diagnosis": diagnosis,
}

(output_root / "database-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True, default=str),
    encoding="utf-8",
)
(output_root / "artifact-verification.json").write_text(
    json.dumps(artifact_verification, indent=2, sort_keys=True, default=str),
    encoding="utf-8",
)
(output_root / "schema.json").write_text(
    json.dumps(schema, indent=2, sort_keys=True),
    encoding="utf-8",
)
(output_root / "diagnosis.txt").write_text(
    "\n".join(f"- {line}" for line in diagnosis) + "\n",
    encoding="utf-8",
)

print(f"Database: {database_path}")
print(f"Integrity check: {integrity_check}")
print(f"Run: {run_id}")
print("")
print("Diagnosis:")
for line in diagnosis:
    print(f"- {line}")
'@

Write-Host ""
Write-Host "Inspecting SQLite database: $DatabasePath" -ForegroundColor Cyan
$databaseInspector |
    & $python - "$DatabasePath" "$RunId" "$dbRoot"

if ($LASTEXITCODE -ne 0) {
    throw "SQLite inspection failed with exit code $LASTEXITCODE."
}

$manifest = [ordered]@{
    run_id = $RunId
    backend_url = $BackendUrl
    database_path = $DatabasePath
    actor = $Actor
    created_at = (Get-Date).ToString("o")
    output_root = $OutputRoot
}
$manifest |
    ConvertTo-Json -Depth 10 |
    Set-Content -Path (Join-Path $OutputRoot "inspection-manifest.json") -Encoding utf8

Write-Host ""
Write-Host "Inspection complete." -ForegroundColor Green
Write-Host "Output: $OutputRoot"
Write-Host "Diagnosis: $(Join-Path $dbRoot 'diagnosis.txt')"
Write-Host "Database summary: $(Join-Path $dbRoot 'database-summary.json')"
Write-Host "API status: $(Join-Path $OutputRoot 'api-status.csv')"
