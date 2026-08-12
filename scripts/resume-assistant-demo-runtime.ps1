[CmdletBinding()]
param([switch]$BackendOnly)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $repoRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$dataRoot = Join-Path $env:LOCALAPPDATA "AngularMigrationControlTower\clean-proof-20260811-114525"
$logs = Join-Path $dataRoot "runtime-logs"

$env:APPLICATION_DATA_ROOT = $dataRoot
$env:DATABASE_URL = "sqlite:///C:/Users/ilyas.abarbach/AppData/Local/AngularMigrationControlTower/clean-proof-20260811-114525/control-tower.db"
$env:ALLOWED_SOURCE_ROOTS = "C:\amd\angular-crud-poc-main-angular-21-d447395a0660\.migration-factory\runs\run-0f8d0d812454\stage-sandboxes\.sealed\angular-19-to-20--75f38f3ba8fdd3ea"
$env:ALLOWED_TARGET_ROOTS = "C:\amf"
$env:BACKEND_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
$env:NPM_CONFIG_REGISTRY = "https://registry.npmjs.org/"
$env:NPM_CONFIG_STRICT_SSL = "true"
$env:LLM_ENABLED = "true"

$api = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "api-resume.stdout.log") -RedirectStandardError (Join-Path $logs "api-resume.stderr.log") -PassThru
$worker = if (-not $BackendOnly) {
    Start-Process -FilePath $python -ArgumentList @("-m", "app.orchestration.transformer_worker") -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "worker-resume.stdout.log") -RedirectStandardError (Join-Path $logs "worker-resume.stderr.log") -PassThru
}

[pscustomobject]@{ ApiPid = $api.Id; WorkerPid = if ($worker) { $worker.Id } else { $null } }
