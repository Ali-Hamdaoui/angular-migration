[CmdletBinding()]
param(
    [string]$TargetRoot = (Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads\MSA-COMMON-STG1"),

    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Initialize-BackendTargetRoot {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$TargetRoot
    )

    if ($TargetRoot.Contains(",")) {
        throw "TargetRoot cannot contain a comma."
    }

    New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
    $resolvedTargetRoot = (Resolve-Path -LiteralPath $TargetRoot).Path
    $env:ALLOWED_TARGET_ROOTS = $resolvedTargetRoot
    return $resolvedTargetRoot
}

function Get-BackendProcessSpecifications {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$BackendRoot,

        [Parameter(Mandatory)]
        [string]$PythonPath,

        [Parameter(Mandatory)]
        [int]$Port
    )

    return @(
        [pscustomobject]@{
            Name = "api"
            FilePath = $PythonPath
            WorkingDirectory = $BackendRoot
            Arguments = @(
                "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1",
                "--port", $Port.ToString(),
                "--reload"
            )
        },
        [pscustomobject]@{
            Name = "transformer-worker"
            FilePath = $PythonPath
            WorkingDirectory = $BackendRoot
            Arguments = @("-m", "app.orchestration.transformer_worker")
        }
    )
}

function New-BackendRuntimeJob {
    [CmdletBinding()]
    param()

    if (-not ("BackendRuntimeJob" -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot "BackendRuntimeJob.cs")
    }
    return New-Object BackendRuntimeJob
}

function Invoke-BackendDatabaseMigration {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$BackendRoot,

        [Parameter(Mandatory)]
        [string]$PythonPath
    )

    Push-Location $BackendRoot
    try {
        & $PythonPath -m alembic -c alembic.ini upgrade heads
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic migration failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Start-BackendRuntimeProcesses {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object[]]$Specifications,

        [Parameter(Mandatory)]
        [object]$RuntimeJob
    )

    $started = @()
    foreach ($specification in $Specifications) {
        $started += $RuntimeJob.StartProcess(
            $specification.FilePath,
            [string[]]$specification.Arguments,
            $specification.WorkingDirectory
        )
    }
    return $started
}

function Assert-BackendRuntimeProcessesRunning {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object[]]$Processes,

        [Parameter(Mandatory)]
        [object[]]$Specifications
    )

    foreach ($index in 0..($Processes.Count - 1)) {
        $Processes[$index].Refresh()
        if ($Processes[$index].HasExited) {
            $name = $Specifications[$index].Name
            throw "$name exited with code $($Processes[$index].ExitCode)."
        }
    }
}

function Invoke-BackendDevelopmentRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RepositoryRoot,

        [Parameter(Mandatory)]
        [string]$TargetRoot,

        [Parameter(Mandatory)]
        [int]$Port
    )

    $backendRoot = (Resolve-Path -LiteralPath (Join-Path $RepositoryRoot "backend")).Path
    $pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Backend virtual-environment Python was not found: $pythonPath"
    }

    $resolvedTargetRoot = Initialize-BackendTargetRoot -TargetRoot $TargetRoot
    $venvRoot = Split-Path -Parent (Split-Path -Parent $pythonPath)
    $venvScripts = Split-Path -Parent $pythonPath
    $env:VIRTUAL_ENV = $venvRoot
    if (($env:PATH -split ";") -notcontains $venvScripts) {
        $env:PATH = "$venvScripts;$env:PATH"
    }

    Write-Host "Allowed target root: $resolvedTargetRoot" -ForegroundColor Cyan
    Write-Host "Applying backend database migrations..." -ForegroundColor Cyan
    Invoke-BackendDatabaseMigration -BackendRoot $backendRoot -PythonPath $pythonPath

    $specifications = @(Get-BackendProcessSpecifications `
        -BackendRoot $backendRoot `
        -PythonPath $pythonPath `
        -Port $Port)
    $processes = @()
    $runtimeJob = $null
    try {
        $runtimeJob = New-BackendRuntimeJob
        $processes = @(Start-BackendRuntimeProcesses `
            -Specifications $specifications `
            -RuntimeJob $runtimeJob)
        Write-Host "Backend API: http://127.0.0.1:$Port (PID $($processes[0].Id))" -ForegroundColor Green
        Write-Host "Transformer worker PID: $($processes[1].Id)" -ForegroundColor Green
        Write-Host "Press Ctrl+C to stop both backend processes." -ForegroundColor Yellow

        while ($true) {
            Assert-BackendRuntimeProcessesRunning `
                -Processes $processes `
                -Specifications $specifications
            Start-Sleep -Seconds 1
        }
    }
    finally {
        if ($null -ne $runtimeJob) {
            Write-Host "Stopping backend API and Transformer worker..." -ForegroundColor Yellow
            $runtimeJob.Dispose()
        }
        foreach ($process in $processes) {
            if ($null -ne $process) {
                $process.WaitForExit(5000) | Out-Null
                $process.Dispose()
            }
        }
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    $repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Invoke-BackendDevelopmentRuntime `
        -RepositoryRoot $repositoryRoot `
        -TargetRoot $TargetRoot `
        -Port $Port
}
