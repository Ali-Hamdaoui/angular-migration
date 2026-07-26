[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\Users\hamdaoui.ali\angular-migration",
    [string]$DataRoot = "$(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'AngularMigrationControlTower' } else { Join-Path $HOME '.local\share\AngularMigrationControlTower' })",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $Force) {
    throw "This deletes the Control Tower SQLite database. Re-run with -Force to confirm."
}

$repo = [System.IO.Path]::GetFullPath($RepoRoot)
$backendRoot = Join-Path $repo "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$data = [System.IO.Path]::GetFullPath($DataRoot)
$db = Join-Path $data "control-tower.db"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Backend virtual environment not found: $python"
}
if ([System.IO.Path]::GetPathRoot($data) -eq $data -or
    [string]::IsNullOrWhiteSpace($data) -or
    $data -notmatch 'AngularMigrationControlTower$') {
    throw "Refusing unsafe data root: $data"
}

if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw "Refusing to remove database files while the backend is listening on port 8000. Stop the backend and retry."
}

New-Item -ItemType Directory -Path $data -Force | Out-Null
foreach ($path in @($db, "$db-wal", "$db-shm")) {
    if (Test-Path -LiteralPath $path) {
        try {
            Remove-Item -LiteralPath $path -Force -ErrorAction Stop
        }
        catch {
            throw "Could not remove '$path'. A process still has the database open. Stop the backend and retry. $($_.Exception.Message)"
        }
    }
}

$env:APPLICATION_DATA_ROOT = $data
$env:DATABASE_URL = "sqlite:///$($db -replace '\\','/')"

Push-Location $backendRoot
try {
    & $python -m alembic -c alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }

    Write-Host "Database reset and migrated: $db" -ForegroundColor Green
}
finally {
    Pop-Location
}
