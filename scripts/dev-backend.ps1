[CmdletBinding()]
param(
    [string]$TargetRoot = "C:\Users\hamdaoui.ali\Downloads\MSA-COMMON-STG1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$Reload
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
        throw "Unable to stop process tree node ${ProcessId}: $($_.Exception.Message)"
    }

    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Wait-Process -Id $ProcessId -Timeout 5 -ErrorAction SilentlyContinue
    }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        throw "Factory process $ProcessId did not stop."
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
$launcherMutex = $null
$ownsLauncherMutex = $false
$runtimeActivated = $false

try {
    New-Item -ItemType Directory -Force -Path $resolvedTargetRoot | Out-Null
    $resolvedTargetRoot = (Resolve-Path -LiteralPath $resolvedTargetRoot).Path
    $env:ALLOWED_TARGET_ROOTS = $resolvedTargetRoot

    Push-Location $backendRoot
    $locationPushed = $true

    $databasePathOutput = & $python -c "from app.core.config import get_settings; from app.core.database import database_path; s=get_settings(); print(database_path(s.database_url) or s.database_url)"
    if ($LASTEXITCODE -ne 0) {
        throw "Backend database identity resolution failed with exit code $LASTEXITCODE."
    }
    $databasePath = ($databasePathOutput | Select-Object -Last 1).Trim()
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $databaseIdentity = -join ($sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($databasePath)) | ForEach-Object { $_.ToString("x2") })
    }
    finally {
        $sha256.Dispose()
    }
    $launcherMutex = [System.Threading.Mutex]::new($false, "AngularMigrationFactory-$databaseIdentity")
    try {
        $ownsLauncherMutex = $launcherMutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        $ownsLauncherMutex = $true
    }
    if (-not $ownsLauncherMutex) {
        throw "Another Factory launcher already owns database: $databasePath"
    }

    $factorySha = (& git -C $repoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($factorySha)) {
        throw "Unable to resolve Factory git SHA."
    }
    $runtimeGeneration = "factory-runtime-" + [guid]::NewGuid().ToString("N")
    $env:FACTORY_RUNTIME_GENERATION = $runtimeGeneration
    $env:FACTORY_GIT_SHA = $factorySha
    $env:FACTORY_DATABASE_IDENTITY = $databaseIdentity
    $env:FACTORY_LAUNCHER_PID = $PID.ToString()

    Write-Host "Applying backend database migrations..." -ForegroundColor Cyan
    & $python -m alembic -c alembic.ini upgrade heads
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic migration failed with exit code $LASTEXITCODE."
    }

    $env:FACTORY_RUNTIME_ACTION = "activate"
    & $python -m app.services.factory_runtime_service
    if ($LASTEXITCODE -ne 0) {
        throw "Factory runtime activation failed with exit code $LASTEXITCODE."
    }
    $runtimeActivated = $true

    & $python -c "from app.core.config import get_settings; from app.core.database import database_path; print('Backend database: ' + str(database_path(get_settings().database_url)))"
    if ($LASTEXITCODE -ne 0) {
        throw "Backend configuration validation failed with exit code $LASTEXITCODE."
    }

    $uvicornArguments = @(
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        $Port.ToString()
    )
    if ($Reload) {
        Write-Warning "DEVELOPMENT RELOAD MODE - NOT FOR MIGRATION CERTIFICATION"
        $uvicornArguments += "--reload"
    }
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
    Write-Host "Factory SHA: $factorySha"
    Write-Host "Factory runtime generation: $runtimeGeneration"
    Write-Host "Factory database identity: $databaseIdentity"
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

    if ($runtimeActivated) {
        $env:FACTORY_RUNTIME_ACTION = "retire"
        & $python -m app.services.factory_runtime_service
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

    if ($ownsLauncherMutex) {
        $launcherMutex.ReleaseMutex()
    }
    if ($null -ne $launcherMutex) {
        $launcherMutex.Dispose()
    }
}
