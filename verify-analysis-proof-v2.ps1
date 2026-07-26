param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [string]$BackendUrl = "http://127.0.0.1:8000",

    [string]$DatabasePath,

    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$base = $BackendUrl.TrimEnd("/")

function Resolve-DatabasePath {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath)) {
            throw "Database not found: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $root = Join-Path $env:LOCALAPPDATA "AngularMigrationControlTower"
    $candidate = Get-ChildItem -Path $root -Filter "control-tower.db" -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $candidate) {
        throw "No control-tower.db found under $root. Pass -DatabasePath explicitly."
    }

    return $candidate.FullName
}

function Get-ApiJson {
    param([string]$Path)

    try {
        return Invoke-RestMethod `
            -Uri "$base$Path" `
            -Method Get `
            -TimeoutSec 30
    }
    catch {
        Write-Host "API warning: GET $Path failed: $($_.Exception.Message)" -ForegroundColor Yellow
        return $null
    }
}

$db = Resolve-DatabasePath -ExplicitPath $DatabasePath
Write-Host "`nRun:      $RunId" -ForegroundColor Cyan
Write-Host "Database: $db"
Write-Host "Backend:  $base"

# API discovery gives the most direct scanner projection.
$discovery = Get-ApiJson "/api/v1/runs/$RunId/discovery"
$state = Get-ApiJson "/api/v1/runs/$RunId/state"
$readiness = Get-ApiJson "/api/v1/llm/readiness"

$tempPy = Join-Path $env:TEMP ("verify-analysis-proof-" + [guid]::NewGuid().ToString("N") + ".py")
$tempJson = Join-Path $env:TEMP ("verify-analysis-proof-" + [guid]::NewGuid().ToString("N") + ".json")

$python = @'
import json
import sqlite3
import sys
from pathlib import Path

db_path, run_id, output_path = sys.argv[1:4]
conn = sqlite3.connect(db_path, timeout=30)
conn.row_factory = sqlite3.Row

def tables():
    return [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]

TABLES = tables()

def columns(table):
    return [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]

def first_table(exact=None, contains_all=()):
    if exact and exact in TABLES:
        return exact
    for table in TABLES:
        lower = table.lower()
        if all(token in lower for token in contains_all):
            return table
    return None

def parse_json(value):
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}

def rows_for_run(table):
    if not table:
        return []
    cols = columns(table)
    if "run_id" not in cols:
        return []
    order = ""
    for candidate in ("sequence", "created_at", "occurred_at", "id"):
        if candidate in cols:
            order = f' ORDER BY "{candidate}"'
            break
    sql = f'SELECT * FROM "{table}" WHERE run_id = ?{order}'
    return [dict(r) for r in conn.execute(sql, (run_id,)).fetchall()]

event_table = first_table(exact="workflow_events", contains_all=("workflow", "event"))
event_rows = rows_for_run(event_table)

events = []
for row in event_rows:
    payload = {}
    for key in ("payload", "payload_json", "event_payload", "details"):
        if key in row:
            payload = parse_json(row.get(key))
            if payload:
                break
    event_type = row.get("event_type") or row.get("type") or row.get("name")
    events.append({
        "sequence": row.get("sequence"),
        "event_type": event_type,
        "occurred_at": row.get("occurred_at") or row.get("created_at"),
        "payload": payload,
    })

def matching_tables(*tokens):
    result = []
    for table in TABLES:
        lower = table.lower()
        if all(token in lower for token in tokens):
            result.append(table)
    return result

def count_run_rows(candidate_tables):
    details = []
    total = 0
    for table in candidate_tables:
        cols = columns(table)
        if "run_id" not in cols:
            continue
        count = conn.execute(
            f'SELECT COUNT(*) AS count FROM "{table}" WHERE run_id = ?',
            (run_id,),
        ).fetchone()["count"]
        details.append({"table": table, "count": count})
        total += count
    return total, details

llm_tables = matching_tables("llm", "invocation")
usage_tables = matching_tables("usage")
if not usage_tables:
    usage_tables = matching_tables("cost")

llm_count, llm_details = count_run_rows(llm_tables)
usage_count, usage_details = count_run_rows(usage_tables)

# Inspect artifact-like rows for discovery provenance.
artifact_tables = matching_tables("artifact")
artifact_rows = []
for table in artifact_tables:
    cols = columns(table)
    if "run_id" not in cols:
        continue
    try:
        rows = conn.execute(
            f'SELECT * FROM "{table}" WHERE run_id = ?',
            (run_id,),
        ).fetchall()
    except Exception:
        continue
    for raw in rows:
        row = dict(raw)
        path_text = str(
            row.get("relative_path")
            or row.get("path")
            or row.get("artifact_path")
            or ""
        )
        stage_text = str(row.get("stage_id") or "")
        if "02_analysis" not in path_text and "analysis" not in stage_text.lower():
            continue

        extracted = {}
        for key, value in row.items():
            if value is None:
                continue
            if "input_hash" in key.lower():
                extracted[key] = parse_json(value) or value
            elif "metadata" in key.lower() or key.lower().endswith("_json"):
                parsed = parse_json(value)
                if parsed:
                    extracted[key] = parsed

        artifact_rows.append({
            "table": table,
            "artifact_id": row.get("artifact_id") or row.get("id"),
            "relative_path": path_text,
            "stage_id": stage_text,
            "metadata": extracted,
        })

result = {
    "database_path": db_path,
    "tables": TABLES,
    "event_table": event_table,
    "events": events,
    "llm_count": llm_count,
    "llm_details": llm_details,
    "usage_count": usage_count,
    "usage_details": usage_details,
    "artifact_rows": artifact_rows,
}

Path(output_path).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
conn.close()
'@

Set-Content -LiteralPath $tempPy -Value $python -Encoding UTF8

try {
    function Test-PythonExecutable {
        param([string]$Candidate)

        if (-not $Candidate) {
            return $false
        }

        if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return $false
        }

        try {
            $versionOutput = & $Candidate --version 2>&1
            return ($LASTEXITCODE -eq 0 -and "$versionOutput" -match "^Python\s+\d")
        }
        catch {
            return $false
        }
    }

    function Resolve-PythonExecutable {
        param([string]$ExplicitPath)

        $candidates = New-Object System.Collections.Generic.List[string]

        if ($ExplicitPath) {
            $candidates.Add($ExplicitPath)
        }

        if ($env:VIRTUAL_ENV) {
            $candidates.Add((Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"))
        }

        foreach ($relative in @(
            "backend\.venv\Scripts\python.exe",
            "backend\venv\Scripts\python.exe",
            ".venv\Scripts\python.exe",
            "venv\Scripts\python.exe"
        )) {
            $candidates.Add((Join-Path $PSScriptRoot $relative))
        }

        # Fall back to a shallow search for the backend virtual environment.
        $backendRoot = Join-Path $PSScriptRoot "backend"
        if (Test-Path -LiteralPath $backendRoot) {
            Get-ChildItem `
                -LiteralPath $backendRoot `
                -Directory `
                -Force `
                -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -in @(".venv", "venv", "env") } |
                ForEach-Object {
                    $candidates.Add((Join-Path $_.FullName "Scripts\python.exe"))
                }
        }

        foreach ($candidate in $candidates | Select-Object -Unique) {
            if (Test-PythonExecutable -Candidate $candidate) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        }

        # PATH commands are accepted only after a real --version probe.
        foreach ($name in @("py.exe", "py", "python.exe", "python")) {
            $command = Get-Command $name -ErrorAction SilentlyContinue
            if (-not $command) {
                continue
            }

            $source = $command.Source
            if (-not $source) {
                continue
            }

            if ($source -match "\\Microsoft\\WindowsApps\\python(?:3)?\.exe$") {
                continue
            }

            if (Test-PythonExecutable -Candidate $source) {
                return $source
            }
        }

        return $null
    }

    $resolvedPython = Resolve-PythonExecutable -ExplicitPath $PythonPath

    if (-not $resolvedPython) {
        throw @"
A real Python interpreter was not found.

Pass the backend interpreter explicitly, for example:
  -PythonPath "$PSScriptRoot\backend\.venv\Scripts\python.exe"

The WindowsApps python.exe alias was ignored because it is not an installed interpreter.
"@
    }

    Write-Host "Python:   $resolvedPython"
    & $resolvedPython $tempPy $db $RunId $tempJson

    if ($LASTEXITCODE -ne 0) {
        throw "SQLite inspection failed with exit code $LASTEXITCODE using $resolvedPython."
    }

    $dbData = Get-Content -LiteralPath $tempJson -Raw | ConvertFrom-Json
}
finally {
    Remove-Item -LiteralPath $tempPy -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tempJson -Force -ErrorAction SilentlyContinue
}

$eventTypes = @($dbData.events | ForEach-Object { $_.event_type })
$scannerEvents = @($dbData.events | Where-Object { $_.event_type -eq "SCANNER_COMPLETED" })

$scannerResults = @()
if ($discovery) {
    if ($discovery.scanner_results) {
        $scannerResults = @($discovery.scanner_results)
    }
    elseif ($discovery.results) {
        $scannerResults = @($discovery.results)
    }
    elseif ($discovery.scanners) {
        foreach ($property in $discovery.scanners.PSObject.Properties) {
            $scannerResults += [pscustomobject]@{
                scanner = $property.Name
                status = $property.Value.status
                unknowns = $property.Value.unknowns
                warnings = $property.Value.warnings
            }
        }
    }
}

$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Evidence
    )

    $checks.Add([pscustomobject]@{
        Result = $(if ($Passed) { "PASS" } else { "FAIL" })
        Check = $Name
        Evidence = $Evidence
    })
}

Add-Check "DISCOVERY_STARTED exists" `
    ($eventTypes -contains "DISCOVERY_STARTED") `
    "count=$(@($eventTypes | Where-Object { $_ -eq 'DISCOVERY_STARTED' }).Count)"

Add-Check "Exactly seven scanner completions" `
    ($scannerEvents.Count -eq 7) `
    "count=$($scannerEvents.Count)"

Add-Check "DISCOVERY_COMPLETED exists" `
    ($eventTypes -contains "DISCOVERY_COMPLETED") `
    "present=$($eventTypes -contains 'DISCOVERY_COMPLETED')"

Add-Check "DISCOVERY_BLOCKED absent" `
    (-not ($eventTypes -contains "DISCOVERY_BLOCKED")) `
    "present=$($eventTypes -contains 'DISCOVERY_BLOCKED')"

if ($scannerResults.Count -gt 0) {
    $badScanners = @(
        $scannerResults |
            Where-Object { $_.status -ne "completed" } |
            ForEach-Object {
                $unknownText = @($_.unknowns) -join ","
                "$($_.scanner):$($_.status):$unknownText"
            }
    )

    Add-Check "All seven scanners completed" `
        (($scannerResults.Count -eq 7) -and ($badScanners.Count -eq 0)) `
        "scanner_count=$($scannerResults.Count); bad=$($badScanners -join ' | ')"
}
else {
    Add-Check "All seven scanners completed" $false "Discovery API unavailable or returned no scanner projection."
}

$missingEventProvenance = @()
foreach ($event in $scannerEvents) {
    $payload = $event.payload
    $scannerName = if ($payload.scanner) { $payload.scanner } else { "unknown-scanner" }

    if (-not $payload.snapshot_id) {
        $missingEventProvenance += "${scannerName}:snapshot_id"
    }
    if (-not $payload.discovery_root) {
        $missingEventProvenance += "${scannerName}:discovery_root"
    }
}

Add-Check "Scanner events contain snapshot_id and discovery_root" `
    (($scannerEvents.Count -eq 7) -and ($missingEventProvenance.Count -eq 0)) `
    "missing=$($missingEventProvenance -join ', ')"

# Search all persisted artifact metadata recursively for required provenance.
$artifactJson = $dbData.artifact_rows | ConvertTo-Json -Depth 50 -Compress
$hasInputHashes = $artifactJson -match '"input_hash'
$hasAngularJson = $artifactJson -match 'angular\.json'
$hasChecksum = $artifactJson -match '(sha256:|checksum)'
$hasSnapshotId = $artifactJson -match 'snapshot-[A-Za-z0-9_-]+'

Add-Check "Discovery artifacts contain non-empty input provenance" `
    ($hasInputHashes -and $hasChecksum -and $hasSnapshotId) `
    "input_hashes=$hasInputHashes; checksum=$hasChecksum; snapshot_id=$hasSnapshotId"

Add-Check "Angular scanner artifacts reference angular.json" `
    $hasAngularJson `
    "angular_json_reference=$hasAngularJson"

Add-Check "ANALYSIS_AGENT_STARTED exists" `
    ($eventTypes -contains "ANALYSIS_AGENT_STARTED") `
    "present=$($eventTypes -contains 'ANALYSIS_AGENT_STARTED')"

Add-Check "Governed LLM invocation row exists" `
    ([int]$dbData.llm_count -gt 0) `
    "count=$($dbData.llm_count); tables=$(
        @($dbData.llm_details | ForEach-Object { "$($_.table)=$($_.count)" }) -join ', '
    )"

Add-Check "LLM usage/cost row exists" `
    ([int]$dbData.usage_count -gt 0) `
    "count=$($dbData.usage_count); tables=$(
        @($dbData.usage_details | ForEach-Object { "$($_.table)=$($_.count)" }) -join ', '
    )"

Add-Check "ANALYSIS_AGENT_COMPLETED exists" `
    ($eventTypes -contains "ANALYSIS_AGENT_COMPLETED") `
    "present=$($eventTypes -contains 'ANALYSIS_AGENT_COMPLETED')"

Add-Check "ANALYSIS_REVIEWER_COMPLETED exists" `
    ($eventTypes -contains "ANALYSIS_REVIEWER_COMPLETED") `
    "present=$($eventTypes -contains 'ANALYSIS_REVIEWER_COMPLETED')"

Add-Check "G04_CREATED exists" `
    ($eventTypes -contains "G04_CREATED") `
    "present=$($eventTypes -contains 'G04_CREATED')"

Write-Host "`n=== ACCEPTANCE CHECKS ===" -ForegroundColor Cyan
$checks | Format-Table -AutoSize -Wrap

Write-Host "`n=== CURRENT STATE ===" -ForegroundColor Cyan
if ($state) {
    $state |
        Select-Object run_id, status, run_phase, phase_status,
            approval_status, state_version, updated_at |
        Format-List
}

Write-Host "`n=== LLM READINESS ===" -ForegroundColor Cyan
if ($readiness) {
    $readiness |
        Select-Object status, provider, deployment_configured,
            model_capability, error_code |
        Format-List
}

$failed = @($checks | Where-Object { $_.Result -eq "FAIL" })
Write-Host "`n=== FINAL VERDICT ===" -ForegroundColor Cyan

if ($failed.Count -eq 0) {
    Write-Host "PASS: Discovery -> Analysis -> Reviewer -> G04 is runtime-proven." -ForegroundColor Green
    exit 0
}

Write-Host "FAIL: $($failed.Count) acceptance checks are not satisfied." -ForegroundColor Red

if ($eventTypes -contains "DISCOVERY_BLOCKED") {
    Write-Host "Immediate blocker: DISCOVERY_BLOCKED." -ForegroundColor Red
}

if (-not ($eventTypes -contains "ANALYSIS_AGENT_STARTED")) {
    Write-Host "Analysis and Azure invocation were never reached." -ForegroundColor Yellow
}

exit 1
