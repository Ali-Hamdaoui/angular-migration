[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\Users\abdelilah.mortaki\Desktop\angular-migration",
    [string]$SourceRoot = "C:\Users\abdelilah.mortaki\Desktop\angular-crud-poc",
    [string]$TargetBaseRoot = "C:\Users\abdelilah.mortaki\Desktop\angularRus",
    [int]$Port = 8000
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

$expectedAlembicHeads = @(
    "20260726_27",
    "20260727_19"
)

$expectedAssistantRoutes = @{
    "/api/v1/runs/{run_id}/assistant/messages" = @("get", "post")
    "/api/v1/runs/{run_id}/assistant/events"   = @("get")
}

function Get-ProcessSnapshot {
    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    )
}

function Test-IsRepositoryUvicornProcess {
    param(
        [Parameter(Mandatory)]
        [object]$ProcessInfo
    )

    $commandLine = [string]$ProcessInfo.CommandLine

    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    $normalizedCommandLine = $commandLine.ToLowerInvariant()
    $normalizedRepoRoot = $RepoRoot.ToLowerInvariant()
    $normalizedBackendRoot = $backendRoot.ToLowerInvariant()

    $isUvicorn = $normalizedCommandLine -match "(^|\s)(uvicorn|python(?:\.exe)?\s+-m\s+uvicorn)(\s|$)"
    $isExpectedApplication = $normalizedCommandLine -match "app\.main:app"
    $belongsToRepository = (
        $normalizedCommandLine.Contains($normalizedRepoRoot) -or
        $normalizedCommandLine.Contains($normalizedBackendRoot)
    )

    return (
        $isUvicorn -and
        $isExpectedApplication -and
        $belongsToRepository
    )
}

function Get-CandidateProcessDepth {
    param(
        [Parameter(Mandatory)]
        [int]$ProcessId,

        [Parameter(Mandatory)]
        [hashtable]$ProcessesById,

        [Parameter(Mandatory)]
        [object]$CandidateIds
    )

    $depth = 0
    $visited = [System.Collections.Generic.HashSet[int]]::new()
    $currentId = $ProcessId

    while ($ProcessesById.ContainsKey($currentId)) {
        if (-not $visited.Add($currentId)) {
            break
        }

        $parentId = [int]$ProcessesById[$currentId].ParentProcessId

        if (
            $parentId -le 0 -or
            -not $CandidateIds.Contains($parentId)
        ) {
            break
        }

        $depth++
        $currentId = $parentId
    }

    return $depth
}

function Stop-ExistingBackendProcesses {
    param(
        [switch]$Quiet
    )

    $processSnapshot = Get-ProcessSnapshot
    $processesById = @{}
    $childrenByParentId = @{}

    foreach ($processInfo in $processSnapshot) {
        $processId = [int]$processInfo.ProcessId
        $parentId = [int]$processInfo.ParentProcessId

        $processesById[$processId] = $processInfo

        if (-not $childrenByParentId.ContainsKey($parentId)) {
            $childrenByParentId[$parentId] = @()
        }

        $childrenByParentId[$parentId] += $processId
    }

    $candidateIds = [System.Collections.Generic.HashSet[int]]::new()

    # Processes currently listening on the configured port.
    $portOwnerIds = @(
        Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue |
            Where-Object {
                $_.OwningProcess -gt 0 -and
                $_.OwningProcess -ne $PID
            } |
            Select-Object -ExpandProperty OwningProcess -Unique
    )

    foreach ($processId in $portOwnerIds) {
        [void]$candidateIds.Add([int]$processId)
    }

    # Repository-specific Uvicorn parent/reloader processes.
    foreach ($processInfo in $processSnapshot) {
        if (Test-IsRepositoryUvicornProcess -ProcessInfo $processInfo) {
            $processId = [int]$processInfo.ProcessId

            if ($processId -gt 0 -and $processId -ne $PID) {
                [void]$candidateIds.Add($processId)
            }
        }
    }

    # Include matching Uvicorn ancestors of port owners.
    foreach ($seedId in @($candidateIds)) {
        $currentId = [int]$seedId
        $visitedAncestors = [System.Collections.Generic.HashSet[int]]::new()

        while ($processesById.ContainsKey($currentId)) {
            if (-not $visitedAncestors.Add($currentId)) {
                break
            }

            $parentId = [int]$processesById[$currentId].ParentProcessId

            if (
                $parentId -le 0 -or
                $parentId -eq $PID -or
                -not $processesById.ContainsKey($parentId)
            ) {
                break
            }

            $parentProcess = $processesById[$parentId]

            if (Test-IsRepositoryUvicornProcess -ProcessInfo $parentProcess) {
                [void]$candidateIds.Add($parentId)
            }

            $currentId = $parentId
        }
    }

    # Include every child/worker descended from the identified processes.
    $queue = [System.Collections.Generic.Queue[int]]::new()

    foreach ($candidateId in @($candidateIds)) {
        $queue.Enqueue([int]$candidateId)
    }

    while ($queue.Count -gt 0) {
        $parentId = $queue.Dequeue()

        if (-not $childrenByParentId.ContainsKey($parentId)) {
            continue
        }

        foreach ($childId in $childrenByParentId[$parentId]) {
            if (
                $childId -gt 0 -and
                $childId -ne $PID -and
                $candidateIds.Add([int]$childId)
            ) {
                $queue.Enqueue([int]$childId)
            }
        }
    }

    if ($candidateIds.Count -eq 0) {
        if (-not $Quiet) {
            Write-Host "No existing repository backend process found." -ForegroundColor DarkGray
        }
    }
    else {
        $candidateDetails = @(
            foreach ($candidateId in $candidateIds) {
                if (-not $processesById.ContainsKey($candidateId)) {
                    continue
                }

                $processInfo = $processesById[$candidateId]

                [PSCustomObject]@{
                    ProcessId       = [int]$processInfo.ProcessId
                    ParentProcessId = [int]$processInfo.ParentProcessId
                    Depth           = Get-CandidateProcessDepth `
                        -ProcessId ([int]$processInfo.ProcessId) `
                        -ProcessesById $processesById `
                        -CandidateIds $candidateIds
                    Name            = [string]$processInfo.Name
                    CommandLine     = [string]$processInfo.CommandLine
                }
            }
        )

        if (-not $Quiet) {
            Write-Host ""
            Write-Host "Existing backend process tree:" -ForegroundColor Yellow

            $candidateDetails |
                Sort-Object `
                    @{ Expression = "Depth"; Descending = $true },
                    @{ Expression = "ProcessId"; Descending = $true } |
                Format-Table `
                    ProcessId,
                    ParentProcessId,
                    Depth,
                    Name,
                    CommandLine `
                    -AutoSize |
                Out-Host
        }

        # Stop deepest children first, then their parents/reloader.
        $stopOrder = @(
            $candidateDetails |
                Sort-Object `
                    @{ Expression = "Depth"; Descending = $true },
                    @{ Expression = "ProcessId"; Descending = $true }
        )

        foreach ($candidate in $stopOrder) {
            if ($candidate.ProcessId -eq $PID) {
                continue
            }

            $runningProcess = Get-Process `
                -Id $candidate.ProcessId `
                -ErrorAction SilentlyContinue

            if ($null -eq $runningProcess) {
                continue
            }

            if (-not $Quiet) {
                Write-Host (
                    "Stopping PID {0} ({1}), parent {2}..." -f
                    $candidate.ProcessId,
                    $candidate.Name,
                    $candidate.ParentProcessId
                )
            }

            Stop-Process `
                -Id $candidate.ProcessId `
                -Force `
                -ErrorAction SilentlyContinue
        }

        $stopDeadline = (Get-Date).AddSeconds(10)

        do {
            $remainingIds = @(
                foreach ($candidateId in $candidateIds) {
                    $remainingProcess = Get-Process `
                        -Id $candidateId `
                        -ErrorAction SilentlyContinue

                    if ($null -ne $remainingProcess) {
                        $candidateId
                    }
                }
            )

            if ($remainingIds.Count -eq 0) {
                break
            }

            Start-Sleep -Milliseconds 250
        }
        while ((Get-Date) -lt $stopDeadline)

        if ($remainingIds.Count -gt 0) {
            throw (
                "Unable to stop backend process IDs: {0}" -f
                ($remainingIds -join ", ")
            )
        }
    }

    # Verify that the configured port is actually free.
    $portDeadline = (Get-Date).AddSeconds(10)
    $remainingListeners = @()

    do {
        $remainingListeners = @(
            Get-NetTCPConnection `
                -LocalPort $Port `
                -State Listen `
                -ErrorAction SilentlyContinue
        )

        if ($remainingListeners.Count -eq 0) {
            break
        }

        Start-Sleep -Milliseconds 250
    }
    while ((Get-Date) -lt $portDeadline)

    if ($remainingListeners.Count -gt 0) {
        $freshSnapshot = Get-ProcessSnapshot
        $listenerDescriptions = @(
            foreach ($listener in $remainingListeners) {
                $ownerId = [int]$listener.OwningProcess
                $owner = $freshSnapshot |
                    Where-Object { [int]$_.ProcessId -eq $ownerId } |
                    Select-Object -First 1

                if ($null -ne $owner) {
                    "PID=$ownerId Name=$($owner.Name) CommandLine=$($owner.CommandLine)"
                }
                else {
                    "PID=$ownerId"
                }
            }
        )

        throw (
            "Port $Port is still occupied after cleanup. " +
            ($listenerDescriptions -join " | ")
        )
    }

    # Verify that no matching Uvicorn reloader remains.
    $remainingRepositoryUvicorn = @(
        Get-ProcessSnapshot |
            Where-Object {
                $_.ProcessId -ne $PID -and
                (Test-IsRepositoryUvicornProcess -ProcessInfo $_)
            }
    )

    if ($remainingRepositoryUvicorn.Count -gt 0) {
        $remainingDescriptions = @(
            $remainingRepositoryUvicorn |
                ForEach-Object {
                    "PID=$($_.ProcessId) Parent=$($_.ParentProcessId) CommandLine=$($_.CommandLine)"
                }
        )

        throw (
            "Repository Uvicorn processes remain after cleanup: " +
            ($remainingDescriptions -join " | ")
        )
    }

    if (-not $Quiet) {
        Write-Host "Backend process cleanup completed. Port $Port is free." -ForegroundColor Green
    }
}

function Invoke-PythonCapture {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $capturedLines = @()
    $exitCode = $null

    try {
        # Alembic writes normal INFO logs to stderr. Windows PowerShell can
        # otherwise convert those lines into terminating NativeCommandError
        # records when ErrorActionPreference is Stop.
        $ErrorActionPreference = "Continue"

        $capturedLines = @(
            & $python @Arguments 2>&1 |
                ForEach-Object { $_.ToString() }
        )

        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return [PSCustomObject]@{
        Lines    = $capturedLines
        ExitCode = $exitCode
    }
}

function Wait-ForBackendOpenApi {
    param(
        [Parameter(Mandatory)]
        [System.Diagnostics.Process]$UvicornProcess,

        [int]$TimeoutSeconds = 60
    )

    $openApiUri = "http://127.0.0.1:$Port/openapi.json"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastFailure = $null

    while ((Get-Date) -lt $deadline) {
        $UvicornProcess.Refresh()

        if ($UvicornProcess.HasExited) {
            throw (
                "Uvicorn exited before becoming ready. Exit code: {0}" -f
                $UvicornProcess.ExitCode
            )
        }

        try {
            return Invoke-RestMethod `
                -Uri $openApiUri `
                -Method Get `
                -TimeoutSec 5
        }
        catch {
            $lastFailure = $_.Exception.Message
            Start-Sleep -Seconds 1
        }
    }

    throw (
        "Backend did not expose OpenAPI within $TimeoutSeconds seconds. " +
        "Last error: $lastFailure"
    )
}

function Assert-AssistantRoutes {
    param(
        [Parameter(Mandatory)]
        [object]$OpenApiSchema
    )

    $availablePathNames = @(
        $OpenApiSchema.paths.PSObject.Properties.Name
    )

    Write-Host ""
    Write-Host "Live Assistant OpenAPI routes:" -ForegroundColor Cyan

    $assistantPathNames = @(
        $availablePathNames |
            Where-Object { $_ -match "assistant" } |
            Sort-Object
    )

    foreach ($assistantPath in $assistantPathNames) {
        $pathProperty = $OpenApiSchema.paths.PSObject.Properties |
            Where-Object { $_.Name -eq $assistantPath } |
            Select-Object -First 1

        $methods = @(
            $pathProperty.Value.PSObject.Properties.Name |
                Where-Object {
                    $_ -in @(
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                        "options",
                        "head"
                    )
                }
        )

        Write-Host (
            "{0,-12} {1}" -f
            (($methods | ForEach-Object { $_.ToUpperInvariant() }) -join ","),
            $assistantPath
        )
    }

    foreach ($expectedRoute in $expectedAssistantRoutes.GetEnumerator()) {
        $routePath = [string]$expectedRoute.Key
        $requiredMethods = @($expectedRoute.Value)

        if ($availablePathNames -notcontains $routePath) {
            throw "Required Assistant route is absent from live OpenAPI: $routePath"
        }

        $routeProperty = $OpenApiSchema.paths.PSObject.Properties |
            Where-Object { $_.Name -eq $routePath } |
            Select-Object -First 1

        $registeredMethods = @(
            $routeProperty.Value.PSObject.Properties.Name |
                ForEach-Object { $_.ToLowerInvariant() }
        )

        foreach ($requiredMethod in $requiredMethods) {
            if ($registeredMethods -notcontains $requiredMethod.ToLowerInvariant()) {
                throw (
                    "Assistant route $routePath is missing required method " +
                    "$($requiredMethod.ToUpperInvariant())."
                )
            }
        }
    }

    Write-Host ""
    Write-Host "All required Assistant routes are registered in the live backend." -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repository root not found: $RepoRoot"
}

if (-not (Test-Path -LiteralPath $backendRoot -PathType Container)) {
    throw "Backend directory not found: $backendRoot"
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Backend virtual environment not found: $python"
}

if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    throw "Source root not found: $SourceRoot"
}

if (-not (Test-Path -LiteralPath $TargetBaseRoot -PathType Container)) {
    New-Item `
        -ItemType Directory `
        -Path $TargetBaseRoot `
        -Force |
        Out-Null
}

Write-Host ""
Write-Host "Cleaning existing backend processes..." -ForegroundColor Cyan

Stop-ExistingBackendProcesses

# Create a completely fresh database and target folder.
Remove-Item `
    -LiteralPath $dataRoot `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item `
    -LiteralPath $proofTarget `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

New-Item `
    -ItemType Directory `
    -Path $dataRoot `
    -Force |
    Out-Null

New-Item `
    -ItemType Directory `
    -Path $proofTarget `
    -Force |
    Out-Null

# Backend runtime configuration.
$env:APPLICATION_DATA_ROOT = $dataRoot
$env:DATABASE_URL = "sqlite:///$($dbPath -replace '\\', '/')"
$env:ALLOWED_SOURCE_ROOTS = $SourceRoot
$env:ALLOWED_TARGET_ROOTS = $TargetBaseRoot
$env:BACKEND_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
$env:NPM_CONFIG_REGISTRY = "https://registry.npmjs.org/"
$env:NPM_CONFIG_STRICT_SSL = "true"
$env:LLM_ENABLED = "true"

Set-Location $backendRoot

Write-Host ""
Write-Host "Fresh backend configuration" -ForegroundColor Cyan
Write-Host "Repository:    $RepoRoot"
Write-Host "Backend:       $backendRoot"
Write-Host "Database:      $env:DATABASE_URL"
Write-Host "Source root:   $SourceRoot"
Write-Host "Target base:   $TargetBaseRoot"
Write-Host "Target to use: $proofTarget" -ForegroundColor Green
Write-Host ""

Write-Host "Available Alembic heads:" -ForegroundColor Cyan

$headsResult = Invoke-PythonCapture -Arguments @(
    "-m",
    "alembic",
    "-c",
    "alembic.ini",
    "heads"
)

$headsResult.Lines |
    ForEach-Object { Write-Host $_ }

if ($headsResult.ExitCode -ne 0) {
    throw "Unable to inspect Alembic heads. Exit code: $($headsResult.ExitCode)"
}

foreach ($expectedHead in $expectedAlembicHeads) {
    if (-not ($headsResult.Lines -match [regex]::Escape($expectedHead))) {
        throw "Expected Alembic head is missing: $expectedHead"
    }
}

Write-Host ""
Write-Host "Applying all Alembic heads..." -ForegroundColor Cyan

& $python -m alembic -c alembic.ini upgrade heads

if ($LASTEXITCODE -ne 0) {
    throw "Alembic migration failed. Exit code: $LASTEXITCODE"
}

Write-Host ""
Write-Host "Applied Alembic revisions:" -ForegroundColor Cyan

$currentResult = Invoke-PythonCapture -Arguments @(
    "-m",
    "alembic",
    "-c",
    "alembic.ini",
    "current"
)

$currentResult.Lines |
    ForEach-Object { Write-Host $_ }

if ($currentResult.ExitCode -ne 0) {
    throw (
        "Unable to inspect applied Alembic revisions. Exit code: " +
        $currentResult.ExitCode
    )
}

foreach ($expectedHead in $expectedAlembicHeads) {
    if (-not ($currentResult.Lines -match [regex]::Escape($expectedHead))) {
        throw "Fresh database did not reach expected Alembic head: $expectedHead"
    }
}

Write-Host ""
Write-Host "Fresh database reached all expected Alembic heads." -ForegroundColor Green
Write-Host ""
Write-Host "Starting backend on http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Paste this target into New Migration: $proofTarget" -ForegroundColor Yellow
Write-Host ""

$uvicornArguments = @(
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    $Port.ToString(),
    "--reload",
    "--reload-dir",
    $backendRoot
)

$uvicornProcess = $null

try {
    $uvicornProcess = Start-Process `
        -FilePath $python `
        -ArgumentList $uvicornArguments `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -PassThru

    Write-Host "Uvicorn launcher PID: $($uvicornProcess.Id)"
    Write-Host "Waiting for live OpenAPI..." -ForegroundColor Cyan

    $openApiSchema = Wait-ForBackendOpenApi `
        -UvicornProcess $uvicornProcess `
        -TimeoutSeconds 60

    Assert-AssistantRoutes -OpenApiSchema $openApiSchema

    Write-Host ""
    Write-Host "Fresh backend verification passed." -ForegroundColor Green
    Write-Host "OpenAPI: http://127.0.0.1:$Port/openapi.json"
    Write-Host "Press Ctrl+C to stop the backend." -ForegroundColor Yellow
    Write-Host ""

    Wait-Process -Id $uvicornProcess.Id
}
finally {
    if ($null -ne $uvicornProcess) {
        Write-Host ""
        Write-Host "Stopping backend process tree..." -ForegroundColor Yellow

        try {
            Stop-ExistingBackendProcesses -Quiet
            Write-Host "Backend stopped." -ForegroundColor Green
        }
        catch {
            Write-Warning "Backend cleanup warning: $($_.Exception.Message)"
        }
    }
}