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

function Get-ProcessTreeIds {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [int[]]$RootProcessIds,

        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]]$ProcessSnapshot
    )

    $childrenByParent = @{}
    foreach ($processInfo in $ProcessSnapshot) {
        $parentId = [int]$processInfo.ParentProcessId
        if (-not $childrenByParent.ContainsKey($parentId)) {
            $childrenByParent[$parentId] = @()
        }
        $childrenByParent[$parentId] += [int]$processInfo.ProcessId
    }

    $depthById = @{}
    $pending = [System.Collections.Generic.Queue[int]]::new()
    foreach ($rootId in $RootProcessIds) {
        if (-not $depthById.ContainsKey($rootId)) {
            $depthById[$rootId] = 0
            $pending.Enqueue($rootId)
        }
    }

    while ($pending.Count -gt 0) {
        $parentId = $pending.Dequeue()
        if (-not $childrenByParent.ContainsKey($parentId)) {
            continue
        }
        foreach ($childId in @($childrenByParent[$parentId])) {
            if ($depthById.ContainsKey($childId)) {
                continue
            }
            $depthById[$childId] = [int]$depthById[$parentId] + 1
            $pending.Enqueue($childId)
        }
    }

    $depthById.GetEnumerator() |
        Sort-Object -Property @{ Expression = "Value"; Descending = $true }, @{ Expression = "Key"; Descending = $true } |
        ForEach-Object { [int]$_.Key }
}

function Stop-WindowsProcessTree {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [int]$RootProcessId
    )

    # taskkill /T resolves the live Windows tree before terminating its root,
    # avoiding broken parent chains from venv launchers and Uvicorn reloads.
    & taskkill.exe /PID $RootProcessId /T /F 2>$null | Out-Null
}

function Stop-BackendProcessTrees {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object[]]$Processes
    )

    $rootProcessIds = @(
        $Processes |
            Where-Object { $null -ne $_ } |
            ForEach-Object { [int]$_.Id }
    )
    if ($rootProcessIds.Count -eq 0) {
        return
    }

    # Stop the two supervisors first so Uvicorn cannot reload and the worker
    # cannot claim or launch new commands while descendants are being drained.
    foreach ($rootProcessId in $rootProcessIds) {
        Stop-WindowsProcessTree -RootProcessId $rootProcessId
        Stop-Process -Id $rootProcessId -Force -ErrorAction SilentlyContinue
    }
    foreach ($rootProcessId in $rootProcessIds) {
        Wait-Process -Id $rootProcessId -Timeout 1 -ErrorAction SilentlyContinue
    }

    $knownProcessIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($rootProcessId in $rootProcessIds) {
        $null = $knownProcessIds.Add($rootProcessId)
    }
    $consecutiveEmptyPasses = 0

    foreach ($pass in 1..25) {
        $snapshot = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
        $activeProcessIds = [System.Collections.Generic.HashSet[int]]::new()
        foreach ($processInfo in $snapshot) {
            $null = $activeProcessIds.Add([int]$processInfo.ProcessId)
        }
        foreach ($knownProcessId in $knownProcessIds) {
            if ($null -ne (Get-Process -Id $knownProcessId -ErrorAction SilentlyContinue)) {
                $null = $activeProcessIds.Add($knownProcessId)
            }
        }
        $discoveredProcessIds = @(
            Get-ProcessTreeIds -RootProcessIds @($knownProcessIds) -ProcessSnapshot $snapshot
        )
        foreach ($discoveredProcessId in $discoveredProcessIds) {
            $null = $knownProcessIds.Add([int]$discoveredProcessId)
        }
        $processTreeIds = @(
            $discoveredProcessIds |
                Where-Object { $activeProcessIds.Contains([int]$_) }
        )
        if ($processTreeIds.Count -eq 0) {
            $consecutiveEmptyPasses++
            if ($consecutiveEmptyPasses -ge 10) {
                # Finish with a blind stop of every PID ever observed. Windows
                # process providers can briefly omit a terminating venv or
                # reload launcher even though its process object still exists.
                foreach ($knownProcessId in $knownProcessIds) {
                    Stop-Process -Id $knownProcessId -Force -ErrorAction SilentlyContinue
                }
                foreach ($knownProcessId in $knownProcessIds) {
                    Wait-Process -Id $knownProcessId -Timeout 1 -ErrorAction SilentlyContinue
                }
                Start-Sleep -Milliseconds 500
                $stillRunningIds = [System.Collections.Generic.HashSet[int]]::new()
                @(
                    $knownProcessIds |
                        Where-Object {
                            $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue)
                        }
                ) | ForEach-Object { $null = $stillRunningIds.Add([int]$_) }
                @(
                    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                        Where-Object { $knownProcessIds.Contains([int]$_.ProcessId) }
                ) | ForEach-Object { $null = $stillRunningIds.Add([int]$_.ProcessId) }
                if ($stillRunningIds.Count -eq 0) {
                    return
                }
                $consecutiveEmptyPasses = 0
            }
            Start-Sleep -Milliseconds 100
            continue
        }
        $consecutiveEmptyPasses = 0
        foreach ($processId in $processTreeIds) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        foreach ($processId in $processTreeIds) {
            Wait-Process -Id $processId -Timeout 1 -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds 100
    }

    throw "Backend process-tree cleanup did not complete after repeated termination checks."
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
        [object[]]$Specifications
    )

    $started = @()
    try {
        foreach ($specification in $Specifications) {
            $started += Start-Process `
                -FilePath $specification.FilePath `
                -ArgumentList $specification.Arguments `
                -WorkingDirectory $specification.WorkingDirectory `
                -NoNewWindow `
                -PassThru
        }
        return $started
    }
    catch {
        Stop-BackendProcessTrees -Processes $started
        throw
    }
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
    try {
        $processes = @(Start-BackendRuntimeProcesses -Specifications $specifications)
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
        if ($processes.Count -gt 0) {
            Write-Host "Stopping backend API and Transformer worker..." -ForegroundColor Yellow
            Stop-BackendProcessTrees -Processes $processes
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
