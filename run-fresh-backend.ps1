[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\Users\abdelilah.mortaki\Desktop\angular-migration",
    [string]$SourceRoot = "C:\Users\abdelilah.mortaki\Desktop\angular-crud-poc",
    [string]$TargetBaseRoot = "C:\Users\abdelilah.mortaki\Desktop\angularRus",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$backendRoot = Join-Path $RepoRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$venvRoot = Join-Path $backendRoot ".venv"
$venvScripts = Join-Path $venvRoot "Scripts"

$env:VIRTUAL_ENV = $venvRoot
$env:PATH = "$venvScripts;$env:PATH"
$proofName = "clean-proof-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$dataRoot = Join-Path $env:LOCALAPPDATA "AngularMigrationControlTower\$proofName"
$dbPath = Join-Path $dataRoot "control-tower.db"
$proofTarget = Join-Path $TargetBaseRoot $proofName

if (-not (Test-Path $python)) {
    throw "Backend virtual environment not found: $python"
}

# Stop an existing backend on the configured port.
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force
    }

# Create a completely fresh database and target folder.
Remove-Item $dataRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $proofTarget -Recurse -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
New-Item -ItemType Directory -Path $proofTarget -Force | Out-Null

# Backend runtime configuration.
$env:APPLICATION_DATA_ROOT = $dataRoot
$env:DATABASE_URL = "sqlite:///$($dbPath -replace '\\','/')"
$env:ALLOWED_SOURCE_ROOTS = $SourceRoot
$env:ALLOWED_TARGET_ROOTS = $TargetBaseRoot
$env:BACKEND_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
$env:NPM_CONFIG_REGISTRY = "https://registry.npmjs.org/"
$env:NPM_CONFIG_STRICT_SSL = "true"
$env:LLM_ENABLED = "false"

Set-Location $backendRoot

Write-Host ""
Write-Host "Fresh backend configuration" -ForegroundColor Cyan
Write-Host "Database:      $env:DATABASE_URL"
Write-Host "Source root:   $SourceRoot"
Write-Host "Target base:   $TargetBaseRoot"
Write-Host "Target to use: $proofTarget" -ForegroundColor Green
Write-Host ""

& $python -m alembic -c alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Alembic migration failed."
}

Write-Host ""
Write-Host "Backend starting on http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Paste this target into New Migration: $proofTarget" -ForegroundColor Yellow
Write-Host ""

& $python -m uvicorn app.main:app `
    --host 127.0.0.1 `
    --port $Port `
    --reload
