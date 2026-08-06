[CmdletBinding()]
param(
    [string]$TargetRoot = "C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = (Resolve-Path (Join-Path $repoRoot "backend")).Path
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Backend virtual environment not found: $python. Create backend\.venv and install the backend dependencies first."
}

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    throw "TargetRoot must not be empty."
}

$resolvedTargetRoot = [System.IO.Path]::GetFullPath($TargetRoot)
$targetRootName = [System.IO.Path]::GetPathRoot($resolvedTargetRoot)
if ($targetRootName -and $resolvedTargetRoot.TrimEnd('\') -eq $targetRootName.TrimEnd('\')) {
    throw "TargetRoot must not be a filesystem root: $resolvedTargetRoot"
}

function Get-ChildProcessIds {
    param(
        [Parameter(Mandatory)]
        [int]$ParentProcessId
    )

    try {
        $children = @(
            Get-CimInstance `
                -ClassName Win32_Process `
                -Filter "ParentProcessId = $ParentProcessId" `
                -ErrorAction Stop
        )
    }
    catch {
        return
    }

    foreach ($child in $children) {
        $childId = [int]$child.ProcessId
        Get-ChildProcessIds -ParentProcessId $childId
        $childId
    }
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory)]
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return
    }

    $descendantIds = @(Get-ChildProcessIds -ParentProcessId $ProcessId)
    foreach ($descendantId in $descendantIds) {
        Stop-ProcessTree -ProcessId $descendantId
    }

    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        if (-not $process.HasExited) {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        }
    }
    catch [System.ArgumentException] {
        # The process exited between discovery and cleanup.
    }
    catch {
        Write-Warning "Unable to stop process tree node ${ProcessId}: $($_.Exception.Message)"
    }
}

function Assert-ProcessRunning {
    param(
        [Parameter(Mandatory)]
        [System.Diagnostics.Process]$Process,

        [Parameter(Mandatory)]
        [string]$ProcessName
    )

    $Process.Refresh()
    if ($Process.HasExited) {
        throw "$ProcessName exited during startup with code $($Process.ExitCode)."
    }
}

$previousAllowedTargetRoots = [System.Environment]::GetEnvironmentVariable(
    "ALLOWED_TARGET_ROOTS",
    "Process"
)
$locationPushed = $false
$uvicornProcess = $null
$transformerProcess = $null

try {
    New-Item -ItemType Directory -Force -Path $resolvedTargetRoot | Out-Null
    $resolvedTargetRoot = (Resolve-Path -LiteralPath $resolvedTargetRoot).Path
    $env:ALLOWED_TARGET_ROOTS = $resolvedTargetRoot

    Push-Location $backendRoot
    $locationPushed = $true

    Write-Host "Applying backend database migrations..." -ForegroundColor Cyan
    & $python -m alembic -c alembic.ini upgrade heads
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic migration failed with exit code $LASTEXITCODE."
    }

    & $python -c "from app.core.config import get_settings; from app.core.database import database_path; print('Backend database: ' + str(database_path(get_settings().database_url)))"
    if ($LASTEXITCODE -ne 0) {
        throw "Backend configuration validation failed with exit code $LASTEXITCODE."
    }

    $uvicornArguments = @(
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        $Port.ToString()
    )
    $transformerArguments = @(
        "-m",
        "app.orchestration.transformer_worker"
    )

    Write-Host "Starting FastAPI on http://127.0.0.1:$Port" -ForegroundColor Green
    $uvicornProcess = Start-Process `
        -FilePath $python `
        -ArgumentList $uvicornArguments `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -PassThru
    Start-Sleep -Milliseconds 500
    Assert-ProcessRunning -Process $uvicornProcess -ProcessName "Uvicorn"

    Write-Host "Starting the Transformer/command worker..." -ForegroundColor Green
    $transformerProcess = Start-Process `
        -FilePath $python `
        -ArgumentList $transformerArguments `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -PassThru
    Start-Sleep -Milliseconds 500
    Assert-ProcessRunning -Process $transformerProcess -ProcessName "Transformer worker"

    Write-Host "Backend target root: $resolvedTargetRoot" -ForegroundColor Yellow
    Write-Host "Uvicorn process ID: $($uvicornProcess.Id)"
    Write-Host "Transformer worker process ID: $($transformerProcess.Id)"
    Write-Host "Press Ctrl+C to stop the API and Transformer worker." -ForegroundColor Yellow

    while ($true) {
        Start-Sleep -Seconds 1

        Assert-ProcessRunning -Process $uvicornProcess -ProcessName "Uvicorn"
        Assert-ProcessRunning -Process $transformerProcess -ProcessName "Transformer worker"
    }
}
finally {
    if ($null -ne $transformerProcess) {
        Stop-ProcessTree -ProcessId $transformerProcess.Id
    }

    if ($null -ne $uvicornProcess) {
        Stop-ProcessTree -ProcessId $uvicornProcess.Id
    }

    if ($locationPushed) {
        Pop-Location
    }

    if ($null -eq $previousAllowedTargetRoots) {
        Remove-Item Env:ALLOWED_TARGET_ROOTS -ErrorAction SilentlyContinue
    }
    else {
        $env:ALLOWED_TARGET_ROOTS = $previousAllowedTargetRoots
    }
}
