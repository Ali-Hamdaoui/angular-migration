[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\Users\abdelilah.mortaki\Desktop\angular-migration",
    [string]$SourceRoot = "C:\Users\abdelilah.mortaki\Desktop\angular-crud-poc",
    [string]$TargetBaseRoot = "C:\Users\abdelilah.mortaki\Desktop\angularRus",
    [int]$Port = 8000,
    [switch]$DisableLlm
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

$expectedRuntimeRoutes = @{
    "/api/v1/runs/{run_id}/assistant/messages" = @("get", "post")
    "/api/v1/runs/{run_id}/assistant/events"   = @("get")
    "/api/v1/runs/{run_id}/transformation" = @("get")
    "/api/v1/runs/{run_id}/transformation/prompts/{prompt_id}/decision" = @("post")
    "/api/v1/runs/{run_id}/transformation/gates/{gate_id}/decisions" = @("post")
    "/api/v1/runs/{run_id}/transformation/cancel" = @("post")
    "/api/v1/runs/{run_id}/transformation/restart" = @("post")
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
    $processName = [string]$ProcessInfo.Name
    $normalizedRepoRoot = $RepoRoot.ToLowerInvariant()
    $normalizedBackendRoot = $backendRoot.ToLowerInvariant()

    $isUvicorn = (
        $processName -match "^uvicorn(?:\.exe)?$" -or
        (
            $processName -match "^python(?:\.exe)?$" -and
            $normalizedCommandLine -match "\s-m\s+uvicorn(\s|$)"
        )
    )
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

function Test-IsRepositoryTransformerWorkerProcess {
    param(
        [Parameter(Mandatory)]
        [object]$ProcessInfo
    )

    $commandLine = [string]$ProcessInfo.CommandLine

    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    $normalizedCommandLine = $commandLine.ToLowerInvariant()
    $processName = [string]$ProcessInfo.Name
    $belongsToRepository = (
        $normalizedCommandLine.Contains($RepoRoot.ToLowerInvariant()) -or
        $normalizedCommandLine.Contains($backendRoot.ToLowerInvariant())
    )

    return (
        $processName -match "^python(?:\.exe)?$" -and
        $normalizedCommandLine -match "\s-m\s+app\.orchestration\.transformer_worker(\s|$)" -and
        $belongsToRepository
    )
}

function Test-IsRepositoryRuntimeProcess {
    param(
        [Parameter(Mandatory)]
        [object]$ProcessInfo
    )

    return (
        (Test-IsRepositoryUvicornProcess -ProcessInfo $ProcessInfo) -or
        (Test-IsRepositoryTransformerWorkerProcess -ProcessInfo $ProcessInfo)
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

function Stop-ExistingRepositoryRuntimeProcesses {
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

    $unrelatedPortOwners = @()

    foreach ($processId in $portOwnerIds) {
        $ownerId = [int]$processId
        $currentId = $ownerId
        $visitedAncestors = [System.Collections.Generic.HashSet[int]]::new()
        $belongsToRepository = $false

        while ($processesById.ContainsKey($currentId)) {
            if (-not $visitedAncestors.Add($currentId)) {
                break
            }

            $processInfo = $processesById[$currentId]

            if (Test-IsRepositoryRuntimeProcess -ProcessInfo $processInfo) {
                $belongsToRepository = $true
                break
            }

            $currentId = [int]$processInfo.ParentProcessId
        }

        if ($belongsToRepository) {
            [void]$candidateIds.Add($ownerId)
        }
        else {
            $unrelatedPortOwners += $ownerId
        }
    }

    if ($unrelatedPortOwners.Count -gt 0) {
        $ownerDescriptions = @(
            foreach ($ownerId in $unrelatedPortOwners) {
                if ($processesById.ContainsKey($ownerId)) {
                    $owner = $processesById[$ownerId]
                    "PID=$ownerId Name=$($owner.Name) CommandLine=$($owner.CommandLine)"
                }
                else {
                    "PID=$ownerId"
                }
            }
        )

        throw (
            "Port $Port is occupied by an unrelated process; it was not stopped. " +
            ($ownerDescriptions -join " | ")
        )
    }

    # Repository-specific Uvicorn and Transformer worker processes.
    foreach ($processInfo in $processSnapshot) {
        if (Test-IsRepositoryRuntimeProcess -ProcessInfo $processInfo) {
            $processId = [int]$processInfo.ProcessId

            if ($processId -gt 0 -and $processId -ne $PID) {
                [void]$candidateIds.Add($processId)
            }
        }
    }

    # Include matching repository runtime ancestors of port owners.
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

            if (Test-IsRepositoryRuntimeProcess -ProcessInfo $parentProcess) {
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
            Write-Host "No existing repository runtime process found." -ForegroundColor DarkGray
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
            Write-Host "Existing repository runtime process tree:" -ForegroundColor Yellow

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
                "Unable to stop repository runtime process IDs: {0}" -f
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

    # Verify that no matching Uvicorn or Transformer worker remains.
    $remainingRepositoryRuntime = @(
        Get-ProcessSnapshot |
            Where-Object {
                $_.ProcessId -ne $PID -and
                (Test-IsRepositoryRuntimeProcess -ProcessInfo $_)
            }
    )

    if ($remainingRepositoryRuntime.Count -gt 0) {
        $remainingDescriptions = @(
            $remainingRepositoryRuntime |
                ForEach-Object {
                    "PID=$($_.ProcessId) Parent=$($_.ParentProcessId) CommandLine=$($_.CommandLine)"
                }
        )

        throw (
            "Repository runtime processes remain after cleanup: " +
            ($remainingDescriptions -join " | ")
        )
    }

    if (-not $Quiet) {
        Write-Host "Repository runtime cleanup completed. Port $Port is free." -ForegroundColor Green
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

function Get-AlembicHeadIds {
    param(
        [Parameter(Mandatory)]
        [string[]]$Lines
    )

    $headIds = @(
        foreach ($line in $Lines) {
            $text = [string]$line

            # Supports:
            #   20260727_31 (head)
            #   abc123 (branch-name) (head)
            if ($text -match '^\s*(?<revision>[^\s]+).*\(head\)\s*$') {
                $Matches["revision"]
            }
        }
    )

    return @(
        $headIds |
            Sort-Object -Unique
    )
}

function Assert-PythonSourcesCompile {
    Write-Host ""
    Write-Host "Validating backend Python syntax..." -ForegroundColor Cyan

    $compileResult = Invoke-PythonCapture -Arguments @(
        "-m",
        "compileall",
        "-q",
        "app"
    )

    $compileResult.Lines |
        ForEach-Object { Write-Host $_ }

    if ($compileResult.ExitCode -ne 0) {
        throw (
            "Backend Python syntax validation failed. " +
            "Fix the reported source file before creating or starting the backend."
        )
    }

    Write-Host "Backend Python syntax validation passed." -ForegroundColor Green
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

function Assert-RequiredRuntimeRoutes {
    param(
        [Parameter(Mandatory)]
        [object]$OpenApiSchema
    )

    $availablePathNames = @(
        $OpenApiSchema.paths.PSObject.Properties.Name
    )

    Write-Host ""
    Write-Host "Live required runtime OpenAPI routes:" -ForegroundColor Cyan

    $runtimePathNames = @(
        $availablePathNames |
            Where-Object {
                $_ -match "/assistant/" -or
                $_ -match "/transformation(?:/|$)"
            } |
            Sort-Object
    )

    foreach ($runtimePath in $runtimePathNames) {
        $pathProperty = $OpenApiSchema.paths.PSObject.Properties |
            Where-Object { $_.Name -eq $runtimePath } |
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
            $runtimePath
        )
    }

    foreach ($expectedRoute in $expectedRuntimeRoutes.GetEnumerator()) {
        $routePath = [string]$expectedRoute.Key
        $requiredMethods = @($expectedRoute.Value)

        if ($availablePathNames -notcontains $routePath) {
            throw "Required runtime route is absent from live OpenAPI: $routePath"
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
                    "Runtime route $routePath is missing required method " +
                    "$($requiredMethod.ToUpperInvariant())."
                )
            }
        }
    }

    Write-Host ""
    Write-Host "All required runtime routes are registered in the live backend." -ForegroundColor Green
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
Write-Host "Cleaning existing repository runtime processes..." -ForegroundColor Cyan

Stop-ExistingRepositoryRuntimeProcesses

Set-Location $backendRoot
Assert-PythonSourcesCompile

# Create a completely fresh database and target folder.
foreach ($pathToReset in @($dataRoot, $proofTarget)) {
    if (Test-Path -LiteralPath $pathToReset) {
        Remove-Item `
            -LiteralPath $pathToReset `
            -Recurse `
            -Force `
            -ErrorAction Stop
    }

    if (Test-Path -LiteralPath $pathToReset) {
        throw "Unable to completely reset path: $pathToReset"
    }
}

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

if (Test-Path -LiteralPath $dbPath) {
    throw "Fresh database path already exists before migrations: $dbPath"
}

# Backend runtime configuration.
$env:APPLICATION_DATA_ROOT = $dataRoot
$env:DATABASE_URL = "sqlite:///$($dbPath -replace '\\', '/')"
$env:ALLOWED_SOURCE_ROOTS = $SourceRoot
$env:ALLOWED_TARGET_ROOTS = $TargetBaseRoot
$env:BACKEND_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
$env:NPM_CONFIG_REGISTRY = "https://registry.npmjs.org/"
$env:NPM_CONFIG_STRICT_SSL = "true"
$env:LLM_ENABLED = if ($DisableLlm) { "false" } else { "true" }

$llmModeDescription = if ($DisableLlm) {
    "disabled explicitly with -DisableLlm"
}
else {
    "enabled and required by default"
}

Write-Host ""
Write-Host "Fresh backend configuration" -ForegroundColor Cyan
Write-Host "Repository:    $RepoRoot"
Write-Host "Backend:       $backendRoot"
Write-Host "Database:      $env:DATABASE_URL"
Write-Host "Source root:   $SourceRoot"
Write-Host "Target base:   $TargetBaseRoot"
Write-Host "Target to use: $proofTarget" -ForegroundColor Green
Write-Host "LLM mode:      $llmModeDescription"
Write-Host ""

$llmValidationScript = @'
from app.core.config import get_settings

settings = get_settings()

if not settings.llm_enabled:
    print("LLM: explicitly disabled; deterministic Transformer only.")
    raise SystemExit(0)

required = {
    "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
    "AZURE_OPENAI_DEPLOYMENT": settings.azure_openai_deployment,
    "AZURE_OPENAI_API_VERSION": settings.azure_openai_api_version,
    "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
}

missing = [
    name
    for name, value in required.items()
    if not value
]

if missing:
    print(
        "LLM configuration incomplete: "
        + ", ".join(missing)
    )
    raise SystemExit(2)

print(
    "LLM: Azure OpenAI ready; "
    f"deployment {settings.azure_openai_deployment}, "
    f"API {settings.azure_openai_api_version}, "
    "endpoint configured."
)
'@

$previousErrorActionPreference = $ErrorActionPreference

try {
    $ErrorActionPreference = "Continue"

    $llmConfigLines = @(
        $llmValidationScript |
            & $python - 2>&1 |
            ForEach-Object { $_.ToString() }
    )

    $llmConfigExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

$llmConfigLines |
    ForEach-Object { Write-Host $_ }

if ($llmConfigExitCode -ne 0) {
    throw (
        "Azure LLM configuration validation failed. " +
        "The backend was not started."
    )
}

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

$availableAlembicHeads = @(
    Get-AlembicHeadIds -Lines $headsResult.Lines
)

if ($availableAlembicHeads.Count -ne 1) {
    throw (
        "Expected exactly one Alembic head, found {0}: {1}" -f
        $availableAlembicHeads.Count,
        ($availableAlembicHeads -join ", ")
    )
}

Write-Host ""
Write-Host (
    "Detected {0} Alembic head(s): {1}" -f
    $availableAlembicHeads.Count,
    ($availableAlembicHeads -join ", ")
) -ForegroundColor Green

Write-Host ""
Write-Host "Applying Alembic head..." -ForegroundColor Cyan

& $python -m alembic -c alembic.ini upgrade head

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

$appliedAlembicHeads = @(
    Get-AlembicHeadIds -Lines $currentResult.Lines
)

$missingAppliedHeads = @(
    $availableAlembicHeads |
        Where-Object {
            $_ -notin $appliedAlembicHeads
        }
)

if ($missingAppliedHeads.Count -gt 0) {
    throw (
        "Fresh database did not reach the available Alembic head. " +
        "Missing: " +
        ($missingAppliedHeads -join ", ")
    )
}

Write-Host ""
Write-Host (
    "Fresh database reached Alembic head: {0}" -f
    ($availableAlembicHeads -join ", ")
) -ForegroundColor Green

Write-Host ""
Write-Host "Validating backend application import..." -ForegroundColor Cyan

$importResult = Invoke-PythonCapture -Arguments @(
    "-c",
    "from app.main import app; print('Backend application import passed.')"
)

$importResult.Lines |
    ForEach-Object { Write-Host $_ }

if ($importResult.ExitCode -ne 0) {
    throw (
        "Backend application import failed after database migration. " +
        "Uvicorn will not be started."
    )
}

Write-Host "Backend application import validation passed." -ForegroundColor Green

Write-Host ""
Write-Host "Validating Transformer worker import..." -ForegroundColor Cyan

$workerImportResult = Invoke-PythonCapture -Arguments @(
    "-c",
    "import app.orchestration.transformer_worker; print('Transformer worker import passed.')"
)

$workerImportResult.Lines | ForEach-Object { Write-Host $_ }

if ($workerImportResult.ExitCode -ne 0) {
    throw "Transformer worker import failed."
}

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
    $Port.ToString()
)

$workerArguments = @(
    "-m",
    "app.orchestration.transformer_worker"
)

$runtimeLogRoot = Join-Path $dataRoot "runtime-logs"
New-Item -ItemType Directory -Force -Path $runtimeLogRoot | Out-Null

$apiStdout = Join-Path $runtimeLogRoot "api.stdout.log"
$apiStderr = Join-Path $runtimeLogRoot "api.stderr.log"
$workerStdout = Join-Path $runtimeLogRoot "worker.stdout.log"
$workerStderr = Join-Path $runtimeLogRoot "worker.stderr.log"

$uvicornProcess = $null
$transformerWorker = $null

try {
    $uvicornProcess = Start-Process `
        -FilePath $python `
        -ArgumentList $uvicornArguments `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -RedirectStandardOutput $apiStdout `
        -RedirectStandardError $apiStderr `
        -PassThru

    $null = $uvicornProcess.Handle

    $transformerWorker = Start-Process `
        -FilePath $python `
        -ArgumentList $workerArguments `
        -WorkingDirectory $backendRoot `
        -NoNewWindow `
        -RedirectStandardOutput $workerStdout `
        -RedirectStandardError $workerStderr `
        -PassThru

    $null = $transformerWorker.Handle

    Write-Host "Uvicorn launcher PID: $($uvicornProcess.Id)"
    Write-Host "Transformer worker PID: $($transformerWorker.Id)"
    Write-Host "API stdout:    $apiStdout"
    Write-Host "API stderr:    $apiStderr"
    Write-Host "Worker stdout: $workerStdout"
    Write-Host "Worker stderr: $workerStderr"
    Write-Host "Waiting for live OpenAPI..." -ForegroundColor Cyan

    $openApiSchema = Wait-ForBackendOpenApi `
        -UvicornProcess $uvicornProcess `
        -TimeoutSeconds 60

    Assert-RequiredRuntimeRoutes -OpenApiSchema $openApiSchema

    Start-Sleep -Seconds 2
    $transformerWorker.Refresh()

    if ($transformerWorker.HasExited) {
        $transformerWorker.WaitForExit()
        throw "Transformer worker exited during startup with code $($transformerWorker.ExitCode)."
    }

    Write-Host ""
    Write-Host "Fresh backend verification passed." -ForegroundColor Green
    Write-Host "OpenAPI: http://127.0.0.1:$Port/openapi.json"
    Write-Host "Press Ctrl+C to stop the backend and Transformer worker." -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        $uvicornProcess.Refresh()
        $transformerWorker.Refresh()

        if ($uvicornProcess.HasExited) {
            $uvicornProcess.WaitForExit()
            throw "Uvicorn exited with code $($uvicornProcess.ExitCode)."
        }

        if ($transformerWorker.HasExited) {
            $transformerWorker.WaitForExit()
            throw "Transformer worker exited with code $($transformerWorker.ExitCode)."
        }

        Start-Sleep -Seconds 1
    }
}
finally {
    if ($null -ne $uvicornProcess -or $null -ne $transformerWorker) {
        Write-Host ""
        Write-Host "Stopping repository runtime process trees..." -ForegroundColor Yellow

        try {
            Stop-ExistingRepositoryRuntimeProcesses -Quiet
            Write-Host "Backend and Transformer worker stopped." -ForegroundColor Green
        }
        catch {
            Write-Warning "Backend cleanup warning: $($_.Exception.Message)"
        }
    }
}
