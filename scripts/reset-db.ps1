param(
    [switch]$ConfirmReset,
    [string]$DataRoot = "$(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'AngularMigrationControlTower' } else { Join-Path $HOME '.local\share\AngularMigrationControlTower' })"
)
$ErrorActionPreference = "Stop"
if (-not $ConfirmReset) { throw "Refusing to reset the database without -ConfirmReset." }
$data = [System.IO.Path]::GetFullPath($DataRoot)
if ([System.IO.Path]::GetPathRoot($data) -eq $data -or [string]::IsNullOrWhiteSpace($data) -or $data -notmatch 'AngularMigrationControlTower') {
    throw "Refusing unsafe data root: $data"
}
$db = Join-Path $data "control-tower.db"
New-Item -ItemType Directory -Path $data -Force | Out-Null
foreach ($path in @($db, "$db-wal", "$db-shm")) {
    if (Test-Path -LiteralPath $path) {
        try { Remove-Item -LiteralPath $path -Force -ErrorAction Stop }
        catch { throw "Could not remove '$path'. Stop the backend and retry. $($_.Exception.Message)" }
    }
}
$env:APPLICATION_DATA_ROOT = $data
$env:DATABASE_URL = "sqlite:///$($db -replace '\\','/')"
& (Join-Path $PSScriptRoot "migrate-db.ps1")
